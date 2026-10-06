import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_DEFAULT_REGION", "af-south-1")
INGESTION_QUEUE_URL = os.getenv("SQS_INGESTION_QUEUE_URL")
EMBEDDING_QUEUE_URL = os.getenv("SQS_EMBEDDING_QUEUE_URL")

BATCH_SIZE = int(os.getenv("INGESTION_BATCH_SIZE", "50"))
WAIT_TIME_SECONDS = int(os.getenv("SQS_WAIT_TIME_SECONDS", "20"))
VISIBILITY_TIMEOUT = int(os.getenv("SQS_VISIBILITY_TIMEOUT", "300"))
MAX_FOODS_PER_FILE = int(os.getenv("MAX_FOODS_PER_FILE", "100000"))
MAX_BATCHES_PER_FILE = int(os.getenv("MAX_BATCHES_PER_FILE", "2000"))

if not INGESTION_QUEUE_URL:
    raise RuntimeError("Missing SQS_INGESTION_QUEUE_URL in .env")
if not EMBEDDING_QUEUE_URL:
    raise RuntimeError("Missing SQS_EMBEDDING_QUEUE_URL in .env")
if BATCH_SIZE <= 0 or BATCH_SIZE > 1000:
    raise RuntimeError("INGESTION_BATCH_SIZE must be between 1 and 1000")

aws_config = Config(
    region_name=REGION,
    retries={"max_attempts": 5, "mode": "standard"},
    connect_timeout=10,
    read_timeout=60,
)

sqs = boto3.client("sqs", config=aws_config)
s3 = boto3.client("s3", config=aws_config)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def delete_message(receipt_handle):
    sqs.delete_message(
        QueueUrl=INGESTION_QUEUE_URL,
        ReceiptHandle=receipt_handle,
    )


def parse_s3_event(body):
    if body.get("Event") == "s3:TestEvent":
        print("Received S3 test event; ignoring it.")
        return None, None

    records = body.get("Records")
    if not records:
        print("Message has no S3 Records:")
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return None, None

    record = records[0]
    if record.get("eventSource") != "aws:s3":
        print(f"Unsupported event source: {record.get('eventSource')}")
        return None, None

    if not record.get("eventName", "").startswith("ObjectCreated:"):
        print(f"Unsupported S3 event: {record.get('eventName')}")
        return None, None

    try:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        return bucket, key
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed S3 event: {exc}") from exc


def download_json(bucket, key):
    print(f"Downloading s3://{bucket}/{key}")
    response = s3.get_object(Bucket=bucket, Key=key)
    raw_text = response["Body"].read().decode("utf-8-sig").strip()

    if not raw_text:
        raise ValueError("Downloaded file is empty.")

    # Try standard JSON first (.json)
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Fallback to JSON Lines (.jsonl)
        records = []
        for line_num, line in enumerate(raw_text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as err:
                raise ValueError(
                    f"Invalid JSON on line {line_num} of s3://{bucket}/{key}: {err}"
                ) from err

        if not records:
            raise ValueError("No valid records found in JSONL file.")

        return records


def validate_foods(data):
    if isinstance(data, list):
        foods = data
    elif isinstance(data, dict) and isinstance(data.get("foods"), list):
        foods = data["foods"]
    else:
        raise ValueError("JSON must be a food list or contain a 'foods' list.")

    if not foods:
        raise ValueError("Knowledge base contains zero records.")
    if len(foods) > MAX_FOODS_PER_FILE:
        raise ValueError("Knowledge base exceeds MAX_FOODS_PER_FILE.")

    seen = set()
    duplicates = []

    for i, food in enumerate(foods):
        if not isinstance(food, dict):
            raise ValueError(f"Record {i} is not an object.")
        if not food.get("food_id"):
            raise ValueError(f"Record {i} is missing food_id.")
        if not food.get("name"):
            raise ValueError(f"Record {i} is missing name.")

        food_id = food["food_id"]
        if food_id in seen:
            duplicates.append(food_id)
        seen.add(food_id)

    if duplicates:
        raise ValueError(f"Duplicate food_id values found: {duplicates[:10]}")

    return foods


def build_job(bucket, key, batch_number, total_batches, start, end, total):
    return {
        "schema_version": "1.0",
        "job_type": "embedding_batch",
        "job_id": f"{bucket}:{key}:batch-{batch_number:05d}",
        "created_at": utc_now(),
        "source": {"bucket": bucket, "key": key},
        "batch": {
            "batch_number": batch_number,
            "total_batches": total_batches,
            "start_index": start,
            "end_index": end,
            "count": end - start,
            "total_foods": total,
        },
    }


def send_jobs(jobs):
    # SQS SendMessageBatch accepts at most 10 messages per API call.
    for offset in range(0, len(jobs), 10):
        chunk = jobs[offset:offset + 10]
        entries = [
            {
                "Id": str(i),
                "MessageBody": json.dumps(job, ensure_ascii=False),
            }
            for i, job in enumerate(chunk)
        ]

        response = sqs.send_message_batch(
            QueueUrl=EMBEDDING_QUEUE_URL,
            Entries=entries,
        )

        failed = response.get("Failed", [])
        if failed:
            raise RuntimeError(
                f"{len(failed)} batch jobs failed to publish: "
                f"{json.dumps(failed, indent=2)}"
            )

        print(f"Published {len(chunk)} batch job(s).")


def process_message(message):
    body = json.loads(message["Body"])
    print("\n============================================================")
    print("RECEIVED INGESTION EVENT")
    print("============================================================")
    print(json.dumps(body, indent=2, ensure_ascii=False))

    bucket, key = parse_s3_event(body)

    if not bucket or not key:
        delete_message(message["ReceiptHandle"])
        print("Message deleted.")
        return

    data = download_json(bucket, key)
    foods = validate_foods(data)

    total = len(foods)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    if total_batches > MAX_BATCHES_PER_FILE:
        raise ValueError("Number of batches exceeds MAX_BATCHES_PER_FILE.")

    print(f"Validated {total} foods.")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Creating {total_batches} batch jobs...")

    jobs = []
    for batch_number, start in enumerate(
        range(0, total, BATCH_SIZE), start=1
    ):
        end = min(start + BATCH_SIZE, total)
        jobs.append(
            build_job(
                bucket, key, batch_number, total_batches,
                start, end, total
            )
        )

    for job in jobs:
        b = job["batch"]
        print(
            f"  {job['job_id']} -> "
            f"records {b['start_index']} to {b['end_index'] - 1} "
            f"({b['count']} foods)"
        )

    print("\nPublishing jobs to embedding queue...")
    send_jobs(jobs)

    # Acknowledge the original S3 event only after every batch job
    # has been successfully published.
    delete_message(message["ReceiptHandle"])

    print("\nSUCCESS")
    print(f"{total_batches} embedding jobs created for {total} foods.")
    print("Original ingestion message deleted.")


def main():
    print("============================================================")
    print("KALNUR INGESTION WORKER")
    print("============================================================")
    print(f"Region: {REGION}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Ingestion queue: {INGESTION_QUEUE_URL}")
    print(f"Embedding queue: {EMBEDDING_QUEUE_URL}")
    print("\nWaiting for S3 ingestion events...")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=INGESTION_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=WAIT_TIME_SECONDS,
                VisibilityTimeout=VISIBILITY_TIMEOUT,
            )

            messages = response.get("Messages", [])
            if not messages:
                continue

            message = messages[0]

            try:
                process_message(message)
            except json.JSONDecodeError as exc:
                print(f"Invalid JSON message: {exc}")
                delete_message(message["ReceiptHandle"])
                print("Malformed message deleted.")
            except Exception as exc:
                # Do NOT delete on processing failure. SQS will retry
                # after the visibility timeout.
                print(f"\nPROCESSING ERROR: {type(exc).__name__}: {exc}")
                print("Message NOT deleted; SQS will retry it.")

        except KeyboardInterrupt:
            print("\nWorker stopped.")
            sys.exit(0)
        except ClientError as exc:
            print(f"\nAWS ERROR: {exc}")
            print("Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as exc:
            print(f"\nUNEXPECTED ERROR: {type(exc).__name__}: {exc}")
            print("Retrying in 5 seconds...")
            time.sleep(5)


if __name__ == "__main__":
    main()

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
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
EMBEDDING_QUEUE_URL = os.getenv("SQS_EMBEDDING_QUEUE_URL")
VECTOR_BUCKET = os.getenv("S3_VECTOR_BUCKET_NAME")
VECTOR_INDEX = os.getenv("S3_VECTOR_INDEX_NAME")
MODEL_ID = os.getenv("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
WAIT_TIME = int(os.getenv("SQS_WAIT_TIME_SECONDS", "20"))
VISIBILITY_TIMEOUT = int(os.getenv("SQS_VISIBILITY_TIMEOUT", "300"))

if not EMBEDDING_QUEUE_URL:
    raise RuntimeError("Missing SQS_EMBEDDING_QUEUE_URL in .env")
if not VECTOR_BUCKET:
    raise RuntimeError("Missing S3_VECTOR_BUCKET_NAME in .env")
if not VECTOR_INDEX:
    raise RuntimeError("Missing S3_VECTOR_INDEX_NAME in .env")
if DIMENSIONS not in (256, 512, 1024):
    raise RuntimeError("EMBEDDING_DIMENSIONS must be 256, 512, or 1024")

cfg = Config(
    region_name=REGION,
    retries={"max_attempts": 5, "mode": "standard"},
    connect_timeout=10,
    read_timeout=60,
)

bedrock_cfg = Config(
    region_name=BEDROCK_REGION,
    retries={"max_attempts": 5, "mode": "standard"},
    connect_timeout=10,
    read_timeout=60,
)

sqs = boto3.client("sqs", config=cfg)
s3 = boto3.client("s3", config=cfg)
bedrock = boto3.client("bedrock-runtime", config=bedrock_cfg)
s3vectors = boto3.client("s3vectors", config=cfg)


def now():
    return datetime.now(timezone.utc).isoformat()


def delete_message(receipt):
    sqs.delete_message(
        QueueUrl=EMBEDDING_QUEUE_URL,
        ReceiptHandle=receipt,
    )


def read_jsonl(bucket, key):
    response = s3.get_object(Bucket=bucket, Key=key)
    text = response["Body"].read().decode("utf-8-sig")

    foods = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"JSONL line {line_no} is not an object")
        foods.append(record)

    if not foods:
        raise ValueError("S3 JSONL file contains zero records")

    return foods


def parse_job(message):
    job = json.loads(message["Body"])

    if job.get("job_type") != "embedding_batch":
        raise ValueError(f"Unsupported job_type: {job.get('job_type')}")

    source = job.get("source", {})
    batch = job.get("batch", {})

    bucket = source.get("bucket")
    key = source.get("key")
    start = batch.get("start_index")
    end = batch.get("end_index")

    if not bucket or not key:
        raise ValueError("Job is missing S3 bucket/key")
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        raise ValueError("Job has an invalid batch range")

    return job, bucket, unquote_plus(key), start, end


def food_text(food):
    parts = []

    for label, field in [
        ("Food", "name"),
        ("Category", "category"),
        ("Region", "region"),
        ("Meal types", "meal_types"),
        ("Dietary flags", "dietary_flags"),
        ("Availability", "availability"),
        ("Description", "document"),
    ]:
        value = food.get(field)
        if value is not None and value != "":
            parts.append(f"{label}: {value}")

    nutrition = []
    for field in [
        "calories", "protein", "fat", "carbohydrates", "fiber",
        "sodium", "calcium", "iron", "magnesium", "potassium",
        "zinc", "vitamin_a", "vitamin_b12", "vitamin_c",
        "vitamin_d", "folate",
    ]:
        value = food.get(field)
        if value is not None:
            nutrition.append(f"{field}={value}")

    if nutrition:
        parts.append("Nutrition: " + ", ".join(nutrition))

    text = "\n".join(parts)
    return text[:50000] if text else json.dumps(food, ensure_ascii=False)


def embed(text, max_retries=6):
    delay = 1.0
    for attempt in range(max_retries):
        try:
            response = bedrock.invoke_model(
                modelId=MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "inputText": text,
                    "dimensions": DIMENSIONS,
                    "normalize": True,
                }),
            )

            result = json.loads(response["body"].read())
            vector = result.get("embedding")

            if not vector:
                raise RuntimeError("Bedrock returned no embedding")
            if len(vector) != DIMENSIONS:
                raise RuntimeError(
                    f"Expected {DIMENSIONS} dimensions, got {len(vector)}"
                )

            return [float(x) for x in vector]

        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "ThrottlingException" and attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise


def metadata(food, bucket, key, job_id):
    data = {
        "food_id": str(food["food_id"]),
        "name": str(food["name"]),
        "source_bucket": bucket,
        "source_key": key,
        "job_id": str(job_id),
        "ingested_at": now(),
    }

    for field in ["category", "region", "price_tier", "confidence",
                  "typical_portion_g"]:
        value = food.get(field)
        if isinstance(value, (str, int, float, bool)):
            data[field] = value

    return data


def process(message):
    job, bucket, key, start, end = parse_job(message)

    print("\n============================================================")
    print("RECEIVED EMBEDDING JOB")
    print("============================================================")
    print(f"Job:       {job.get('job_id')}")
    print(f"Source:    s3://{bucket}/{key}")
    print(f"Range:     {start} - {end - 1}")

    foods = read_jsonl(bucket, key)

    if end > len(foods):
        raise ValueError(f"Batch ends at {end}, but file has {len(foods)} records")

    batch = foods[start:end]
    print(f"Selected {len(batch)} foods")

    vectors = []

    for i, food in enumerate(batch, 1):
        if not food.get("food_id"):
            raise ValueError(f"Food at index {start + i - 1} is missing food_id")
        if not food.get("name"):
            raise ValueError(f"Food at index {start + i - 1} is missing name")

        print(f"  [{i:02d}/{len(batch)}] {food['name']}")

        vectors.append({
            "key": str(food["food_id"]),
            "data": {"float32": embed(food_text(food))},
            "metadata": metadata(
                food, bucket, key, job.get("job_id", "")
            ),
        })

    print("\nWriting vectors to S3 Vectors...")

    s3vectors.put_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        vectors=vectors,
    )

    print(f"Stored {len(vectors)} vectors")

    # Delete only after Bedrock and S3 Vectors both succeed.
    delete_message(message["ReceiptHandle"])

    print("\nSUCCESS")
    print(f"Processed {len(vectors)} foods")
    print("SQS message deleted")


def main():
    print("============================================================")
    print("KALNUR EMBEDDING WORKER")
    print("============================================================")
    print(f"Region:          {REGION}")
    print(f"Bedrock region:  {BEDROCK_REGION}")
    print(f"Bedrock model:   {MODEL_ID}")
    print(f"Dimensions:      {DIMENSIONS}")
    print(f"Embedding queue: {EMBEDDING_QUEUE_URL}")
    print(f"Vector bucket:   {VECTOR_BUCKET}")
    print(f"Vector index:    {VECTOR_INDEX}")
    print("\nWaiting for embedding jobs...")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=EMBEDDING_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=WAIT_TIME,
                VisibilityTimeout=VISIBILITY_TIMEOUT,
            )

            messages = response.get("Messages", [])
            if not messages:
                continue

            message = messages[0]

            try:
                process(message)
            except json.JSONDecodeError as exc:
                print(f"Invalid JSON job: {exc}")
                delete_message(message["ReceiptHandle"])
                print("Malformed job deleted")
            except Exception as exc:
                print(f"\nPROCESSING ERROR: {type(exc).__name__}: {exc}")
                print("Message NOT deleted; SQS will retry it")

        except KeyboardInterrupt:
            print("\nWorker stopped")
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

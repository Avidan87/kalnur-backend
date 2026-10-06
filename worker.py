import json
import os
import sys

import boto3
from dotenv import load_dotenv


# ============================================
# Load environment variables
# ============================================

load_dotenv()


# ============================================
# AWS configuration
# ============================================

REGION = os.environ["AWS_DEFAULT_REGION"]
QUEUE_URL = os.environ["SQS_QUEUE_URL"]


# ============================================
# AWS clients
# ============================================

sqs = boto3.client(
    "sqs",
    region_name=REGION
)

s3 = boto3.client(
    "s3",
    region_name=REGION
)


# ============================================
# Receive one message from SQS
# ============================================

print("Waiting for an SQS message...")

response = sqs.receive_message(
    QueueUrl=QUEUE_URL,
    MaxNumberOfMessages=1,
    WaitTimeSeconds=20
)

messages = response.get("Messages", [])


# ============================================
# No message
# ============================================

if not messages:

    print("No messages available.")

    sys.exit(0)


message = messages[0]


# ============================================
# Read SQS message
# ============================================

print("\nReceived SQS message:")

try:

    body = json.loads(message["Body"])

    print(
        json.dumps(
            body,
            indent=2
        )
    )

except json.JSONDecodeError:

    print("ERROR: SQS message is not valid JSON.")

    print(message["Body"])

    # Delete malformed message so it doesn't
    # continuously return to the queue.

    sqs.delete_message(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=message["ReceiptHandle"]
    )

    sys.exit(1)


# ============================================
# Handle S3 test events
# ============================================

if body.get("Event") == "s3:TestEvent":

    print("\nReceived S3 test event.")
    print("This is not a real object upload.")
    print("Ignoring test event...")

    sqs.delete_message(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=message["ReceiptHandle"]
    )

    print("S3 test event deleted from SQS.")

    sys.exit(0)


# ============================================
# Validate real S3 event
# ============================================

if "Records" not in body:

    print("\nUnknown SQS message format.")

    print(
        json.dumps(
            body,
            indent=2
        )
    )

    print("\nDeleting unknown message from SQS...")

    sqs.delete_message(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=message["ReceiptHandle"]
    )

    print("Unknown message deleted.")

    sys.exit(1)


# ============================================
# Get S3 event record
# ============================================

record = body["Records"][0]


# ============================================
# Extract S3 information
# ============================================

bucket_name = record["s3"]["bucket"]["name"]

object_key = record["s3"]["object"]["key"]


print("\nS3 information:")

print(f"Bucket: {bucket_name}")

print(f"Object: {object_key}")


# ============================================
# Download object from S3
# ============================================

print("\nDownloading object from S3...")

try:

    response = s3.get_object(
        Bucket=bucket_name,
        Key=object_key
    )

    content = response["Body"].read().decode("utf-8")

except Exception as e:

    print("\nERROR downloading object from S3:")

    print(e)

    print(
        "\nMessage will NOT be deleted from SQS."
    )

    print(
        "It can become visible again after the "
        "visibility timeout."
    )

    sys.exit(1)


# ============================================
# Parse JSONL
# ============================================

foods = []


for line_number, line in enumerate(
    content.splitlines(),
    start=1
):

    if not line.strip():
        continue

    try:

        food = json.loads(line)

        foods.append(food)

    except json.JSONDecodeError as e:

        print(
            f"\nWARNING: Invalid JSON on line "
            f"{line_number}: {e}"
        )


# ============================================
# Display results
# ============================================

print(
    f"\nSuccessfully loaded "
    f"{len(foods)} foods."
)


# ============================================
# Display first 5 foods
# ============================================

print("\nFirst 5 foods:")


for food in foods[:5]:

    print(
        f"- {food.get('name', 'Unknown')}"
    )


# ============================================
# Delete SQS message
# ============================================

print("\nDeleting SQS message...")


sqs.delete_message(
    QueueUrl=QUEUE_URL,
    ReceiptHandle=message["ReceiptHandle"]
)


print("SQS message successfully deleted.")


# ============================================
# Worker finished
# ============================================

print("\nWorker finished successfully.")
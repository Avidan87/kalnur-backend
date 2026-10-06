import json
import os

import boto3
from supabase import create_client
from dotenv import load_dotenv


# Load variables from .env
load_dotenv()


# ============================================================
# SUPABASE CONFIGURATION
# ============================================================

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_ANON_KEY
)


# ============================================================
# AWS CONFIGURATION
# ============================================================

AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
AWS_DEFAULT_REGION = os.environ["AWS_DEFAULT_REGION"]

S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]


# Create S3 client using the credentials from .env
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_DEFAULT_REGION
)


# ============================================================
# S3 DESTINATION
# ============================================================

S3_KEY = "knowledge-base/nigerian_foods.jsonl"


# ============================================================
# GET FOOD DATA FROM SUPABASE
# ============================================================

print("Connecting to Supabase...")

response = (
    supabase
    .table("nigerian_foods")
    .select("*")
    .execute()
)

foods = response.data

print(f"Retrieved {len(foods)} foods from Supabase")


# ============================================================
# REMOVE EXISTING EMBEDDINGS
# ============================================================

records = []

for food in foods:
    food = food.copy()

    # We don't want to transfer the existing
    # 3072-dimensional pgvector embeddings.
    food.pop("embedding", None)

    records.append(food)


# ============================================================
# CONVERT DATA TO JSONL
# ============================================================

jsonl_data = "\n".join(
    json.dumps(
        record,
        ensure_ascii=False
    )
    for record in records
)


# ============================================================
# UPLOAD TO AMAZON S3
# ============================================================

print("Uploading data to Amazon S3...")

s3.put_object(
    Bucket=S3_BUCKET_NAME,
    Key=S3_KEY,
    Body=jsonl_data.encode("utf-8"),
    ContentType="application/json"
)


# ============================================================
# SUCCESS
# ============================================================

print()
print("========================================")
print("        KALNUR EXPORT SUCCESSFUL")
print("========================================")
print(f"Records exported : {len(records)}")
print(f"S3 bucket        : {S3_BUCKET_NAME}")
print(f"S3 location      : s3://{S3_BUCKET_NAME}/{S3_KEY}")
print("========================================")
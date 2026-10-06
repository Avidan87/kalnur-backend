import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

SOURCE_FILE = Path(
    r"C:\Users\avifr\Downloads\nigerian_foods.json"
)

OUTPUT_FILE = Path(
    r"C:\Users\avifr\KAI\knowledge-base\test\kalnur_foods_500.jsonl"
)

TARGET_RECORDS = 500

# Smaller batches because each Kalnur record has many fields.
BATCH_SIZE = 5

MAX_ATTEMPTS = 100

MODEL = os.getenv(
    "OPENAI_GENERATION_MODEL",
    "gpt-4o-mini"
)

REQUEST_DELAY_SECONDS = 1


# ============================================================
# OPENAI
# ============================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is missing from your .env file."
    )

client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ============================================================
# LOAD EXISTING DATA
# ============================================================

def load_food_file(path: Path) -> list[dict[str, Any]]:

    if not path.exists():
        raise FileNotFoundError(
            f"Source file not found:\n{path}"
        )

    text = path.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not text:
        raise ValueError(
            "Source file is empty."
        )

    # Try normal JSON first
    try:

        data = json.loads(text)

        if isinstance(data, list):
            records = data

        elif isinstance(data, dict):

            records = None

            for key in [
                "foods",
                "data",
                "records",
                "items"
            ]:

                if isinstance(data.get(key), list):
                    records = data[key]
                    break

            if records is None:
                raise ValueError(
                    "Could not find a list of food records."
                )

        else:
            raise ValueError(
                "Expected a JSON list or object."
            )

    except json.JSONDecodeError:

        # Try JSONL
        records = []

        for line_number, line in enumerate(
            text.splitlines(),
            start=1
        ):

            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line "
                    f"{line_number}: {exc}"
                )

            records.append(record)

    valid_records = [
        record
        for record in records
        if isinstance(record, dict)
    ]

    if not valid_records:
        raise ValueError(
            "No valid food records found."
        )

    return valid_records


# ============================================================
# NORMALIZE FOOD NAME
# ============================================================

def normalize_name(name: Any) -> str:

    if not isinstance(name, str):
        return ""

    name = name.lower().strip()

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    name = re.sub(
        r"[^a-z0-9\s]",
        "",
        name
    )

    return name


# ============================================================
# GET EXISTING FOOD NAMES
# ============================================================

def get_existing_names(
    records: list[dict[str, Any]]
) -> set[str]:

    names = set()

    for record in records:

        normalized = normalize_name(
            record.get("name")
        )

        if normalized:
            names.add(normalized)

    return names


# ============================================================
# INSPECT SCHEMA
# ============================================================

def describe_value(value: Any) -> Any:

    if isinstance(value, dict):

        return {
            key: describe_value(value[key])
            for key in value
        }

    if isinstance(value, list):

        if not value:
            return []

        return [
            describe_value(value[0])
        ]

    return type(value).__name__


def inspect_schema(
    records: list[dict[str, Any]]
) -> dict[str, Any]:

    first = records[0]

    return {
        key: describe_value(value)
        for key, value in first.items()
    }


# ============================================================
# REFERENCE EXAMPLES
# ============================================================

def build_examples(
    records: list[dict[str, Any]],
    count: int = 3
) -> list[dict[str, Any]]:

    if len(records) <= count:
        return records

    indexes = [
        round(
            i * (len(records) - 1) / (count - 1)
        )
        for i in range(count)
    ]

    return [
        records[index]
        for index in indexes
    ]


# ============================================================
# SYSTEM PROMPT
# ============================================================

def build_system_prompt(
    schema: dict[str, Any]
) -> str:

    return f"""
You are a senior food knowledge-base generation
specialist working on a RAG system called Kalnur.

Your job is to generate SYNTHETIC TEST FOOD RECORDS.

These records are being created specifically for:

- AWS S3 ingestion testing
- SQS buffering testing
- ECS worker testing
- batch processing testing
- vector database scaling experiments

The generated nutrition values are synthetic test values.
They must NOT be represented as authoritative medical or
nutritional advice.

IMPORTANT RULES:

1. Generate real, recognizable foods from around the world.

2. Foods do NOT need to be Nigerian.

3. Produce global cuisine diversity.

Examples include:

African
Asian
European
Middle Eastern
North American
South American
Caribbean
Central American
Oceania

4. Do not create fictional foods.

5. Do not create trivial variations of the same food.

For example, do NOT generate:

Chicken Rice
Chicken Rice Special
Chicken Rice Deluxe
Chicken Rice With Vegetables

6. Do not duplicate existing Kalnur foods.

7. Every record must follow the existing Kalnur schema.

8. Do not add random fields.

9. Do not remove existing fields.

10. Preserve the same data types as the reference schema.

11. Nutrition values should be internally plausible,
but they are synthetic test values.

12. Return ONLY valid JSON.

13. Return this exact structure:

{{
    "foods": [
        {{
            ...
        }}
    ]
}}

Existing Kalnur schema:

{json.dumps(schema, indent=2, ensure_ascii=False)}
""".strip()


# ============================================================
# USER PROMPT
# ============================================================

def build_user_prompt(
    existing_names: set[str],
    examples: list[dict[str, Any]],
    count: int
) -> str:

    existing_names_text = json.dumps(
        sorted(existing_names),
        ensure_ascii=False
    )

    examples_text = json.dumps(
        examples,
        indent=2,
        ensure_ascii=False
    )

    return f"""
Generate up to {count} NEW and UNIQUE food records.

The existing Kalnur database already contains these food
names:

{existing_names_text}

DO NOT generate any of these foods.

Also avoid obvious aliases, spelling variations, or trivial
variations of existing foods.

Use these existing Kalnur records as structural examples:

{examples_text}

Requirements:

- Every record must contain the correct fields.
- Every record must follow the same structure.
- Use realistic synthetic nutrition values.
- Use real foods.
- Use diverse international cuisines.
- Avoid duplicates.
- Avoid near-duplicates.
- Do not return explanations.
- Do not return markdown.
- Return only JSON.

Return:

{{
    "foods": [
        ...
    ]
}}
""".strip()


# ============================================================
# GENERATE BATCH
# ============================================================

def generate_batch(
    system_prompt: str,
    user_prompt: str,
    expected_count: int
) -> list[dict[str, Any]]:

    response = client.chat.completions.create(

        model=MODEL,

        temperature=0.8,

        response_format={
            "type": "json_object"
        },

        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError(
            "OpenAI returned an empty response."
        )

    data = json.loads(content)

    foods = data.get("foods")

    if not isinstance(foods, list):
        raise ValueError(
            "Response does not contain a 'foods' list."
        )

    if len(foods) == 0:
        raise ValueError(
            "OpenAI returned zero foods."
        )

    # OpenAI may return fewer than requested.
    # THAT IS NOW OK.
    if len(foods) < expected_count:

        print(
            f"OpenAI returned {len(foods)} "
            f"instead of {expected_count}. "
            f"Accepting them."
        )

    elif len(foods) > expected_count:

        print(
            f"OpenAI returned {len(foods)}. "
            f"Keeping first {expected_count}."
        )

        foods = foods[:expected_count]

    return foods


# ============================================================
# VALIDATE SCHEMA
# ============================================================

def validate_record(
    record: dict[str, Any],
    reference_keys: set[str]
) -> tuple[bool, str]:

    if not isinstance(record, dict):

        return False, "Not a JSON object."

    keys = set(record.keys())

    if keys != reference_keys:

        missing = reference_keys - keys
        extra = keys - reference_keys

        return False, (
            f"Schema mismatch. "
            f"Missing={missing}, "
            f"Extra={extra}"
        )

    name = record.get("name")

    if not isinstance(name, str):
        return False, "Invalid name."

    if not name.strip():
        return False, "Empty name."

    return True, ""


# ============================================================
# ACCEPT UNIQUE RECORDS
# ============================================================

def accept_unique_records(
    records: list[dict[str, Any]],
    used_names: set[str],
    reference_keys: set[str]
) -> list[dict[str, Any]]:

    accepted = []

    for record in records:

        valid, reason = validate_record(
            record,
            reference_keys
        )

        if not valid:

            print(
                f"  REJECTED: "
                f"{record.get('name', 'UNKNOWN')} "
                f"→ {reason}"
            )

            continue

        name = normalize_name(
            record["name"]
        )

        if name in used_names:

            print(
                f"  DUPLICATE: "
                f"{record['name']}"
            )

            continue

        used_names.add(name)

        accepted.append(record)

    return accepted


# ============================================================
# ADD TEST METADATA
# ============================================================

def prepare_test_record(
    record: dict[str, Any]
) -> dict[str, Any]:

    record = record.copy()

    # Let Python generate IDs.
    record["food_id"] = (
        f"test-{uuid.uuid4().hex[:12]}"
    )

    # Explicitly mark synthetic data.
    #
    # These fields are intentionally added after
    # validation because they are test metadata.
    record["data_source"] = "openai_generated"
    record["test_data"] = True

    return record


# ============================================================
# SAVE JSONL
# ============================================================

def save_jsonl(
    records: list[dict[str, Any]],
    path: Path
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "w",
        encoding="utf-8"
    ) as file:

        for record in records:

            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                )
                + "\n"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("KALNUR TEST FOOD GENERATOR")
    print("=" * 60)

    print(
        f"\nSource:\n{SOURCE_FILE}"
    )

    print(
        f"Output:\n{OUTPUT_FILE}"
    )

    print(
        f"Target records: {TARGET_RECORDS}"
    )

    print(
        f"OpenAI model: {MODEL}"
    )

    print(
        f"Batch size: {BATCH_SIZE}"
    )

    # --------------------------------------------------------
    # Load existing 134 foods
    # --------------------------------------------------------

    existing_records = load_food_file(
        SOURCE_FILE
    )

    print(
        f"\nLoaded {len(existing_records)} "
        f"existing Kalnur records."
    )

    if len(existing_records) >= TARGET_RECORDS:

        raise ValueError(
            f"Existing dataset already contains "
            f"{len(existing_records)} records."
        )

    # --------------------------------------------------------
    # Schema
    # --------------------------------------------------------

    schema = inspect_schema(
        existing_records
    )

    reference_keys = set(
        existing_records[0].keys()
    )

    print("\nDetected schema:")

    for key in sorted(reference_keys):
        print(f"  - {key}")

    # --------------------------------------------------------
    # Existing names
    # --------------------------------------------------------

    used_names = get_existing_names(
        existing_records
    )

    # --------------------------------------------------------
    # Examples
    # --------------------------------------------------------

    examples = build_examples(
        existing_records,
        count=3
    )

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    system_prompt = build_system_prompt(
        schema
    )

    # --------------------------------------------------------
    # How many new records?
    # --------------------------------------------------------

    required_new_records = (
        TARGET_RECORDS
        - len(existing_records)
    )

    print(
        f"\nNeed to generate "
        f"{required_new_records} additional foods."
    )

    generated_records = []

    attempts = 0

    # --------------------------------------------------------
    # Generate until we reach 366
    # --------------------------------------------------------

    while len(generated_records) < required_new_records:

        attempts += 1

        if attempts > MAX_ATTEMPTS:

            raise RuntimeError(
                "Maximum generation attempts reached.\n"
                f"Generated "
                f"{len(generated_records)} "
                f"of {required_new_records} "
                "required foods."
            )

        remaining = (
            required_new_records
            - len(generated_records)
        )

        request_count = min(
            BATCH_SIZE,
            remaining
        )

        print("\n" + "-" * 60)

        print(
            f"Generation attempt {attempts}"
        )

        print(
            f"Current progress: "
            f"{len(generated_records)}/"
            f"{required_new_records}"
        )

        print(
            f"Requesting up to "
            f"{request_count} foods..."
        )

        # ----------------------------------------------------
        # Tell OpenAI about ALL names already used.
        # ----------------------------------------------------

        user_prompt = build_user_prompt(
            existing_names=used_names,
            examples=examples,
            count=request_count
        )

        try:

            batch = generate_batch(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                expected_count=request_count
            )

            print(
                f"Received {len(batch)} "
                f"records from OpenAI."
            )

            # ------------------------------------------------
            # Validate + deduplicate
            # ------------------------------------------------

            accepted = accept_unique_records(
                records=batch,
                used_names=used_names,
                reference_keys=reference_keys
            )

            print(
                f"Accepted {len(accepted)} "
                f"new records."
            )

            # ------------------------------------------------
            # Add synthetic metadata
            # ------------------------------------------------

            for record in accepted:

                test_record = prepare_test_record(
                    record
                )

                generated_records.append(
                    test_record
                )

            print(
                f"TOTAL NEW RECORDS: "
                f"{len(generated_records)}/"
                f"{required_new_records}"
            )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

        except KeyboardInterrupt:

            print(
                "\n\nGeneration stopped by user."
            )

            print(
                f"Generated so far: "
                f"{len(generated_records)}"
            )

            return

        except Exception as exc:

            print(
                f"\nGeneration error:"
            )

            print(
                f"{type(exc).__name__}: {exc}"
            )

            print(
                "Waiting before retry..."
            )

            time.sleep(5)

    # --------------------------------------------------------
    # Exactly 366 generated
    # --------------------------------------------------------

    generated_records = generated_records[
        :required_new_records
    ]

    # --------------------------------------------------------
    # Combine
    # --------------------------------------------------------

    final_records = (
        existing_records
        + generated_records
    )

    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    if len(final_records) != TARGET_RECORDS:

        raise RuntimeError(
            f"Expected {TARGET_RECORDS} "
            f"final records but got "
            f"{len(final_records)}."
        )

    # --------------------------------------------------------
    # Check duplicate names
    # --------------------------------------------------------

    final_names = []

    for record in final_records:

        name = normalize_name(
            record.get("name")
        )

        if name:
            final_names.append(name)

    duplicate_names = {
        name
        for name in final_names
        if final_names.count(name) > 1
    }

    if duplicate_names:

        raise RuntimeError(
            "Duplicate food names detected:\n"
            + "\n".join(
                sorted(duplicate_names)
            )
        )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_jsonl(
        final_records,
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("SUCCESS")
    print("=" * 60)

    print(
        f"Original Kalnur records: "
        f"{len(existing_records)}"
    )

    print(
        f"Generated test records: "
        f"{len(generated_records)}"
    )

    print(
        f"Final records: "
        f"{len(final_records)}"
    )

    print(
        f"\nOutput:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        "\nThe 500-record dataset is ready."
    )


if __name__ == "__main__":
    main()
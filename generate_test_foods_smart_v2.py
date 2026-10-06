import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# KALNUR SMART / RESUMABLE TEST FOOD GENERATOR
# ============================================================
#
# This is a replacement for the original generator.
#
# It keeps the original Kalnur generation prompt/schema strategy,
# but adds:
#
# 1. Persistent JSONL checkpointing.
# 2. Automatic resume after interruption/crash.
# 3. SQLite name cache.
# 4. Cheap candidate-name stage before expensive full records.
# 5. Smaller full-record batches.
# 6. Immediate save after every accepted record.
# 7. No "expected exactly N" failure when the model returns fewer.
# 8. Safe retries and timeout handling.
#
# IMPORTANT:
# The 134 original foods are never regenerated.
#
# ============================================================


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

CACHE_DB = Path(
    r"C:\Users\avifr\KAI\knowledge-base\test\food_generation_cache.db"
)

TARGET_RECORDS = 500

# Cheap candidate-name generation.
NAME_BATCH_SIZE = 20

# Expensive full-record generation.
# Keep this small because each record has many fields.
RECORD_BATCH_SIZE = 5

MAX_ATTEMPTS = 300

MODEL = os.getenv(
    "OPENAI_GENERATION_MODEL",
    "gpt-4o-mini"
)

NAME_MODEL = os.getenv(
    "OPENAI_NAME_MODEL",
    MODEL
)

REQUEST_DELAY_SECONDS = 1

# A request that hangs should not hang forever.
REQUEST_TIMEOUT_SECONDS = 90


# ============================================================
# OPENAI
# ============================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is missing from your .env file."
    )

client = OpenAI(
    api_key=OPENAI_API_KEY,
    timeout=REQUEST_TIMEOUT_SECONDS,
    max_retries=2,
)


# ============================================================
# LOAD FOOD FILE
# ============================================================

def load_food_file(
    path: Path
) -> list[dict[str, Any]]:

    if not path.exists():
        raise FileNotFoundError(
            f"Food file not found:\n{path}"
        )

    text = path.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not text:
        raise ValueError(
            "Food file is empty."
        )

    # Try normal JSON first.
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

                if isinstance(
                    data.get(key),
                    list
                ):

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

        # JSONL fallback.
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

def normalize_name(
    name: Any
) -> str:

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
# SQLITE CACHE
# ============================================================

def init_cache() -> sqlite3.Connection:

    CACHE_DB.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(
        CACHE_DB
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS food_names (
            normalized_name TEXT PRIMARY KEY,
            original_name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )

    conn.commit()

    return conn


def cache_name(
    conn: sqlite3.Connection,
    name: str,
    status: str
) -> None:

    normalized = normalize_name(name)

    if not normalized:
        return

    conn.execute(
        """
        INSERT OR IGNORE INTO food_names
        (normalized_name, original_name, status, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            normalized,
            name,
            status,
            time.time()
        )
    )

    conn.commit()


def cache_exists(
    conn: sqlite3.Connection,
    name: str
) -> bool:

    normalized = normalize_name(name)

    if not normalized:
        return False

    row = conn.execute(
        """
        SELECT 1
        FROM food_names
        WHERE normalized_name = ?
        LIMIT 1
        """,
        (normalized,)
    ).fetchone()

    return row is not None


# ============================================================
# CHECKPOINT
# ============================================================

def save_checkpoint(
    records: list[dict[str, Any]],
    max_retries: int = 5
) -> None:

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = OUTPUT_FILE.with_suffix(
        ".tmp"
    )

    with temp_file.open(
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

        file.flush()
        os.fsync(file.fileno())

    # Atomic replacement with retries for Windows file locks.
    for attempt in range(max_retries):
        try:
            temp_file.replace(
                OUTPUT_FILE
            )
            return

        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(0.2 * (attempt + 1))
            else:
                # Fallback: direct write if replace is blocked by an external lock.
                try:
                    with OUTPUT_FILE.open(
                        "w",
                        encoding="utf-8"
                    ) as out_file:
                        for record in records:
                            out_file.write(
                                json.dumps(
                                    record,
                                    ensure_ascii=False
                                )
                                + "\n"
                            )
                    if temp_file.exists():
                        try:
                            temp_file.unlink()
                        except Exception:
                            pass
                    return

                except Exception as exc:
                    raise PermissionError(
                        f"Could not save checkpoint after {max_retries} attempts: {exc}"
                    )


# ============================================================
# SCHEMA INSPECTION
# ============================================================

def describe_value(
    value: Any
) -> Any:

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
            i * (len(records) - 1)
            / (count - 1)
        )
        for i in range(count)
    ]

    return [
        records[index]
        for index in indexes
    ]


# ============================================================
# ORIGINAL HIGH-QUALITY SYSTEM PROMPT
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

{json.dumps(
    schema,
    indent=2,
    ensure_ascii=False
)}
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
Generate UP TO {count} NEW and UNIQUE food records.

The existing Kalnur database already contains these
food names:

{existing_names_text}

DO NOT generate any of these foods.

Also avoid:

- obvious aliases
- spelling variations
- translated duplicates
- trivial variations
- preparation-only variations of an existing dish
- the same dish with a minor ingredient change

Use these existing Kalnur records as structural examples:

{examples_text}

Requirements:

- Every record must contain the correct fields.
- Every record must follow the same structure.
- Use realistic synthetic nutrition values.
- Use real foods.
- Use diverse international cuisines.
- Do not repeat any requested food within this response.
- Prefer genuinely different dishes rather than variations.
- If you cannot safely produce the requested number of
  unique foods, return fewer rather than inventing duplicates.

Return ONLY:

{{
    "foods": [
        ...
    ]
}}
""".strip()


# ============================================================
# CHEAP CANDIDATE-NAME STAGE
# ============================================================

def generate_candidate_names(
    existing_names: set[str],
    count: int
) -> list[str]:

    # Send a bounded list to the model so the prompt does not
    # grow indefinitely as the dataset grows.
    known_names = sorted(existing_names)

    if len(known_names) > 350:
        known_names = known_names[-350:]

    prompt = f"""
You are the candidate-name stage of the Kalnur food
knowledge-base generator.

Generate UP TO {count} REAL and DISTINCT food dishes.

Foods may come from ANY country.

Do NOT generate:

- fictional foods
- drinks
- raw ingredients
- aliases
- spelling variants
- translated duplicates
- trivial variations
- foods already in the known list

Known food names:

{json.dumps(
    known_names,
    ensure_ascii=False
)}

Prioritize global cuisine diversity.

Return ONLY valid JSON in this format:

{{
    "foods": [
        "Food name 1",
        "Food name 2"
    ]
}}
""".strip()

    response = client.chat.completions.create(
        model=NAME_MODEL,
        temperature=0.9,
        response_format={
            "type": "json_object"
        },
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a food candidate-name "
                    "generation specialist that always outputs valid JSON."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    content = (
        response.choices[0]
        .message
        .content
    )

    if not content:
        return []

    data = json.loads(content)

    names = data.get(
        "foods",
        []
    )

    if not isinstance(names, list):
        return []

    return [
        name.strip()
        for name in names
        if isinstance(name, str)
        and name.strip()
    ]


# ============================================================
# EXPENSIVE FULL RECORD STAGE
# ============================================================

def generate_full_records(
    names: list[str],
    system_prompt: str,
    examples: list[dict[str, Any]]
) -> list[dict[str, Any]]:

    prompt = f"""
Create complete Kalnur nutrition records for EXACTLY
these requested food names:

{json.dumps(
    names,
    ensure_ascii=False
)}

Use the system schema exactly.

Reference Kalnur examples:

{json.dumps(
    examples,
    indent=2,
    ensure_ascii=False
)}

CRITICAL:

- Do not substitute another food.
- Do not invent a food name.
- Do not return duplicate names.
- Use one record per requested name.
- Keep every schema field.
- Preserve data types.
- Nutrition values are synthetic test values.
- Return ONLY JSON.
- If a requested name is genuinely unsuitable as a food
  dish, omit it rather than inventing a replacement.

Return:

{{
    "foods": [
        ...
    ]
}}
"""

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.7,
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
                "content": prompt
            }
        ]
    )

    content = (
        response.choices[0]
        .message
        .content
    )

    if not content:
        return []

    data = json.loads(content)

    foods = data.get(
        "foods",
        []
    )

    if not isinstance(foods, list):
        return []

    return [
        food
        for food in foods
        if isinstance(food, dict)
    ]


# ============================================================
# VALIDATION
# ============================================================

def validate_record(
    record: dict[str, Any],
    reference_keys: set[str]
) -> tuple[bool, str]:

    if not isinstance(record, dict):
        return False, "Not a JSON object."

    keys = set(
        record.keys()
    )

    if keys != reference_keys:

        missing = reference_keys - keys
        extra = keys - reference_keys

        return False, (
            f"Schema mismatch. "
            f"Missing={missing}, "
            f"Extra={extra}"
        )

    name = record.get(
        "name"
    )

    if not isinstance(name, str):
        return False, "Invalid name."

    if not name.strip():
        return False, "Empty name."

    return True, ""


# ============================================================
# ADD TEST METADATA
# ============================================================

def prepare_test_record(
    record: dict[str, Any]
) -> dict[str, Any]:

    record = record.copy()

    # Python owns synthetic IDs.
    record["food_id"] = (
        f"test-{uuid.uuid4().hex[:12]}"
    )

    # NOTE:
    # Do not add data_source/test_data here because the
    # existing Kalnur schema does not contain those fields.
    # We want the generated records to remain schema-compatible.

    return record


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 65)
    print("KALNUR SMART TEST FOOD GENERATOR")
    print("=" * 65)

    print(
        f"\nSource:\n{SOURCE_FILE}"
    )

    print(
        f"Output:\n{OUTPUT_FILE}"
    )

    print(
        f"Cache:\n{CACHE_DB}"
    )

    print(
        f"\nTarget records: {TARGET_RECORDS}"
    )

    print(
        f"Name model: {NAME_MODEL}"
    )

    print(
        f"Record model: {MODEL}"
    )

    print(
        f"Candidate batch: {NAME_BATCH_SIZE}"
    )

    print(
        f"Record batch: {RECORD_BATCH_SIZE}"
    )

    # --------------------------------------------------------
    # Load original 134 foods.
    # --------------------------------------------------------

    source_records = load_food_file(
        SOURCE_FILE
    )

    print(
        f"\nLoaded {len(source_records)} "
        f"original Kalnur records."
    )

    if len(source_records) >= TARGET_RECORDS:

        raise ValueError(
            f"Source already contains "
            f"{len(source_records)} records."
        )

    # --------------------------------------------------------
    # Schema
    # --------------------------------------------------------

    schema = inspect_schema(
        source_records
    )

    reference_keys = set(
        source_records[0].keys()
    )

    print("\nDetected schema:")

    for key in sorted(
        reference_keys
    ):

        print(
            f"  - {key}"
        )

    # --------------------------------------------------------
    # Cache
    # --------------------------------------------------------

    conn = init_cache()

    # --------------------------------------------------------
    # Load checkpoint.
    #
    # If the checkpoint does not exist, immediately create it
    # with the original 134 records.
    # --------------------------------------------------------

    temp_file = OUTPUT_FILE.with_suffix(".tmp")
    current_records = []

    if OUTPUT_FILE.exists():
        try:
            current_records = load_food_file(
                OUTPUT_FILE
            )
        except Exception:
            pass

    if temp_file.exists():
        try:
            tmp_records = load_food_file(
                temp_file
            )
            if len(tmp_records) > len(current_records):
                current_records = tmp_records
                save_checkpoint(
                    current_records
                )
        except Exception:
            pass

    if current_records:
        print(
            f"\nCheckpoint found: "
            f"{len(current_records)} records."
        )
    else:
        current_records = (
            source_records.copy()
        )

        save_checkpoint(
            current_records
        )

        print(
            "\nNo checkpoint found."
        )

        print(
            "Created safe starting checkpoint "
            f"with {len(current_records)} records."
        )

    # Never allow a checkpoint to lose the original 134.
    if len(current_records) < len(source_records):

        print(
            "\nCheckpoint contains fewer records "
            "than the source."
        )

        print(
            "Restoring the original source as the base."
        )

        current_records = (
            source_records.copy()
        )

        save_checkpoint(
            current_records
        )

    # --------------------------------------------------------
    # Build name set and cache.
    # --------------------------------------------------------

    used_names = set()

    for record in current_records:

        name = record.get(
            "name"
        )

        normalized = normalize_name(
            name
        )

        if normalized:

            used_names.add(
                normalized
            )

            cache_name(
                conn,
                name,
                "existing_or_generated"
            )

    # --------------------------------------------------------
    # Examples and system prompt.
    # --------------------------------------------------------

    examples = build_examples(
        source_records,
        count=3
    )

    system_prompt = build_system_prompt(
        schema
    )

    print(
        f"\nCurrent progress: "
        f"{len(current_records)}/{TARGET_RECORDS}"
    )

    print(
        f"Need: "
        f"{TARGET_RECORDS - len(current_records)} "
        f"more foods."
    )

    attempts = 0

    # ========================================================
    # GENERATION LOOP
    # ========================================================

    while len(current_records) < TARGET_RECORDS:

        attempts += 1

        if attempts > MAX_ATTEMPTS:

            print(
                "\nMaximum attempts reached."
            )

            print(
                f"SAFE CHECKPOINT: "
                f"{len(current_records)}/"
                f"{TARGET_RECORDS}"
            )

            print(
                "Run the script again to resume."
            )

            return

        remaining = (
            TARGET_RECORDS
            - len(current_records)
        )

        print(
            "\n" + "-" * 65
        )

        print(
            f"Attempt {attempts}"
        )

        print(
            f"Progress: "
            f"{len(current_records)}/"
            f"{TARGET_RECORDS}"
        )

        # ----------------------------------------------------
        # STEP 1 — CHEAP candidate names.
        # ----------------------------------------------------

        print(
            f"\nGenerating up to "
            f"{NAME_BATCH_SIZE} candidate names..."
        )

        try:

            candidate_names = (
                generate_candidate_names(
                    existing_names=used_names,
                    count=NAME_BATCH_SIZE
                )
            )

        except KeyboardInterrupt:

            print(
                "\nStopped by user."
            )

            print(
                f"SAFE CHECKPOINT: "
                f"{len(current_records)}/"
                f"{TARGET_RECORDS}"
            )

            return

        except Exception as exc:

            print(
                "\nCandidate generation error:"
            )

            print(
                f"{type(exc).__name__}: {exc}"
            )

            time.sleep(3)
            continue

        # ----------------------------------------------------
        # STEP 2 — LOCAL CACHE FILTER.
        #
        # This happens BEFORE the expensive full-record call.
        # ----------------------------------------------------

        unique_candidates = []

        for name in candidate_names:

            normalized = normalize_name(
                name
            )

            if not normalized:
                continue

            if (
                normalized in used_names
                or cache_exists(conn, name)
            ):

                print(
                    f"  CACHE HIT / DUPLICATE SKIP: "
                    f"{name}"
                )

                cache_name(
                    conn,
                    name,
                    "duplicate"
                )

                continue

            if normalized in {
                normalize_name(x)
                for x in unique_candidates
            }:

                print(
                    f"  BATCH DUPLICATE SKIP: "
                    f"{name}"
                )

                continue

            unique_candidates.append(
                name
            )

            # Reserve locally.
            cache_name(
                conn,
                name,
                "candidate"
            )

            if len(unique_candidates) >= min(
                RECORD_BATCH_SIZE,
                remaining
            ):

                break

        if not unique_candidates:

            print(
                "\nNo new candidates survived "
                "the cache."
            )

            continue

        print(
            "\nUnique names going to the "
            "EXPENSIVE full-record call:"
        )

        for name in unique_candidates:

            print(
                f"  + {name}"
            )

        # ----------------------------------------------------
        # STEP 3 — EXPENSIVE full records.
        # ----------------------------------------------------

        try:

            batch = generate_full_records(
                names=unique_candidates,
                system_prompt=system_prompt,
                examples=examples
            )

        except KeyboardInterrupt:

            print(
                "\nStopped by user."
            )

            print(
                f"SAFE CHECKPOINT: "
                f"{len(current_records)}/"
                f"{TARGET_RECORDS}"
            )

            return

        except Exception as exc:

            print(
                "\nFull-record generation error:"
            )

            print(
                f"{type(exc).__name__}: {exc}"
            )

            # Candidate names were not successfully enriched.
            # They are NOT treated as completed.
            time.sleep(3)
            continue

        print(
            f"\nOpenAI returned "
            f"{len(batch)} record(s)."
        )

        # ----------------------------------------------------
        # STEP 4 — Validate and save each record immediately.
        # ----------------------------------------------------

        accepted_this_round = 0

        for record in batch:

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

            display_name = record["name"]

            normalized = normalize_name(
                display_name
            )

            # This is the final local safety gate.
            if normalized in used_names:

                print(
                    f"  DUPLICATE RETURNED: "
                    f"{display_name}"
                )

                cache_name(
                    conn,
                    display_name,
                    "duplicate"
                )

                continue

            # Only now reserve it as generated.
            used_names.add(
                normalized
            )

            cache_name(
                conn,
                display_name,
                "generated"
            )

            test_record = (
                prepare_test_record(
                    record
                )
            )

            current_records.append(
                test_record
            )

            # ------------------------------------------------
            # CRITICAL CHECKPOINT:
            # save immediately after ONE successful record.
            # ------------------------------------------------

            save_checkpoint(
                current_records
            )

            accepted_this_round += 1

            print(
                f"  SAVED: "
                f"{display_name} "
                f"→ {len(current_records)}/"
                f"{TARGET_RECORDS}"
            )

            if (
                len(current_records)
                >= TARGET_RECORDS
            ):

                break

        print(
            f"\nAccepted this round: "
            f"{accepted_this_round}"
        )

        print(
            f"Total saved: "
            f"{len(current_records)}/"
            f"{TARGET_RECORDS}"
        )

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    # ========================================================
    # FINAL VERIFICATION
    # ========================================================

    if len(current_records) != TARGET_RECORDS:

        raise RuntimeError(
            f"Expected {TARGET_RECORDS} "
            f"records but got "
            f"{len(current_records)}."
        )

    # Final duplicate check.
    final_names = []

    for record in current_records:

        normalized = normalize_name(
            record.get("name")
        )

        if normalized:
            final_names.append(
                normalized
            )

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

    # Final safe write.
    save_checkpoint(
        current_records
    )

    print(
        "\n" + "=" * 65
    )

    print(
        "SUCCESS"
    )

    print(
        "=" * 65
    )

    print(
        f"Original Kalnur records: "
        f"{len(source_records)}"
    )

    print(
        f"Generated test records: "
        f"{len(current_records) - len(source_records)}"
    )

    print(
        f"Final records: "
        f"{len(current_records)}"
    )

    print(
        f"\nOutput:\n{OUTPUT_FILE}"
    )

    print(
        f"\nCache:\n{CACHE_DB}"
    )

    print(
        "\nThe 500-record test dataset is ready."
    )


if __name__ == "__main__":
    main()

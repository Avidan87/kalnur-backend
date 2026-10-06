"""
Append new foods batch to the main JSONL knowledge base.
Creates a backup before modifying.
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

JSONL_PATH = Path(__file__).resolve().parent.parent / "knowledge-base" / "data" / "processed" / "nigerian_foods_v2_improved.jsonl"
BATCH_PATH = Path(__file__).resolve().parent.parent / "knowledge-base" / "data" / "processed" / "new_foods_batch.jsonl"


def main():
    if not BATCH_PATH.exists():
        print("No batch file found. Run add_new_foods.py first.")
        return

    # Load existing
    existing = []
    existing_ids = set()
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            food = json.loads(line)
            existing.append(food)
            existing_ids.add(food["id"])

    # Load new batch
    new_foods = []
    with open(BATCH_PATH, "r", encoding="utf-8") as f:
        for line in f:
            food = json.loads(line)
            if food["id"] not in existing_ids:
                new_foods.append(food)
            else:
                print(f"  Skipping duplicate: {food['name']} ({food['id']})")

    if not new_foods:
        print("No new foods to add.")
        return

    # Backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = JSONL_PATH.with_suffix(f".backup_{timestamp}.jsonl")
    shutil.copy2(JSONL_PATH, backup_path)
    print(f"Backup created: {backup_path}")

    # Append
    with open(JSONL_PATH, "a", encoding="utf-8") as f:
        for food in new_foods:
            f.write(json.dumps(food, ensure_ascii=False) + "\n")

    total = len(existing) + len(new_foods)
    print(f"\nAdded {len(new_foods)} new foods")
    print(f"Total foods in knowledge base: {total}")
    print(f"\nNext: python reinitialize_chromadb.py")


if __name__ == "__main__":
    main()

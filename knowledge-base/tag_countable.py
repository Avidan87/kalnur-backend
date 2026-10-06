"""
tag_countable.py — Auto-classify countable flag for Nigerian foods

Run this script whenever you add new foods to the JSONL database.
It finds all foods missing the "countable" flag, asks GPT-4o to classify
each one, and writes the result back permanently.

Usage:
    python knowledge-base/tag_countable.py

Requirements:
    - OPENAI_API_KEY in .env
    - nigerian_foods_v2_improved.jsonl already has food entries

What "countable" means:
    True  → discrete items you count individually (slices, pieces, balls, whole fish, eggs)
    False → volume/scoopable foods you measure by portion size (rice, soup, porridge, stew)
"""

import json
import os
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

JSONL_PATH = Path(__file__).parent / "data" / "processed" / "nigerian_foods_v2_improved.jsonl"


def classify_countable(client: OpenAI, food_name: str, category: str, description: str) -> bool:
    """
    Ask GPT-4o to determine if a food is a discrete countable item.

    Returns True if the food is countable (slices, pieces, whole items),
    False if it is volume/scoopable (rice, soup, porridge, stew, etc.).
    """
    prompt = f"""You are classifying Nigerian foods as "countable" or "volume" for a nutrition tracking app.

COUNTABLE = discrete items a user counts individually before eating:
- Examples: bread slices, eggs, pieces of chicken, whole fish, akara balls, puff puff, meat pies, corn cobs, suya sticks
- Key test: Can you say "I ate 2 of them"? → countable

VOLUME = foods measured by portion/scoop, not counted individually:
- Examples: rice, soup, porridge, eba, stew, beans, yogurt, juice, vegetables in a salad
- Key test: You scoop or pour it, not count it → volume

Food to classify:
- Name: {food_name}
- Category: {category}
- Description: {description}

Reply with ONLY "true" or "false". No explanation.
true = countable (discrete items)
false = volume (scoopable/pourable)"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=5
    )
    answer = response.choices[0].message.content.strip().lower()
    return answer == "true"


def run():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in .env")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    # Load all foods
    foods = []
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                foods.append(json.loads(line))

    # Find foods missing the countable flag
    to_classify = [f for f in foods if "countable" not in f]

    if not to_classify:
        print(f"All {len(foods)} foods already have the countable flag. Nothing to do.")
        return

    print(f"Found {len(to_classify)} foods missing 'countable' flag. Classifying...\n")

    # Classify each one
    results = {}
    for food in to_classify:
        name = food["name"]
        category = food.get("category", "unknown")
        description = food.get("description", "")

        countable = classify_countable(client, name, category, description)
        results[name] = countable
        status = "countable" if countable else "volume"
        print(f"  {name} ({category}) -> {status}")

    # Write back to JSONL
    updated_foods = []
    for food in foods:
        if food["name"] in results:
            food["countable"] = results[food["name"]]
        updated_foods.append(json.dumps(food, ensure_ascii=False))

    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(updated_foods) + "\n")

    countable_count = sum(1 for v in results.values() if v)
    volume_count = sum(1 for v in results.values() if not v)
    print(f"\nDone! Tagged {len(results)} foods: {countable_count} countable, {volume_count} volume.")
    print(f"Updated: {JSONL_PATH}")


if __name__ == "__main__":
    run()

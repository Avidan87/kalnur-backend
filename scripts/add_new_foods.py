"""
Add New Nigerian Foods to Knowledge Base
Uses GPT-4o with web-grounded research prompting for accurate nutrient data.
Outputs entries matching the exact nigerian_foods_v2_improved.jsonl schema.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# === CONFIG ===
JSONL_PATH = Path(__file__).resolve().parent.parent / "knowledge-base" / "data" / "processed" / "nigerian_foods_v2_improved.jsonl"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "knowledge-base" / "data" / "processed" / "new_foods_batch.jsonl"

# 15 new Nigerian dishes to add
NEW_DISHES = [
    "Yam Porridge (Asaro)",
    "Beans Porridge (Ewa Riro)",
    "Masa (Northern Rice Cakes)",
    "Oha Soup",
    "Potato Porridge",
    "Meat Pie",
    "Egg Roll",
    "Pap (Ogi/Akamu)",
    "Custard (Nigerian Style)",
    "Soaked Garri with Groundnut",
    "Plantain Porridge",
    "Boiled Corn & Pear (Ube)",
    "Sausage Roll",
    "Peppered Ponmo",
    "Roasted Corn (Agbado)",
]

# All 16 tracked nutrients
TRACKED_NUTRIENTS = [
    "calories", "protein", "carbohydrates", "fat", "fiber",
    "iron", "calcium", "zinc", "potassium", "sodium", "magnesium",
    "vitamin_a", "vitamin_c", "vitamin_d", "vitamin_b12", "folate",
]

# Valid categories in the existing database
VALID_CATEGORIES = [
    "starch", "protein", "protein_dish", "soup", "swallow",
    "vegetable", "fruit", "snack", "beverage", "condiment",
]

# Nutrient sanity ranges (per 100g)
NUTRIENT_RANGES = {
    "calories": (0, 700),
    "protein": (0, 60),
    "carbohydrates": (0, 85),
    "fat": (0, 60),
    "fiber": (0, 30),
    "iron": (0, 20),
    "calcium": (0, 500),
    "zinc": (0, 15),
    "potassium": (0, 1500),
    "sodium": (0, 1500),
    "magnesium": (0, 300),
    "vitamin_a": (0, 2000),
    "vitamin_c": (0, 100),
    "vitamin_d": (0, 30),
    "vitamin_b12": (0, 10),
    "folate": (0, 500),
}


SYSTEM_PROMPT = """You are a Nigerian food nutrition scientist with access to USDA FoodData Central,
West African Food Composition Table (WAFCT), Nigerian Food Composition Table (NFCT), and FitNigerian.com data.

Your task: provide ACCURATE nutrition data per 100g for Nigerian dishes.

ACCURACY RULES:
1. For simple ingredients (corn, yam, beans): use USDA FoodData Central values directly
2. For Nigerian dishes: mentally decompose into ingredients, calculate weighted average per 100g
3. For fried foods: account for oil absorption (typically 10-15% of weight)
4. For soups/stews: account for water content reducing nutrient density
5. NEVER guess - if truly uncertain, use conservative middle estimates
6. Cross-reference: values should be consistent (e.g., calories ≈ protein*4 + carbs*4 + fat*9)

CRITICAL: All nutrient values must be PER 100 GRAMS of the prepared/served food."""


def get_extraction_prompt(dish_name: str) -> str:
    return f"""Research and provide accurate nutrition data for this Nigerian dish: "{dish_name}"

STEP 1 - Identify the dish:
- What exactly is this dish? How is it prepared in Nigeria?
- What are the key ingredients and their approximate proportions?

STEP 2 - Calculate nutrients per 100g:
- For each ingredient, use known USDA/WAFCT values
- Calculate the weighted average based on typical recipe proportions
- Account for cooking method (frying adds fat, boiling adds water)

STEP 3 - Physical properties:
- density_g_per_ml: how dense is this food? (water=1.0, bread~0.35, rice~0.85, soup~1.0)
- typical_height_cm: when served on a plate, how tall is a typical portion?

STEP 4 - Return this EXACT JSON structure (no markdown, no explanation):
{{
    "id": "lowercase_underscore_id",
    "name": "{dish_name}",
    "aliases": ["alias1", "alias2", "alias3"],
    "category": "starch|protein|protein_dish|soup|swallow|vegetable|fruit|snack|beverage|condiment",
    "description": "Brief 1-2 sentence description of the Nigerian dish",
    "nutrients_per_100g": {{
        "calories": 0.0,
        "protein": 0.0,
        "carbohydrates": 0.0,
        "fat": 0.0,
        "fiber": 0.0,
        "iron": 0.0,
        "calcium": 0.0,
        "zinc": 0.0,
        "potassium": 0.0,
        "sodium": 0.0,
        "magnesium": 0.0,
        "vitamin_a": 0.0,
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 0.0
    }},
    "density_g_per_ml": 0.0,
    "typical_height_cm": 0.0,
    "preparation_method": "boiled|fried|grilled|roasted|baked|steamed|soaked|raw|cooked",
    "common_servings": {{
        "typical_portion_g": 0,
        "min_reasonable_g": 0,
        "max_reasonable_g": 0
    }},
    "sources": [
        {{"name": "Source name and what it covers", "url": "https://...", "confidence": "high|medium"}},
        {{"name": "Second source", "url": "https://...", "confidence": "high|medium"}}
    ],
    "data_confidence": "high|medium",
    "confidence_notes": "Explain how you derived the values and what sources you used"
}}

RETURN ONLY THE JSON. No markdown. No explanation outside the JSON."""


def validate_food_entry(food: Dict[str, Any], dish_name: str) -> List[str]:
    """Validate a food entry against schema and nutrient ranges. Returns list of issues."""
    issues = []

    # Required fields
    required = ["id", "name", "aliases", "category", "description",
                "nutrients_per_100g", "density_g_per_ml", "typical_height_cm",
                "preparation_method", "common_servings", "sources",
                "data_confidence", "confidence_notes"]

    for field in required:
        if field not in food:
            issues.append(f"Missing required field: {field}")

    # Category check
    if food.get("category") not in VALID_CATEGORIES:
        issues.append(f"Invalid category: {food.get('category')} (valid: {VALID_CATEGORIES})")

    # Nutrient validation
    nutrients = food.get("nutrients_per_100g", {})
    for nutrient in TRACKED_NUTRIENTS:
        val = nutrients.get(nutrient)
        if val is None:
            issues.append(f"Missing nutrient: {nutrient}")
            continue
        if not isinstance(val, (int, float)):
            issues.append(f"Non-numeric {nutrient}: {val}")
            continue

        lo, hi = NUTRIENT_RANGES[nutrient]
        if not (lo <= val <= hi):
            issues.append(f"Out of range {nutrient}={val} (expected {lo}-{hi})")

    # Calorie cross-check: calories should roughly equal P*4 + C*4 + F*9
    p = nutrients.get("protein", 0)
    c = nutrients.get("carbohydrates", 0)
    f = nutrients.get("fat", 0)
    expected_cal = p * 4 + c * 4 + f * 9
    actual_cal = nutrients.get("calories", 0)
    if expected_cal > 0 and actual_cal > 0:
        ratio = actual_cal / expected_cal
        if ratio < 0.7 or ratio > 1.4:
            issues.append(f"Calorie mismatch: {actual_cal} vs estimated {expected_cal:.0f} (P*4+C*4+F*9)")

    # Serving size checks
    servings = food.get("common_servings", {})
    typical = servings.get("typical_portion_g", 0)
    min_g = servings.get("min_reasonable_g", 0)
    max_g = servings.get("max_reasonable_g", 0)
    if not (0 < min_g < typical < max_g < 2000):
        issues.append(f"Serving sizes inconsistent: min={min_g}, typical={typical}, max={max_g}")

    # Density check
    density = food.get("density_g_per_ml", 0)
    if not (0.2 <= density <= 1.5):
        issues.append(f"Unusual density: {density}")

    return issues


def extract_food_data(client: OpenAI, dish_name: str, attempt: int = 1) -> Optional[Dict[str, Any]]:
    """Extract food data using GPT-4o with validation and retry."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": get_extraction_prompt(dish_name)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,  # Low temperature for factual accuracy
        )

        content = response.choices[0].message.content
        if not content:
            print(f"    Empty response for {dish_name}")
            return None

        food = json.loads(content)

        # Validate
        issues = validate_food_entry(food, dish_name)

        if issues:
            print(f"    Validation issues (attempt {attempt}):")
            for issue in issues:
                print(f"      - {issue}")

            if attempt < 2:
                print(f"    Retrying {dish_name}...")
                time.sleep(1)
                return extract_food_data(client, dish_name, attempt + 1)
            else:
                print(f"    Accepting with warnings after {attempt} attempts")

        return food

    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"    Error: {e}")
        return None


def load_existing_ids() -> set:
    """Load existing food IDs to prevent duplicates."""
    ids = set()
    if JSONL_PATH.exists():
        with open(JSONL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    food = json.loads(line)
                    ids.add(food["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return ids


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in environment")

    client = OpenAI(api_key=api_key)
    existing_ids = load_existing_ids()

    print(f"\n{'='*60}")
    print(f"ADDING {len(NEW_DISHES)} NEW NIGERIAN FOODS")
    print(f"{'='*60}")
    print(f"Existing foods: {len(existing_ids)}")
    print(f"New dishes to add: {len(NEW_DISHES)}")
    print(f"Target total: {len(existing_ids) + len(NEW_DISHES)}")
    print(f"{'='*60}\n")

    new_foods = []
    failed = []

    for i, dish in enumerate(NEW_DISHES, 1):
        print(f"[{i}/{len(NEW_DISHES)}] Extracting: {dish}...")

        food = extract_food_data(client, dish)

        if food:
            # Check for ID collision
            if food["id"] in existing_ids:
                print(f"    ID collision: {food['id']} already exists, adding suffix")
                food["id"] = food["id"] + "_v2"

            new_foods.append(food)
            existing_ids.add(food["id"])
            print(f"    OK: {food['name']} ({food['category']}) - {food['nutrients_per_100g']['calories']} cal/100g")
        else:
            failed.append(dish)
            print(f"    FAILED: {dish}")

        # Rate limit
        time.sleep(0.5)

    # Save new foods to batch file
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for food in new_foods:
            f.write(json.dumps(food, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"Successful: {len(new_foods)}/{len(NEW_DISHES)}")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print(f"Saved to: {OUTPUT_PATH}")

    # Summary table
    print(f"\n{'='*60}")
    print(f"{'Name':<35} {'Cat':<12} {'Cal':>5} {'Pro':>5} {'Carb':>5} {'Fat':>5}")
    print(f"{'-'*35} {'-'*12} {'-'*5} {'-'*5} {'-'*5} {'-'*5}")
    for food in new_foods:
        n = food["nutrients_per_100g"]
        print(f"{food['name']:<35} {food['category']:<12} {n['calories']:>5.0f} {n['protein']:>5.1f} {n['carbohydrates']:>5.1f} {n['fat']:>5.1f}")

    # Prompt to append
    print(f"\n{'='*60}")
    print("NEXT STEPS:")
    print(f"  1. Review {OUTPUT_PATH}")
    print(f"  2. Run: python scripts/append_new_foods.py")
    print(f"  3. Run: python reinitialize_chromadb.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

"""
Enrich Nigerian Foods JSONL with 8 New Nutrients

This script adds the following nutrients to each food entry:
- fiber (g)
- sodium (mg)
- magnesium (mg)
- vitamin_a (mcg RAE)
- vitamin_c (mg)
- vitamin_d (mcg)
- vitamin_b12 (mcg)
- folate (mcg DFE)

Usage:
    python scripts/enrich_jsonl_with_nutrients.py

This will:
1. Read the existing JSONL
2. Add new nutrients from research data
3. Create a backup of the original
4. Write the enriched JSONL
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
import sys

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))
from nutrient_research_data import NUTRIENT_DATA


def enrich_jsonl():
    """Enrich the JSONL file with new nutrients."""

    # Paths
    jsonl_path = Path("knowledge-base/data/processed/nigerian_foods_v2_improved.jsonl")
    backup_path = jsonl_path.with_suffix(
        f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )

    # Verify source exists
    if not jsonl_path.exists():
        print(f"ERROR: Source file not found: {jsonl_path}")
        return False

    # Create backup
    print(f"Creating backup: {backup_path.name}")
    shutil.copy(jsonl_path, backup_path)

    # Read and enrich
    enriched_foods = []
    missing_data = []

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            food = json.loads(line.strip())
            food_id = food['id']

            # Get new nutrient data
            new_nutrients = NUTRIENT_DATA.get(food_id)

            if new_nutrients is None:
                missing_data.append(food_id)
                print(f"  WARNING: No nutrient data for '{food_id}'")
                # Add zeros as placeholder
                new_nutrients = {
                    "fiber": 0.0,
                    "sodium": 0.0,
                    "magnesium": 0.0,
                    "vitamin_a": 0.0,
                    "vitamin_c": 0.0,
                    "vitamin_d": 0.0,
                    "vitamin_b12": 0.0,
                    "folate": 0.0
                }

            # Add new nutrients to existing nutrients_per_100g
            food['nutrients_per_100g'].update(new_nutrients)

            enriched_foods.append(food)

    # Write enriched JSONL
    print(f"\nWriting enriched JSONL with {len(enriched_foods)} foods...")
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for food in enriched_foods:
            f.write(json.dumps(food, ensure_ascii=False) + '\n')

    # Summary
    print("\n" + "=" * 50)
    print("ENRICHMENT COMPLETE")
    print("=" * 50)
    print(f"Total foods processed: {len(enriched_foods)}")
    print(f"Foods with nutrient data: {len(enriched_foods) - len(missing_data)}")

    if missing_data:
        print(f"Foods missing data (zeros added): {len(missing_data)}")
        for fid in missing_data:
            print(f"  - {fid}")

    # Verify the new structure
    print("\nVerifying enriched data...")
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        first_food = json.loads(f.readline())
        nutrients = list(first_food['nutrients_per_100g'].keys())
        print(f"Nutrients now tracked ({len(nutrients)}): {nutrients}")

    return True


def verify_enrichment():
    """Verify the enrichment was successful."""
    jsonl_path = Path("knowledge-base/data/processed/nigerian_foods_v2_improved.jsonl")

    required_nutrients = [
        # Original 8
        "calories", "protein", "carbohydrates", "fat",
        "iron", "calcium", "zinc", "potassium",
        # New 8
        "fiber", "sodium", "magnesium", "vitamin_a",
        "vitamin_c", "vitamin_d", "vitamin_b12", "folate"
    ]

    errors = []

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            food = json.loads(line.strip())
            food_id = food['id']
            nutrients = food.get('nutrients_per_100g', {})

            missing = [n for n in required_nutrients if n not in nutrients]
            if missing:
                errors.append(f"{food_id}: missing {missing}")

    if errors:
        print("VERIFICATION FAILED:")
        for err in errors[:10]:  # Show first 10
            print(f"  {err}")
        return False

    print(f"VERIFICATION PASSED: All 75 foods have all 16 nutrients!")
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("NIGERIAN FOODS NUTRIENT ENRICHMENT")
    print("Adding 8 new nutrients to 75 foods")
    print("=" * 50 + "\n")

    success = enrich_jsonl()

    if success:
        print("\n" + "-" * 50)
        verify_enrichment()

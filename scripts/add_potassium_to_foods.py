"""
Add Potassium to Nigerian Food Database

This script updates nigerian_foods_v2_improved.jsonl to:
1. Add potassium values (using USDA API + GPT-4o fallback)
2. Remove vitamin_a values

Hybrid approach:
- USDA API for foods with USDA sources (most accurate)
- GPT-4o for Nigerian-specific foods (smart estimates)
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
import requests
from openai import OpenAI
from dotenv import load_dotenv

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# USDA FoodData Central API (free, no key required for basic searches)
USDA_API_BASE = "https://api.nal.usda.gov/fdc/v1"
USDA_API_KEY = os.environ.get("USDA_API_KEY", "DEMO_KEY")  # Optional: get key from https://fdc.nal.usda.gov/api-key-signup.html


def get_potassium_from_usda(food_name: str) -> Optional[float]:
    """
    Fetch potassium content from USDA FoodData Central API.

    Args:
        food_name: Name of the food to search

    Returns:
        Potassium content in mg per 100g, or None if not found
    """
    try:
        # Search for food
        search_url = f"{USDA_API_BASE}/foods/search"
        params = {
            "query": food_name,
            "api_key": USDA_API_KEY,
            "pageSize": 5
        }

        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get("foods"):
            return None

        # Get first result (most relevant)
        food = data["foods"][0]

        # Find potassium nutrient (nutrient ID: 306)
        for nutrient in food.get("foodNutrients", []):
            if nutrient.get("nutrientId") == 306:  # Potassium
                # USDA returns per 100g by default
                value = nutrient.get("value", 0)
                print(f"  ✓ USDA: {food_name} → {value} mg potassium/100g")
                return float(value)

        return None

    except Exception as e:
        print(f"  ✗ USDA API error for {food_name}: {e}")
        return None


def get_potassium_from_gpt(food_name: str, food_data: Dict[str, Any]) -> float:
    """
    Use GPT-4o to estimate potassium content for Nigerian-specific foods.

    Args:
        food_name: Name of the food
        food_data: Full food data including description, category, etc.

    Returns:
        Estimated potassium content in mg per 100g
    """
    try:
        description = food_data.get("description", "")
        category = food_data.get("category", "")

        prompt = f"""You are a nutrition expert specializing in Nigerian cuisine.

Food: {food_name}
Category: {category}
Description: {description}

Based on typical ingredients and preparation methods for this Nigerian food, estimate the potassium content per 100g in milligrams (mg).

Consider:
- Main ingredients (e.g., plantains are high in potassium ~500mg/100g, yams ~800mg/100g, leafy greens ~500mg/100g)
- Cooking method (boiling/frying doesn't significantly change potassium)
- Typical recipe proportions

Respond with ONLY a number (the mg of potassium per 100g). No explanation, just the number.
Example: 450
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Cheaper model for estimates
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Low temp for consistent estimates
            max_tokens=10
        )

        potassium_str = response.choices[0].message.content.strip()
        potassium = float(potassium_str)

        print(f"  ✓ GPT-4o: {food_name} → {potassium} mg potassium/100g (estimated)")
        return potassium

    except Exception as e:
        print(f"  ✗ GPT-4o error for {food_name}: {e}")
        # Fallback: reasonable default based on food category
        defaults = {
            "starch": 300,  # Average for starchy foods
            "protein_dish": 250,  # Average for protein dishes
            "soup": 400,  # Soups often have vegetables (higher K+)
            "vegetable": 500,  # Vegetables are high in potassium
        }
        return defaults.get(food_data.get("category", ""), 300)


def update_food_with_potassium(food: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a single food entry: add potassium, remove vitamin_a.

    Args:
        food: Food data dictionary

    Returns:
        Updated food dictionary
    """
    food_name = food.get("name", "Unknown")
    print(f"\n🔄 Processing: {food_name}")

    # Check if food has USDA source
    sources = food.get("sources", [])
    has_usda = any("USDA" in str(source) or "usda" in str(source) for source in sources)

    # Try USDA first if available
    potassium = None
    if has_usda:
        potassium = get_potassium_from_usda(food_name)
        time.sleep(0.5)  # Rate limiting for USDA API

    # Fallback to GPT if USDA fails
    if potassium is None:
        potassium = get_potassium_from_gpt(food_name, food)
        time.sleep(0.3)  # Rate limiting for OpenAI

    # Update nutrients
    if "nutrients_per_100g" not in food:
        food["nutrients_per_100g"] = {}

    food["nutrients_per_100g"]["potassium"] = potassium

    # Remove vitamin_a
    if "vitamin_a" in food["nutrients_per_100g"]:
        del food["nutrients_per_100g"]["vitamin_a"]

    return food


def main():
    """Main execution function"""

    print("=" * 60)
    print("🥔 Adding Potassium to Nigerian Food Database")
    print("=" * 60)

    # Input/output paths
    input_path = Path("knowledge-base/data/processed/nigerian_foods_v2_improved.jsonl")
    output_path = Path("knowledge-base/data/processed/nigerian_foods_v2_improved_with_potassium.jsonl")

    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)

    # Read all foods
    foods = []
    print(f"\n📖 Reading foods from: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                foods.append(json.loads(line))

    print(f"✓ Loaded {len(foods)} foods")

    # Process each food
    print(f"\n🔄 Processing {len(foods)} foods...")
    print("=" * 60)

    usda_count = 0
    gpt_count = 0

    updated_foods = []
    for i, food in enumerate(foods, 1):
        print(f"\n[{i}/{len(foods)}]", end=" ")

        # Track source used
        sources_before = food.get("sources", [])
        has_usda = any("USDA" in str(source) or "usda" in str(source) for source in sources_before)

        updated_food = update_food_with_potassium(food)
        updated_foods.append(updated_food)

        # Count source used
        if has_usda and updated_food["nutrients_per_100g"].get("potassium"):
            usda_count += 1
        else:
            gpt_count += 1

    # Write updated foods to output file
    print(f"\n\n💾 Writing updated foods to: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for food in updated_foods:
            f.write(json.dumps(food, ensure_ascii=False) + '\n')

    print(f"✓ Wrote {len(updated_foods)} foods")

    # Summary
    print("\n" + "=" * 60)
    print("✅ SUMMARY")
    print("=" * 60)
    print(f"Total foods processed: {len(foods)}")
    print(f"  • USDA API (accurate):  {usda_count} foods ({usda_count/len(foods)*100:.1f}%)")
    print(f"  • GPT-4o (estimated):   {gpt_count} foods ({gpt_count/len(foods)*100:.1f}%)")
    print(f"\n📁 Output file: {output_path}")
    print(f"📁 Original file: {input_path} (unchanged)")
    print("\n✅ Done! Review the output file, then rename it to replace the original.")
    print("   Command: mv nigerian_foods_v2_improved_with_potassium.jsonl nigerian_foods_v2_improved.jsonl")


if __name__ == "__main__":
    main()

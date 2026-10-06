"""
Knowledge Base Enrichment Script

This script uses OpenAI's GPT-4o to extract, validate, and enrich Nigerian food data
from the existing knowledge base into a structured format with Pydantic validation.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


class FoodNutrients(BaseModel):
    """Validated nutrient data per 100g"""
    calories: float = Field(ge=0, le=1000, description="Calories per 100g")
    protein: float = Field(ge=0, le=100, description="Protein in grams per 100g")
    carbohydrates: float = Field(ge=0, le=100, description="Carbs in grams per 100g")
    fat: float = Field(ge=0, le=100, description="Fat in grams per 100g")
    iron: float = Field(ge=0, le=50, description="Iron in mg per 100g")
    calcium: float = Field(ge=0, le=1000, description="Calcium in mg per 100g")
    vitamin_a: float = Field(ge=0, le=5000, description="Vitamin A in mcg per 100g")
    zinc: float = Field(ge=0, le=50, description="Zinc in mg per 100g")


class EnrichedFood(BaseModel):
    """Complete food data with validation"""
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    category: str  # staple, protein, soup, vegetable, snack, drink
    region: str
    meal_types: list[str]  # breakfast, lunch, dinner, snack
    description: str
    typical_portion: str
    typical_portion_grams: float = Field(ge=0, description="Typical portion in grams")
    nutrients_per_100g: FoodNutrients
    cooking_methods: list[str]
    common_pairings: list[str]
    dietary_flags: list[str]  # vegetarian, vegan, contains_meat, contains_fish, gluten_free
    health_benefits: list[str] = Field(default_factory=list)
    cultural_significance: str
    price_tier: str = Field(default="mid", description="budget, mid, premium")
    availability: str = Field(default="widely_available", description="Availability across Nigeria")
    confidence: float = Field(ge=0, le=1)
    sources: list[str]

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid_categories = ['staple', 'protein', 'soup', 'vegetable', 'snack', 'drink', 'side_dish']
        if v.lower() not in valid_categories:
            return 'staple'  # default
        return v.lower()

    @field_validator('meal_types')
    @classmethod
    def validate_meal_types(cls, v: list[str]) -> list[str]:
        valid_types = ['breakfast', 'lunch', 'dinner', 'snack']
        return [meal.lower() for meal in v if meal.lower() in valid_types]


def enrich_food_with_llm(raw_food: dict) -> Optional[EnrichedFood]:
    """
    Use OpenAI GPT-4o to extract and validate Nigerian food data.

    Args:
        raw_food: Raw food data from existing knowledge base

    Returns:
        EnrichedFood object with validated data, or None if processing fails
    """

    # Extract existing data
    food_id = raw_food.get("id", "")
    metadata = raw_food.get("metadata", {})
    nutrients = raw_food.get("nutrients", {})
    text_description = raw_food.get("text", "")

    # Build prompt for LLM
    prompt = f"""
You are a Nigerian food nutrition expert. Extract and enhance the structured data from this Nigerian food entry.

**Existing Data:**
```json
{json.dumps(raw_food, indent=2)}
```

**Your Task:**
1. Extract accurate nutrient values PER 100G (the current data may be for typical portions, you need to convert)
2. Calculate the typical portion size in grams (e.g., "1 plate" = ~250g, "1 cup" = ~200g, "1 wrap" = ~80g)
3. Identify the food category (staple, protein, soup, vegetable, snack, drink, side_dish)
4. List common Nigerian names and aliases
5. Specify what meals this is typically eaten for
6. Identify cooking methods commonly used in Nigeria
7. List common pairings with other Nigerian foods
8. Add dietary flags (vegetarian, vegan, contains_meat, contains_fish, gluten_free, dairy_free)
9. List 2-3 key health benefits specific to Nigerians' nutrition needs
10. Describe cultural significance (when/why Nigerians eat this)
11. Estimate price tier in Nigerian markets (budget = ₦100-500, mid = ₦500-1500, premium = ₦1500+)
12. Note availability (widely_available, regional, seasonal)

**Important Conversion Notes:**
- If the existing nutrients are for a typical portion, convert to per 100g
- Example: If "1 plate (250g)" has 32.1g carbs, then per 100g = 32.1/2.5 = 12.84g
- Use your knowledge of Nigerian foods to estimate if conversion is needed

**Return Format (JSON only, no explanation):**
```json
{{
  "name": "Food Name",
  "aliases": ["alternative name 1", "alternative name 2"],
  "category": "staple|protein|soup|vegetable|snack|drink|side_dish",
  "description": "Brief 1-2 sentence description",
  "typical_portion": "1 plate (~250g)",
  "typical_portion_grams": 250.0,
  "nutrients_per_100g": {{
    "calories": 0.0,
    "protein": 0.0,
    "carbohydrates": 0.0,
    "fat": 0.0,
    "iron": 0.0,
    "calcium": 0.0,
    "vitamin_a": 0.0,
    "zinc": 0.0
  }},
  "meal_types": ["breakfast", "lunch", "dinner", "snack"],
  "cooking_methods": ["boiling", "frying", "steaming", "grilling"],
  "common_pairings": ["Food 1", "Food 2", "Food 3"],
  "dietary_flags": ["vegetarian", "contains_meat", "gluten_free"],
  "health_benefits": [
    "High in iron - supports blood health for women",
    "Rich in plant protein - aids muscle recovery",
    "Contains calcium - strengthens bones"
  ],
  "cultural_significance": "When/why Nigerians eat this food, cultural context",
  "price_tier": "budget|mid|premium",
  "availability": "widely_available|regional|seasonal",
  "confidence": 0.85,
  "sources": ["source 1", "source 2"]
}}
```

**CRITICAL**: Return ONLY the JSON, no markdown formatting, no explanation.
"""

    try:
        # Call OpenAI
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a Nigerian food nutrition expert. Extract structured nutrition data accurately. Return ONLY valid JSON, no markdown."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3  # Lower temperature for factual extraction
        )

        # Parse response
        extracted_json = response.choices[0].message.content
        extracted_data = json.loads(extracted_json)

        # Validate with Pydantic
        enriched_food = EnrichedFood(
            id=food_id,
            name=extracted_data["name"],
            aliases=extracted_data.get("aliases", []),
            category=extracted_data["category"],
            region="Nigeria",
            meal_types=extracted_data["meal_types"],
            description=extracted_data["description"],
            typical_portion=extracted_data["typical_portion"],
            typical_portion_grams=extracted_data["typical_portion_grams"],
            nutrients_per_100g=FoodNutrients(**extracted_data["nutrients_per_100g"]),
            cooking_methods=extracted_data["cooking_methods"],
            common_pairings=extracted_data["common_pairings"],
            dietary_flags=extracted_data["dietary_flags"],
            health_benefits=extracted_data.get("health_benefits", []),
            cultural_significance=extracted_data.get("cultural_significance", ""),
            price_tier=extracted_data.get("price_tier", "mid"),
            availability=extracted_data.get("availability", "widely_available"),
            confidence=extracted_data["confidence"],
            sources=extracted_data.get("sources", [])
        )

        return enriched_food

    except Exception as e:
        print(f"  ✗ Error enriching {food_id}: {e}")
        return None


def process_knowledge_base(input_file: str, output_file: str, limit: Optional[int] = None):
    """
    Process all foods in knowledge base and enrich with LLM.

    Args:
        input_file: Path to input JSONL file
        output_file: Path to output JSONL file
        limit: Optional limit on number of foods to process (for testing)
    """
    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        print(f"❌ Input file not found: {input_file}")
        return

    # Clear output file if it exists
    if output_path.exists():
        output_path.unlink()

    enriched_foods = []
    processed_count = 0
    success_count = 0

    print(f"\n🚀 Starting knowledge base enrichment...")
    print(f"📂 Input: {input_file}")
    print(f"📂 Output: {output_file}\n")

    with open(input_path) as f:
        for line_num, line in enumerate(f, 1):
            # Check limit
            if limit and processed_count >= limit:
                print(f"\n⚠️  Reached limit of {limit} foods\n")
                break

            try:
                raw_food = json.loads(line)
                food_name = raw_food.get("metadata", {}).get("name") or raw_food.get("id", "Unknown")

                print(f"[{line_num}/50] Enriching: {food_name}...")

                enriched = enrich_food_with_llm(raw_food)

                if enriched:
                    enriched_foods.append(enriched)

                    # Save incrementally
                    with open(output_path, 'a', encoding='utf-8') as out:
                        out.write(enriched.model_dump_json() + '\n')

                    print(f"  ✓ Success! Confidence: {enriched.confidence:.2f}")
                    print(f"  📊 Nutrients per 100g: {enriched.nutrients_per_100g.protein}g protein, "
                          f"{enriched.nutrients_per_100g.iron}mg iron")
                    print(f"  🏷️  Category: {enriched.category} | Price: {enriched.price_tier}")
                    success_count += 1
                else:
                    print(f"  ✗ Failed to enrich")

                processed_count += 1
                print()

            except json.JSONDecodeError as e:
                print(f"  ✗ JSON error on line {line_num}: {e}\n")
                continue
            except Exception as e:
                print(f"  ✗ Unexpected error on line {line_num}: {e}\n")
                continue

    # Summary
    print("=" * 60)
    print(f"✅ Enrichment Complete!")
    print(f"📊 Total processed: {processed_count}")
    print(f"✓  Successful: {success_count}")
    print(f"✗  Failed: {processed_count - success_count}")
    print(f"📂 Output saved to: {output_file}")
    print("=" * 60)

    # Show sample
    if enriched_foods:
        print(f"\n📋 Sample Entry: {enriched_foods[0].name}")
        print(f"   Aliases: {', '.join(enriched_foods[0].aliases[:3])}")
        print(f"   Category: {enriched_foods[0].category}")
        print(f"   Typical portion: {enriched_foods[0].typical_portion}")
        print(f"   Health benefits: {len(enriched_foods[0].health_benefits)} listed")
        print(f"   Common pairings: {', '.join(enriched_foods[0].common_pairings[:3])}")

    return enriched_foods


if __name__ == "__main__":
    # File paths
    input_file = "knowledge-base/data/processed/nigerian_llm_complete.jsonl"
    output_file = "knowledge-base/data/processed/nigerian_foods_v2_improved.jsonl"

    # Process all foods (or set limit for testing)
    # process_knowledge_base(input_file, output_file, limit=5)  # Test with 5 foods
    process_knowledge_base(input_file, output_file)  # Process all foods

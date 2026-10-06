"""
Nigerian Foods LLM Ingestion Script
Extracts structured nutrition data for Nigerian dishes using OpenAI GPT-4o-mini.
Outputs: knowledge-base/data/processed/nigerian_llm_complete.jsonl
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Tracked nutrients (7 total - removed vitamin_d as it's rarely present in Nigerian foods)
TRACKED_NUTRIENTS = [
    "protein",
    "fat",
    "carbohydrates",
    "iron",
    "calcium",
    "vitamin_a",
    "zinc",
]

# Nigerian dishes (12) - Most common and essential
NIGERIAN_DISHES = [
    "Jollof Rice",
    "Egusi Soup",
    "Pounded Yam",
    "Fufu",
    "Suya",
    "Moi Moi",
    "Pepper Soup",
    "Akara",
    "Efo Riro",
    "Ewa Agoyin",
    "Okra Soup",
    "Ogbono Soup",
]

# Global/common staples (8) - Most frequently consumed
GLOBAL_STAPLES = [
    "Rice & Stew",
    "Beans & Stew",
    "Eba (Garri)",
    "Fried Plantain",
    "Chicken Stew",
    "Fish Stew",
    "Bread & Eggs",
    "Pap (Ogi/Akamu)",
]

SYSTEM_PROMPT = """You are a nutrition data extraction assistant specializing in Nigerian foods.

Your task is to extract structured nutrition data into strict JSON matching the provided schema.

Rules:
- If a value is unknown, set it to null. Never invent numbers.
- Units: protein, fat, carbohydrates in g/100 g; iron, calcium, zinc in mg/100 g; vitamin_a in µg/100 g.
- If you encounter IU units: Vitamin A: IU × 0.3 = µg.
- Include at least 1-2 credible sources (government, NGO, encyclopedic).
- Output ONLY valid JSON. No additional text or explanation.

Schema:
{
  "id": "string (lowercase-hyphenated)",
  "metadata": {
    "aliases": ["string"],
    "region": "string",
    "meal_type": ["breakfast", "lunch", "dinner", "snack"],
    "dietary_flags": ["vegetarian", "vegan", "contains_meat", "contains_fish", "gluten_free", "dairy_free"],
    "confidence": 0.0-1.0,
    "sources": ["url"]
  },
  "nutrients": {
    "protein": float or null,
    "fat": float or null,
    "carbohydrates": float or null,
    "iron": float or null,
    "calcium": float or null,
    "vitamin_a": float or null,
    "zinc": float or null
  },
  "text": "string (RAG chunk with sections: Description, Typical portion, Nutrient highlights, Preparation adjustments, Local context)"
}"""

FEW_SHOT_EXAMPLES = [
    {
        "dish": "Jollof Rice",
        "response": {
            "id": "nigerian-jollof-rice",
            "metadata": {
                "aliases": ["party rice", "celebration rice", "red rice"],
                "region": "West Africa (Nigeria)",
                "meal_type": ["lunch", "dinner"],
                "dietary_flags": ["contains_meat"],
                "confidence": 0.85,
                "sources": [
                    "https://en.wikipedia.org/wiki/Jollof_rice",
                    "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6315720/",
                ],
            },
            "nutrients": {
                "protein": 4.2,
                "fat": 8.5,
                "carbohydrates": 32.1,
                "iron": 1.2,
                "calcium": 25.0,
                "vitamin_a": 450.0,
                "zinc": 0.8,
            },
            "text": """## Description
Jollof rice is a West African rice dish cooked in a tomato-based sauce with onions, peppers, and spices. Often served with chicken, beef, or fish.

## Typical portion
200 g (1 cup cooked)

## Nutrient highlights
Protein: 4.2 g | Fat: 8.5 g | Carbohydrates: 32.1 g | Iron: 1.2 mg | Calcium: 25 mg | Vitamin A: 450 µg | Zinc: 0.8 mg

## Preparation adjustments
Palm oil or vegetable oil adds fat; tomato paste boosts vitamin A; protein varies with meat/fish additions.

## Local context
Popular at celebrations and parties across Nigeria. Regional variations exist (Lagos vs. Northern styles).""",
        },
    },
    {
        "dish": "Egusi Soup",
        "response": {
            "id": "nigerian-egusi-soup",
            "metadata": {
                "aliases": ["melon soup", "egusi", "agusi"],
                "region": "Nigeria",
                "meal_type": ["lunch", "dinner"],
                "dietary_flags": ["contains_meat", "contains_fish"],
                "confidence": 0.80,
                "sources": [
                    "https://en.wikipedia.org/wiki/Egusi_soup",
                    "https://www.fao.org/3/y5609e/y5609e0b.htm",
                ],
            },
            "nutrients": {
                "protein": 8.5,
                "fat": 12.3,
                "carbohydrates": 6.2,
                "iron": 2.8,
                "calcium": 120.0,
                "vitamin_a": 850.0,
                "zinc": 1.5,
            },
            "text": """## Description
Egusi soup is a thick Nigerian soup made from ground melon seeds, leafy vegetables (ugwu/spinach), palm oil, and assorted meats or fish.

## Typical portion
250 g (1 bowl)

## Nutrient highlights
Protein: 8.5 g | Fat: 12.3 g | Carbohydrates: 6.2 g | Iron: 2.8 mg | Calcium: 120 mg | Vitamin A: 850 µg | Zinc: 1.5 mg

## Preparation adjustments
Palm oil increases vitamin A and fat; leafy greens (ugwu) boost iron and calcium; stockfish/crayfish add protein and zinc.

## Local context
Commonly eaten with fufu, pounded yam, or eba. Popular across all Nigerian regions with slight variations.""",
        },
    },
]


@dataclass
class Config:
    openai_api_key: str
    output_path: Path
    model: str = "gpt-4o-mini"
    temperature: float = 0.2


def build_user_prompt(dish_name: str) -> str:
    return f"""Dish: "{dish_name}"

Task: Return JSON matching the schema with best-available estimates from cited sources. Include aliases and typical portion info relevant to Nigeria."""


def extract_dish_data(client: OpenAI, config: Config, dish_name: str) -> Dict[str, Any] | None:
    """Extract structured data for a single dish using OpenAI."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    
    # Add few-shot examples
    for example in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": build_user_prompt(example["dish"])})
        messages.append({"role": "assistant", "content": json.dumps(example["response"], ensure_ascii=False)})
    
    # Add current dish
    messages.append({"role": "user", "content": build_user_prompt(dish_name)})
    
    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            response_format={"type": "json_object"},
        )
        
        content = response.choices[0].message.content
        if not content:
            print(f"⚠️  Empty response for {dish_name}")
            return None
        
        data = json.loads(content)
        return data
    
    except Exception as e:
        print(f"❌ Error extracting {dish_name}: {e}")
        return None


def validate_record(record: Dict[str, Any], dish_name: str) -> bool:
    """Validate extracted record against schema and ranges."""
    required_keys = ["id", "metadata", "nutrients", "text"]
    if not all(k in record for k in required_keys):
        print(f"⚠️  Missing required keys in {dish_name}")
        return False
    
    # Validate nutrients
    nutrients = record.get("nutrients", {})
    for key in TRACKED_NUTRIENTS:
        value = nutrients.get(key)
        if value is not None:
            if not isinstance(value, (int, float)):
                print(f"⚠️  Invalid nutrient type for {key} in {dish_name}: {type(value)}")
                return False
            
            # Range checks
            if key in ["protein", "fat", "carbohydrates"]:
                if not (0 <= value <= 100):
                    print(f"⚠️  Out of range {key} in {dish_name}: {value}")
                    return False
            elif key in ["iron", "calcium", "zinc"]:
                if not (0 <= value <= 100):
                    print(f"⚠️  Out of range {key} in {dish_name}: {value}")
                    return False
            elif key in ["vitamin_a"]:
                if not (0 <= value <= 50000):
                    print(f"⚠️  Out of range {key} in {dish_name}: {value}")
                    return False
    
    # Validate confidence
    confidence = record.get("metadata", {}).get("confidence")
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        print(f"⚠️  Invalid confidence in {dish_name}: {confidence}")
        return False
    
    return True


def generate_qa_report(records: List[Dict[str, Any]]) -> str:
    """Generate QA summary report."""
    total = len(records)
    if total == 0:
        return "No records generated."
    
    # Count missingness per nutrient
    missing_counts = {k: 0 for k in TRACKED_NUTRIENTS}
    confidence_sum = 0.0
    source_counts = 0
    
    for record in records:
        nutrients = record.get("nutrients", {})
        for key in TRACKED_NUTRIENTS:
            if nutrients.get(key) is None:
                missing_counts[key] += 1
        
        metadata = record.get("metadata", {})
        confidence_sum += metadata.get("confidence", 0.0)
        source_counts += len(metadata.get("sources", []))
    
    avg_confidence = confidence_sum / total
    avg_sources = source_counts / total
    
    report = [
        "\n🔍 QA SUMMARY",
        f"\n📊 Total Records: {total}",
        f"\n📈 Average Confidence: {avg_confidence:.2f}",
        f"\n📚 Average Sources per Dish: {avg_sources:.1f}",
        "\n🧪 Missingness per Nutrient (count, %):",
    ]
    
    for key in TRACKED_NUTRIENTS:
        count = missing_counts[key]
        pct = (count / total) * 100
        report.append(f"  - {key}: {count} ({pct:.1f}%)")
    
    return "\n".join(report)


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is required")
    
    root = Path(__file__).resolve().parent.parent
    output_path = root / "data" / "processed" / "nigerian_llm_complete.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    config = Config(
        openai_api_key=api_key,
        output_path=output_path,
    )
    
    client = OpenAI(api_key=config.openai_api_key)
    
    all_dishes = NIGERIAN_DISHES + GLOBAL_STAPLES
    records: List[Dict[str, Any]] = []
    
    print(f"🚀 Starting LLM extraction for {len(all_dishes)} dishes...")
    print(f"📦 Output: {output_path}\n")
    
    with output_path.open("w", encoding="utf-8") as handle:
        for i, dish in enumerate(all_dishes, 1):
            print(f"[{i}/{len(all_dishes)}] Extracting: {dish}...", end=" ")
            
            data = extract_dish_data(client, config, dish)
            if data and validate_record(data, dish):
                handle.write(json.dumps(data, ensure_ascii=False) + "\n")
                records.append(data)
                print("✅")
            else:
                print("❌")
    
    # Generate QA report
    qa_report = generate_qa_report(records)
    print(qa_report)
    
    # Save QA report
    qa_path = root / "data" / "processed" / "nigerian_llm_qa.txt"
    with qa_path.open("w", encoding="utf-8") as handle:
        handle.write(qa_report)
    
    print(f"\n✅ Extraction complete! {len(records)}/{len(all_dishes)} records written.")
    print(f"📄 QA report saved to: {qa_path}")


if __name__ == "__main__":
    main()

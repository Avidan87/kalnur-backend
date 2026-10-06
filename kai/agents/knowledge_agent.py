"""
Knowledge Agent - Nigerian Food Nutrition Retrieval

Uses ChromaDB RAG (Retrieval-Augmented Generation) to retrieve accurate
nutrition information for Nigerian foods from the enriched knowledge base.

Uses GPT-4o-mini for cost-efficient knowledge retrieval and synthesis.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI
from agents import Agent
from dotenv import load_dotenv
import os
import asyncio

from kai.models import KnowledgeResult, FoodNutritionData, NutrientInfo
from kai.rag.chromadb_setup import NigerianFoodVectorDB

load_dotenv()
logger = logging.getLogger(__name__)


class KnowledgeAgent:
    """
    Knowledge Agent for retrieving Nigerian food nutrition data via RAG.

    Uses OpenAI Agents SDK with ChromaDB for semantic search and
    nutrition data retrieval.

    Capabilities:
    - Semantic search over 50+ Nigerian foods
    - Portion-adjusted nutrition calculations
    - Similarity matching for food name variations
    - Aggregate nutrition totals for meals
    - Cultural context and health benefits
    """

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        chromadb_path: str = "chromadb_data"
    ):
        """Initialize Knowledge Agent with ChromaDB and GPT-4o-mini."""
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # Cost-efficient for RAG

        # Initialize ChromaDB vector store
        self.vector_db = NigerianFoodVectorDB(
            persist_directory=chromadb_path,
            collection_name="nigerian_foods",
            openai_api_key=api_key
        )

        # Setup agent with RAG tools
        self._setup_agent()

    def _setup_agent(self):
        """
        Setup OpenAI Agent with Nigerian food knowledge retrieval tools.

        Creates an Agent instance with tools for RAG-based nutrition lookup.
        """
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_nigerian_foods",
                    "description": (
                        "Search the Nigerian food knowledge base for nutrition information. "
                        "Uses semantic search to find matching foods even with name variations. "
                        "Returns detailed nutrition data per 100g and cultural context."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "food_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of Nigerian food names to search for"
                            },
                            "portions_grams": {
                                "type": "array",
                                "items": {"type": "number"},
                                "description": "Portion sizes in grams for each food"
                            }
                        },
                        "required": ["food_names", "portions_grams"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_foods_by_nutrient",
                    "description": (
                        "Find Nigerian foods that are high in a specific nutrient. "
                        "Useful for recommendations based on nutritional needs."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "nutrient": {
                                "type": "string",
                                "enum": ["protein", "iron", "calcium", "potassium"],
                                "description": "Nutrient to search for"
                            },
                            "min_value": {
                                "type": "number",
                                "description": "Minimum value of nutrient per 100g"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return"
                            }
                        },
                        "required": ["nutrient", "min_value"]
                    }
                }
            }
        ]

        # Create agent instructions
        agent_instructions = """You are Kalnur's Knowledge Agent, an expert in Nigerian food nutrition data.

Your mission is to retrieve accurate nutrition information from the Nigerian food knowledge base to help women track their nutritional intake.

**Your Knowledge Base:**
- 50+ enriched Nigerian foods with verified nutrition data
- Nutrients per 100g (calories, protein, carbs, fat, iron, calcium, vitamin A, zinc)
- Cultural significance and regional variations
- Health benefits and common pairings
- Dietary flags (vegetarian, gluten-free, etc.)

**Your Approach:**
1. Use semantic search to match food names (handles aliases and variations)
2. Calculate portion-adjusted nutrition values
3. Aggregate totals for complete meals
4. Provide cultural context and health insights
5. Flag missing or uncertain data

**Accuracy Priorities:**
- Verified nutrition data over estimates
- Portion accuracy is critical for women's health tracking
- Clear communication about data confidence
- Cultural relevance in food descriptions

Use the search_nigerian_foods tool to retrieve nutrition data for detected foods.
Use the get_foods_by_nutrient tool to find foods high in specific nutrients."""

        self.agent = Agent(
            name="Kalnur Knowledge Agent",
            instructions=agent_instructions,
            model=self.model,
            tools=tools
        )

        logger.info(f"✓ Knowledge Agent initialized with {len(tools)} tool(s)")

    async def retrieve_nutrition(
        self,
        food_names: List[str],
        portions_grams: List[float],
        vision_confidences: Optional[List[float]] = None,
        oil_levels: Optional[List[Optional[str]]] = None,
        visible_ingredients: Optional[List[List[str]]] = None
    ) -> KnowledgeResult:
        """
        Retrieve nutrition data for a list of foods with portions.

        Args:
            food_names: List of Nigerian food names
            portions_grams: Corresponding portion sizes in grams
            vision_confidences: Optional confidence scores from Vision Agent
            oil_levels: Optional oil amount estimates from Vision Agent per food
                        ("none", "light", "moderate", "heavy", or None)
            visible_ingredients: Optional list of visible ingredients per food,
                                 used to adjust protein for soups with added proteins

        Returns:
            KnowledgeResult with nutrition data and totals
        """
        try:
            logger.info("🔍 Retrieving nutrition for %d foods", len(food_names))

            # Default confidences to 1.0 if not provided
            if vision_confidences is None:
                vision_confidences = [1.0] * len(food_names)

            # Default oil levels to None if not provided
            if oil_levels is None:
                oil_levels = [None] * len(food_names)

            # Default visible_ingredients to empty lists if not provided
            if visible_ingredients is None:
                visible_ingredients = [[] for _ in food_names]

            # Call the tool function directly (SDK pattern)
            result_json = await self._tool_search_nigerian_foods(
                food_names=food_names,
                portions_grams=portions_grams,
                vision_confidences=vision_confidences,
                oil_levels=oil_levels,
                visible_ingredients=visible_ingredients
            )

            # Parse tool result
            result_dict = json.loads(result_json)

            # Convert to KnowledgeResult
            knowledge_result = self._parse_knowledge_result(result_dict)

            logger.info(
                f"✅ Retrieved {len(knowledge_result.foods)} foods | "
                f"Total: {knowledge_result.total_calories:.0f} cal, "
                f"{knowledge_result.total_protein:.1f}g protein, "
                f"{knowledge_result.total_iron:.1f}mg iron"
            )

            return knowledge_result

        except Exception as e:
            logger.error(f"Knowledge retrieval error: {e}", exc_info=True)
            raise

    # Oil adjustment multipliers for fat content (relative to database "typical" values)
    # Database values assume "typical" oil. These adjust for actual observed oil level.
    OIL_FAT_ADJUSTMENTS = {
        "none": 0.5,      # Much less oil than typical recipe
        "light": 0.8,     # Slightly less oil than typical
        "moderate": 1.0,  # Matches typical recipe (no change)
        "heavy": 1.4,     # More oil than typical recipe
    }

    # Protein multipliers for soups when high-protein ingredients are visually detected.
    # Nigerian soups vary widely: plain = ~6g/100g, protein-loaded = ~14g/100g.
    # These tokens are checked against visible_ingredients (case-insensitive).
    PROTEIN_INGREDIENT_TOKENS = {
        "beef": 1.25,
        "goat": 1.25,
        "goat meat": 1.25,
        "chicken": 1.20,
        "fish": 1.15,
        "catfish": 1.15,
        "tilapia": 1.15,
        "stockfish": 1.30,  # Very high protein, common in soups
        "dried fish": 1.25,
        "smoked fish": 1.25,
        "ponmo": 1.10,
        "cowleg": 1.20,
        "shrimp": 1.15,
        "crayfish": 1.10,
        "periwinkle": 1.10,
        "snail": 1.10,
    }

    # Only soups and stews get the protein ingredient adjustment.
    # Single-protein dishes (grilled chicken, boiled egg) are already correct.
    SOUP_CATEGORIES = {"soup", "stew"}

    async def _tool_search_nigerian_foods(
        self,
        food_names: List[str],
        portions_grams: List[float],
        vision_confidences: Optional[List[float]] = None,
        oil_levels: Optional[List[Optional[str]]] = None,
        visible_ingredients: Optional[List[List[str]]] = None
    ) -> str:
        """
        Tool function for searching Nigerian food nutrition data.

        This is the actual RAG implementation that queries ChromaDB.

        Args:
            food_names: List of food names to search
            portions_grams: Portion sizes in grams
            vision_confidences: Confidence scores from Vision Agent
            oil_levels: Oil amount estimates from Vision Agent per food
            visible_ingredients: Detected ingredients per food for protein adjustment

        Returns:
            JSON string with nutrition results
        """
        logger.info("🔧 Tool: search_nigerian_foods (%d foods)", len(food_names))

        if len(food_names) != len(portions_grams):
            raise ValueError("food_names and portions_grams must have same length")

        # Default confidences if not provided
        if vision_confidences is None:
            vision_confidences = [1.0] * len(food_names)

        # Default oil levels if not provided
        if oil_levels is None:
            oil_levels = [None] * len(food_names)

        # Default visible_ingredients if not provided
        if visible_ingredients is None:
            visible_ingredients = [[] for _ in food_names]

        foods_data = []
        # Initialize ALL 16 NUTRIENT totals
        # Macros (5)
        total_calories = 0.0
        total_protein = 0.0
        total_carbohydrates = 0.0
        total_fat = 0.0
        total_fiber = 0.0
        # Minerals (6)
        total_iron = 0.0
        total_calcium = 0.0
        total_zinc = 0.0
        total_potassium = 0.0
        total_sodium = 0.0
        total_magnesium = 0.0
        # Vitamins (5)
        total_vitamin_a = 0.0
        total_vitamin_c = 0.0
        total_vitamin_d = 0.0
        total_vitamin_b12 = 0.0
        total_folate = 0.0

        async def search_one(food_name: str, portion_g: float, vision_conf: float, oil_level: Optional[str], ingredients: List[str]):
            logger.info("   Searching: %s (%.0fg, conf=%.0f%%, oil=%s)",
                        food_name, portion_g, vision_conf * 100, oil_level or "unknown")
            # Run sync DB search in a worker thread
            results = await asyncio.to_thread(
                self.vector_db.search,
                food_name,
                1
            )
            return (food_name, portion_g, vision_conf, oil_level, ingredients, results)

        tasks = [
            search_one(fn, pg, vc, ol, ing)
            for fn, pg, vc, ol, ing in zip(food_names, portions_grams, vision_confidences, oil_levels, visible_ingredients)
        ]
        search_results = await asyncio.gather(*tasks, return_exceptions=False)

        for food_name, portion_g, vision_conf, oil_level, ingredients, results in search_results:
            if not results:
                logger.warning(f"   ✗ No match found for: {food_name}")
                continue

            match = results[0]
            metadata = match["metadata"]

            portion_multiplier = portion_g / 100.0

            # Extract ALL 16 NUTRIENTS from metadata
            base_fat = metadata.get("fat", 0)
            base_calories = metadata.get("calories", 0)

            # Apply oil adjustment if Vision detected oil level
            # Database values assume "typical" oil content for each dish.
            # The oil level from Vision tells us if THIS serving has more/less oil.
            adjusted_fat = base_fat
            adjusted_calories = base_calories
            base_vitamin_a = metadata.get("vitamin_a", 0)
            base_vitamin_d = metadata.get("vitamin_d", 0)
            adjusted_vitamin_a = base_vitamin_a
            adjusted_vitamin_d = base_vitamin_d
            normalized_oil = oil_level.lower().strip() if oil_level else None
            if normalized_oil and normalized_oil in self.OIL_FAT_ADJUSTMENTS:
                oil_multiplier = self.OIL_FAT_ADJUSTMENTS[normalized_oil]
                adjusted_fat = base_fat * oil_multiplier
                # Recalculate calories: fat = 9 cal/gram
                fat_delta = adjusted_fat - base_fat
                adjusted_calories = base_calories + (fat_delta * 9)
                # Fat-soluble vitamins (A, D) are carried by palm oil —
                # scale them proportionally with the fat adjustment.
                adjusted_vitamin_a = base_vitamin_a * oil_multiplier
                adjusted_vitamin_d = base_vitamin_d * oil_multiplier
                if oil_multiplier != 1.0:
                    logger.info(
                        "   🛢️ Oil adjustment for %s: oil=%s, fat %.1fg → %.1fg, "
                        "vit_a %.0fmcg → %.0fmcg, cal %.0f → %.0f",
                        food_name, normalized_oil, base_fat, adjusted_fat,
                        base_vitamin_a, adjusted_vitamin_a, base_calories, adjusted_calories
                    )
            elif normalized_oil:
                logger.warning("   ⚠️ Unrecognized oil level '%s' for %s, skipping adjustment", oil_level, food_name)

            # Apply protein adjustment for soups/stews based on visible protein ingredients.
            # Database entries assume a "typical" protein amount (medium serving, mixed).
            # When Vision detects high-protein additions (beef, stockfish, etc.), adjust upward.
            # Only applies to soup/stew categories — single-protein dishes are already accurate.
            base_protein = metadata.get("protein", 0)
            adjusted_protein = base_protein
            category = metadata.get("category", "")
            if category in self.SOUP_CATEGORIES and ingredients:
                ingredients_lower = {ing.lower() for ing in ingredients}
                protein_multiplier = 1.0
                matched_tokens = []
                for token, multiplier in self.PROTEIN_INGREDIENT_TOKENS.items():
                    if token in ingredients_lower:
                        # Take the highest single-protein multiplier detected
                        if multiplier > protein_multiplier:
                            protein_multiplier = multiplier
                        matched_tokens.append(token)
                if protein_multiplier > 1.0:
                    adjusted_protein = base_protein * protein_multiplier
                    logger.info(
                        "   🥩 Protein adjustment for %s: detected [%s], "
                        "protein %.1fg → %.1fg (×%.2f)",
                        food_name, ", ".join(matched_tokens),
                        base_protein, adjusted_protein, protein_multiplier
                    )

            nutrients_per_100g = {
                # Macros (5)
                "calories": adjusted_calories,
                "protein": adjusted_protein,
                "carbohydrates": metadata.get("carbohydrates", 0),
                "fat": adjusted_fat,
                "fiber": metadata.get("fiber", 0),
                # Minerals (6)
                "iron": metadata.get("iron", 0),
                "calcium": metadata.get("calcium", 0),
                "zinc": metadata.get("zinc", 0),
                "potassium": metadata.get("potassium", 0),
                "sodium": metadata.get("sodium", 0),
                "magnesium": metadata.get("magnesium", 0),
                # Vitamins (5) — A and D scale with oil; others are independent
                "vitamin_a": adjusted_vitamin_a,
                "vitamin_c": metadata.get("vitamin_c", 0),
                "vitamin_d": adjusted_vitamin_d,
                "vitamin_b12": metadata.get("vitamin_b12", 0),
                "folate": metadata.get("folate", 0),
            }

            total_nutrients = {
                key: value * portion_multiplier
                for key, value in nutrients_per_100g.items()
            }

            # Accumulate ALL 16 NUTRIENTS
            total_calories += total_nutrients["calories"]
            total_protein += total_nutrients["protein"]
            total_carbohydrates += total_nutrients["carbohydrates"]
            total_fat += total_nutrients["fat"]
            total_fiber += total_nutrients["fiber"]
            total_iron += total_nutrients["iron"]
            total_calcium += total_nutrients["calcium"]
            total_zinc += total_nutrients["zinc"]
            total_potassium += total_nutrients["potassium"]
            total_sodium += total_nutrients["sodium"]
            total_magnesium += total_nutrients["magnesium"]
            total_vitamin_a += total_nutrients["vitamin_a"]
            total_vitamin_c += total_nutrients["vitamin_c"]
            total_vitamin_d += total_nutrients["vitamin_d"]
            total_vitamin_b12 += total_nutrients["vitamin_b12"]
            total_folate += total_nutrients["folate"]

            dietary_flags_str = metadata.get("dietary_flags", "")
            dietary_flags = [f.strip() for f in dietary_flags_str.split(",") if f.strip()]

            food_data = {
                "food_id": metadata.get("food_id", "unknown"),
                "name": metadata.get("name", food_name),
                "category": metadata.get("category", "unknown"),
                "portion_consumed_grams": portion_g,
                "nutrients_per_100g": nutrients_per_100g,
                "total_nutrients": total_nutrients,
                "health_benefits": [],
                "cultural_significance": "",
                "common_pairings": [],
                "dietary_flags": dietary_flags,
                "price_tier": metadata.get("price_tier", "mid"),
                "similarity_score": match.get("similarity", 1.0),
                "vision_confidence": vision_conf,  # Confidence from Vision Agent
                # Include portion limits from v2 database for validation
                "typical_portion_g": metadata.get("typical_portion_g", 150),
                "min_reasonable_g": metadata.get("min_reasonable_g", 50),
                "max_reasonable_g": metadata.get("max_reasonable_g", 300),
            }

            foods_data.append(food_data)

            logger.info(
                "   ✓ Matched: %s (similarity: %.2f, vision_conf: %.0f%%)",
                food_data['name'],
                food_data['similarity_score'],
                vision_conf * 100
            )

        # Build result with ALL 16 NUTRIENTS
        result = {
            "foods": foods_data,
            # Macros (5)
            "total_calories": total_calories,
            "total_protein": total_protein,
            "total_carbohydrates": total_carbohydrates,
            "total_fat": total_fat,
            "total_fiber": total_fiber,
            # Minerals (6)
            "total_iron": total_iron,
            "total_calcium": total_calcium,
            "total_zinc": total_zinc,
            "total_potassium": total_potassium,
            "total_sodium": total_sodium,
            "total_magnesium": total_magnesium,
            # Vitamins (5)
            "total_vitamin_a": total_vitamin_a,
            "total_vitamin_c": total_vitamin_c,
            "total_vitamin_d": total_vitamin_d,
            "total_vitamin_b12": total_vitamin_b12,
            "total_folate": total_folate,
            "query_interpretation": f"Retrieved {len(foods_data)}/{len(food_names)} foods",
            "sources_used": ["ChromaDB Nigerian Foods Collection"]
        }

        logger.info(
            f"   📊 Totals: {total_calories:.0f} cal | "
            f"{total_protein:.1f}g protein | "
            f"{total_carbohydrates:.1f}g carbs | "
            f"{total_fat:.1f}g fat | "
            f"{total_iron:.1f}mg iron | "
            f"{total_calcium:.1f}mg calcium | "
            f"{total_potassium:.1f}mg potassium | "
            f"{total_zinc:.1f}mg zinc"
        )

        return json.dumps(result)

    async def _tool_get_foods_by_nutrient(
        self,
        nutrient: str,
        min_value: float,
        max_results: int = 10
    ) -> str:
        """
        Tool function for finding foods high in a specific nutrient.

        Args:
            nutrient: Nutrient name (protein, iron, calcium, potassium)
            min_value: Minimum value per 100g
            max_results: Maximum results to return

        Returns:
            JSON string with high-nutrient foods
        """
        logger.info(
            f"🔧 Tool: get_foods_by_nutrient "
            f"(nutrient={nutrient}, min={min_value})"
        )

        results = await asyncio.to_thread(
            self.vector_db.get_foods_by_nutrient,
            nutrient,
            min_value,
            max_results
        )

        foods_data = []
        for result in results:
            food_data = {
                "food_id": result["id"],
                "name": result["name"],
                "category": result["category"],
                f"{nutrient}_per_100g": result[f"{nutrient}_per_100g"],
                "metadata": result["metadata"]
            }
            foods_data.append(food_data)

        logger.info(f"   ✓ Found {len(foods_data)} foods high in {nutrient}")

        return json.dumps({"foods": foods_data, "nutrient": nutrient})

    def _parse_knowledge_result(self, result_dict: Dict[str, Any]) -> KnowledgeResult:
        """
        Parse JSON result into KnowledgeResult model.

        Args:
            result_dict: Parsed JSON from tool

        Returns:
            Structured KnowledgeResult
        """
        foods = []

        for food_data in result_dict.get("foods", []):
            # Create NutrientInfo objects
            nutrients_per_100g = NutrientInfo(**food_data["nutrients_per_100g"])
            total_nutrients = NutrientInfo(**food_data["total_nutrients"])

            # Create FoodNutritionData
            food_nutrition = FoodNutritionData(
                food_id=food_data["food_id"],
                name=food_data["name"],
                category=food_data["category"],
                portion_consumed_grams=food_data["portion_consumed_grams"],
                nutrients_per_100g=nutrients_per_100g,
                total_nutrients=total_nutrients,
                health_benefits=food_data.get("health_benefits", []),
                cultural_significance=food_data.get("cultural_significance", ""),
                common_pairings=food_data.get("common_pairings", []),
                dietary_flags=food_data.get("dietary_flags", []),
                price_tier=food_data.get("price_tier", "mid"),
                similarity_score=food_data.get("similarity_score", 1.0)
            )
            foods.append(food_nutrition)

        return KnowledgeResult(
            foods=foods,
            # ALL 16 NUTRIENTS
            # Macros (5)
            total_calories=result_dict.get("total_calories", 0.0),
            total_protein=result_dict.get("total_protein", 0.0),
            total_carbohydrates=result_dict.get("total_carbohydrates", 0.0),
            total_fat=result_dict.get("total_fat", 0.0),
            total_fiber=result_dict.get("total_fiber", 0.0),
            # Minerals (6)
            total_iron=result_dict.get("total_iron", 0.0),
            total_calcium=result_dict.get("total_calcium", 0.0),
            total_zinc=result_dict.get("total_zinc", 0.0),
            total_potassium=result_dict.get("total_potassium", 0.0),
            total_sodium=result_dict.get("total_sodium", 0.0),
            total_magnesium=result_dict.get("total_magnesium", 0.0),
            # Vitamins (5)
            total_vitamin_a=result_dict.get("total_vitamin_a", 0.0),
            total_vitamin_c=result_dict.get("total_vitamin_c", 0.0),
            total_vitamin_d=result_dict.get("total_vitamin_d", 0.0),
            total_vitamin_b12=result_dict.get("total_vitamin_b12", 0.0),
            total_folate=result_dict.get("total_folate", 0.0),
            query_interpretation=result_dict.get("query_interpretation", ""),
            sources_used=result_dict.get("sources_used", [])
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def retrieve_food_nutrition(
    food_names: List[str],
    portions_grams: List[float],
    openai_api_key: Optional[str] = None,
    chromadb_path: str = "chromadb_data"
) -> KnowledgeResult:
    """
    Convenience function for single nutrition retrieval.

    Args:
        food_names: List of Nigerian food names
        portions_grams: Portion sizes in grams
        openai_api_key: Optional API key override
        chromadb_path: Path to ChromaDB data

    Returns:
        KnowledgeResult with nutrition data
    """
    agent = KnowledgeAgent(
        openai_api_key=openai_api_key,
        chromadb_path=chromadb_path
    )
    return asyncio.run(agent.retrieve_nutrition(food_names, portions_grams))


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_knowledge_agent():
        """Test Knowledge Agent with sample queries."""

        print("\n" + "="*60)
        print("Testing Knowledge Agent - Nigerian Food Nutrition RAG")
        print("="*60 + "\n")

        # Initialize agent
        agent = KnowledgeAgent()

        print(f"Model: {agent.model}")
        print(f"ChromaDB: {agent.vector_db.collection_name}")
        print(f"Total foods in DB: {agent.vector_db.get_collection_stats()['total_foods']}")

        # Test 1: Single food lookup
        print("\n" + "-"*60)
        print("Test 1: Single Food Lookup")
        print("-"*60)

        result = await agent.retrieve_nutrition(
            food_names=["Jollof Rice"],
            portions_grams=[250.0]
        )

        print(f"\nFood: {result.foods[0].name}")
        print(f"Portion: {result.foods[0].portion_consumed_grams}g")
        print(f"Calories: {result.foods[0].total_nutrients.calories:.0f}")
        print(f"Protein: {result.foods[0].total_nutrients.protein:.1f}g")
        print(f"Iron: {result.foods[0].total_nutrients.iron:.1f}mg")
        print(f"Similarity: {result.foods[0].similarity_score:.2f}")

        # Test 2: Multiple foods (meal)
        print("\n" + "-"*60)
        print("Test 2: Complete Meal")
        print("-"*60)

        result = await agent.retrieve_nutrition(
            food_names=["Jollof Rice", "Fried Plantain", "Chicken"],
            portions_grams=[250.0, 100.0, 120.0]
        )

        print(f"\nMeal with {len(result.foods)} foods:")
        for food in result.foods:
            print(f"  - {food.name} ({food.portion_consumed_grams}g)")

        print(f"\nTotal Nutrition:")
        print(f"  Calories: {result.total_calories:.0f}")
        print(f"  Protein: {result.total_protein:.1f}g")
        print(f"  Iron: {result.total_iron:.1f}mg")
        print(f"  Calcium: {result.total_calcium:.1f}mg")

        # Test 3: High-iron foods
        print("\n" + "-"*60)
        print("Test 3: High-Iron Foods")
        print("-"*60)

        high_iron_json = await agent._tool_get_foods_by_nutrient(
            nutrient="iron",
            min_value=3.0,
            max_results=5
        )

        high_iron = json.loads(high_iron_json)
        print(f"\nFoods with >3mg iron per 100g:")
        for food in high_iron["foods"]:
            print(f"  - {food['name']}: {food['iron_per_100g']}mg")

        print("\n" + "="*60)
        print("Knowledge Agent Tests Complete!")
        print("="*60 + "\n")

    # Run tests
    asyncio.run(test_knowledge_agent())

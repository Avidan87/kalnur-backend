"""
Nigerian Food Vector DB - Supabase pgvector

Replaces ChromaDB with Supabase pgvector for semantic search.
Keeps the same interface (NigerianFoodVectorDB) so agents don't need changes.
"""

import json
import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
logger = logging.getLogger(__name__)


class NigerianFoodVectorDB:
    """Vector database for Nigerian food nutrition data using Supabase pgvector"""

    def __init__(
        self,
        persist_directory: str = "chromadb_data",  # Kept for backward compat, ignored
        collection_name: str = "nigerian_foods",   # Kept for backward compat, ignored
        openai_api_key: Optional[str] = None
    ):
        """
        Initialize with Supabase pgvector + OpenAI embeddings.

        Args:
            persist_directory: Ignored (kept for backward compatibility)
            collection_name: Ignored (kept for backward compatibility)
            openai_api_key: OpenAI API key for embeddings
        """
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        self.openai_client = OpenAI(api_key=api_key)
        self.embedding_model = "text-embedding-3-large"
        self.collection_name = "nigerian_foods"

        # Get Supabase client
        from kai.database.db_setup import get_supabase
        self.supabase = get_supabase()

        logger.info("✓ NigerianFoodVectorDB initialized with Supabase pgvector")

    def _get_embedding(self, text: str) -> List[float]:
        """Get OpenAI embedding for text."""
        response = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding

    def _create_document_text(self, food: Dict[str, Any]) -> str:
        """
        Create searchable text from food data.
        Same as the original ChromaDB version.
        """
        nutrients = food.get("nutrients_per_100g", {})

        text_parts = [
            f"Food: {food['name']}",
            f"Also known as: {', '.join(food.get('aliases', []))}",
            f"Category: {food['category']}",
            f"Description: {food['description']}",
            f"Typical portion: {food.get('typical_portion', 'N/A')}",
            f"Meal types: {', '.join(food.get('meal_types', []))}",
            f"Cooking methods: {', '.join(food.get('cooking_methods', []))}",
            f"Common pairings: {', '.join(food.get('common_pairings', []))}",
            f"Dietary flags: {', '.join(food.get('dietary_flags', []))}",
            f"Health benefits: {' '.join(food.get('health_benefits', []))}",
            f"Cultural significance: {food.get('cultural_significance', '')}",
            f"Price tier: {food.get('price_tier', 'N/A')}",
            f"Availability: {food.get('availability', 'N/A')}",
            f"Calories: {nutrients.get('calories', 'N/A')} per 100g",
            f"Protein: {nutrients.get('protein', 'N/A')}g per 100g",
            f"Iron: {nutrients.get('iron', 'N/A')}mg per 100g",
            f"Calcium: {nutrients.get('calcium', 'N/A')}mg per 100g",
        ]

        return "\n".join(text_parts)

    def load_foods_from_jsonl(self, jsonl_path: str) -> int:
        """
        Load Nigerian food data from JSONL file into Supabase pgvector.

        Args:
            jsonl_path: Path to the enriched foods JSONL file

        Returns:
            Number of foods loaded
        """
        foods_loaded = 0

        print(f"\n📂 Loading foods from {jsonl_path}...")

        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    food = json.loads(line)
                    nutrients = food.get("nutrients_per_100g", {})
                    common_servings = food.get("common_servings", {})

                    # Create document text
                    doc_text = self._create_document_text(food)

                    # Generate embedding
                    embedding = self._get_embedding(doc_text)

                    # Build row for Supabase
                    row = {
                        "food_id": food["id"],
                        "name": food["name"],
                        "category": food["category"],
                        "region": food.get("region", "Nigeria"),
                        "price_tier": food.get("price_tier", "mid"),
                        "availability": food.get("availability", "widely_available"),
                        "confidence": food.get("confidence", 0.0),
                        # Nutrients per 100g
                        "calories": nutrients.get("calories", 0),
                        "protein": nutrients.get("protein", 0),
                        "carbohydrates": nutrients.get("carbohydrates", 0),
                        "fat": nutrients.get("fat", 0),
                        "fiber": nutrients.get("fiber", 0),
                        "iron": nutrients.get("iron", 0),
                        "calcium": nutrients.get("calcium", 0),
                        "zinc": nutrients.get("zinc", 0),
                        "potassium": nutrients.get("potassium", 0),
                        "sodium": nutrients.get("sodium", 0),
                        "magnesium": nutrients.get("magnesium", 0),
                        "vitamin_a": nutrients.get("vitamin_a", 0),
                        "vitamin_c": nutrients.get("vitamin_c", 0),
                        "vitamin_d": nutrients.get("vitamin_d", 0),
                        "vitamin_b12": nutrients.get("vitamin_b12", 0),
                        "folate": nutrients.get("folate", 0),
                        # Metadata
                        "dietary_flags": ",".join(food.get("dietary_flags", [])),
                        "meal_types": ",".join(food.get("meal_types", [])),
                        "typical_portion_g": common_servings.get("typical_portion_g", 150),
                        "min_reasonable_g": common_servings.get("min_reasonable_g", 50),
                        "max_reasonable_g": common_servings.get("max_reasonable_g", 300),
                        "document": doc_text,
                        "embedding": embedding,
                    }

                    # Upsert (insert or update on conflict)
                    self.supabase.table("nigerian_foods").upsert(row).execute()

                    foods_loaded += 1

                    if foods_loaded % 10 == 0:
                        print(f"   Processed {foods_loaded} foods...")

                except json.JSONDecodeError as e:
                    print(f"   ✗ Error parsing line {line_num}: {e}")
                    continue
                except Exception as e:
                    print(f"   ✗ Error processing line {line_num}: {e}")
                    continue

        print(f"   ✓ Successfully loaded {foods_loaded} foods to Supabase pgvector")
        return foods_loaded

    def search(
        self,
        query: str,
        n_results: int = 5,
        category_filter: Optional[str] = None,
        dietary_filter: Optional[str] = None,
        meal_type_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for foods using semantic similarity via pgvector.

        Args:
            query: Natural language search query
            n_results: Number of results to return
            category_filter: Filter by category
            dietary_filter: Filter by dietary flag
            meal_type_filter: Filter by meal type

        Returns:
            List of matching food documents with metadata
        """
        # Generate embedding for query
        query_embedding = self._get_embedding(query)

        # Call the RPC function for vector search
        result = self.supabase.rpc("search_foods", {
            "query_embedding": query_embedding,
            "match_count": n_results * 3,  # Get more for post-filtering
        }).execute()

        # Post-filter
        filtered_results = []
        for row in result.data:
            if category_filter and row.get("category") != category_filter:
                continue
            if dietary_filter:
                flags = row.get("dietary_flags", "")
                if dietary_filter not in flags:
                    continue
            if meal_type_filter:
                types = row.get("meal_types", "")
                if meal_type_filter not in types:
                    continue

            filtered_results.append(row)
            if len(filtered_results) >= n_results:
                break

        # Format results to match old ChromaDB interface
        formatted_results = []
        for row in filtered_results:
            formatted_results.append({
                "id": row["food_id"],
                "name": row["name"],
                "category": row["category"],
                "distance": 1 - row.get("similarity", 0),
                "similarity": row.get("similarity", 0),
                "metadata": {
                    "food_id": row["food_id"],
                    "name": row["name"],
                    "category": row["category"],
                    "calories": row.get("calories", 0),
                    "protein": row.get("protein", 0),
                    "carbohydrates": row.get("carbohydrates", 0),
                    "fat": row.get("fat", 0),
                    "fiber": row.get("fiber", 0),
                    "iron": row.get("iron", 0),
                    "calcium": row.get("calcium", 0),
                    "zinc": row.get("zinc", 0),
                    "potassium": row.get("potassium", 0),
                    "sodium": row.get("sodium", 0),
                    "magnesium": row.get("magnesium", 0),
                    "vitamin_a": row.get("vitamin_a", 0),
                    "vitamin_c": row.get("vitamin_c", 0),
                    "vitamin_d": row.get("vitamin_d", 0),
                    "vitamin_b12": row.get("vitamin_b12", 0),
                    "folate": row.get("folate", 0),
                    "dietary_flags": row.get("dietary_flags", ""),
                    "meal_types": row.get("meal_types", ""),
                    "typical_portion_g": row.get("typical_portion_g", 150),
                    "min_reasonable_g": row.get("min_reasonable_g", 50),
                    "max_reasonable_g": row.get("max_reasonable_g", 300),
                    "price_tier": row.get("price_tier", "mid"),
                },
                "document": row.get("document", ""),
            })

        return formatted_results

    def get_food_by_id(self, food_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific food by ID.

        Args:
            food_id: Food ID (e.g., "nigerian-jollof-rice")

        Returns:
            Food data or None if not found
        """
        try:
            result = self.supabase.table("nigerian_foods").select("*").eq(
                "food_id", food_id
            ).execute()

            if not result.data:
                return None

            row = result.data[0]
            return {
                "id": row["food_id"],
                "metadata": {
                    "food_id": row["food_id"],
                    "name": row["name"],
                    "category": row["category"],
                    "calories": row.get("calories", 0),
                    "protein": row.get("protein", 0),
                    "carbohydrates": row.get("carbohydrates", 0),
                    "fat": row.get("fat", 0),
                    "fiber": row.get("fiber", 0),
                    "iron": row.get("iron", 0),
                    "calcium": row.get("calcium", 0),
                    "zinc": row.get("zinc", 0),
                    "potassium": row.get("potassium", 0),
                    "sodium": row.get("sodium", 0),
                    "magnesium": row.get("magnesium", 0),
                    "vitamin_a": row.get("vitamin_a", 0),
                    "vitamin_c": row.get("vitamin_c", 0),
                    "vitamin_d": row.get("vitamin_d", 0),
                    "vitamin_b12": row.get("vitamin_b12", 0),
                    "folate": row.get("folate", 0),
                },
                "document": row.get("document", ""),
            }

        except Exception as e:
            logger.error(f"Error retrieving food {food_id}: {e}")
            return None

    def get_foods_by_nutrient(
        self,
        nutrient: str,
        min_value: float,
        n_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get foods with high amounts of a specific nutrient.

        Args:
            nutrient: Nutrient name ("protein", "iron", "calcium", "potassium")
            min_value: Minimum value of nutrient
            n_results: Number of results to return

        Returns:
            List of foods matching criteria
        """
        nutrient_key = nutrient.lower()

        try:
            result = self.supabase.rpc("get_foods_by_nutrient", {
                "nutrient_name": nutrient_key,
                "min_value": min_value,
                "max_results": n_results,
            }).execute()

            formatted_results = []
            for row in result.data:
                formatted_results.append({
                    "id": row["food_id"],
                    "name": row["name"],
                    "category": row["category"],
                    f"{nutrient}_per_100g": row.get("nutrient_value", 0),
                    "metadata": {"name": row["name"], "category": row["category"]},
                })

            return formatted_results

        except Exception as e:
            logger.error(f"Error querying by nutrient: {e}")
            return []

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection."""
        result = self.supabase.table("nigerian_foods").select(
            "food_id", count="exact"
        ).limit(0).execute()

        return {
            "collection_name": self.collection_name,
            "total_foods": result.count or 0,
            "persist_directory": "Supabase pgvector",
            "embedding_model": self.embedding_model,
            "embedding_dimensions": 3072
        }

    def reset_collection(self):
        """Reset the collection (delete all food data)"""
        self.supabase.table("nigerian_foods").delete().neq(
            "food_id", "___impossible___"
        ).execute()
        print(f"✓ Collection 'nigerian_foods' reset")


def initialize_chromadb(
    enriched_foods_path: str = "knowledge-base/data/processed/nigerian_foods_v2_improved.jsonl",
    persist_directory: str = "chromadb_data",
    reset: bool = False
) -> NigerianFoodVectorDB:
    """
    Initialize pgvector and load Nigerian food data.
    Name kept as initialize_chromadb for backward compatibility.

    Args:
        enriched_foods_path: Path to enriched foods JSONL
        persist_directory: Ignored (kept for backward compat)
        reset: Whether to reset existing data

    Returns:
        Initialized NigerianFoodVectorDB instance
    """
    print("\n🚀 Initializing Supabase pgvector for Nigerian Food Knowledge Base\n")

    vector_db = NigerianFoodVectorDB()

    if reset:
        print("⚠️  Resetting existing collection...")
        vector_db.reset_collection()

    # Check if collection is already populated
    stats = vector_db.get_collection_stats()
    if stats['total_foods'] > 0 and not reset:
        print(f"ℹ️  Collection already contains {stats['total_foods']} foods")
        print("   Use reset=True to reload data\n")
        return vector_db

    # Load foods from JSONL
    foods_loaded = vector_db.load_foods_from_jsonl(enriched_foods_path)

    print("\n" + "=" * 60)
    print("✅ Supabase pgvector Initialization Complete!")
    print("=" * 60)
    stats = vector_db.get_collection_stats()
    print(f"📊 Collection: {stats['collection_name']}")
    print(f"📦 Total foods loaded: {stats['total_foods']}")
    print(f"🔢 Embedding dimensions: {stats['embedding_dimensions']}")
    print(f"💾 Storage: {stats['persist_directory']}")
    print("=" * 60 + "\n")

    return vector_db

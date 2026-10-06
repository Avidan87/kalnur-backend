"""
Database Setup - Supabase Client

Provides Supabase client for all database operations.
Tables are created via SQL migration in Supabase dashboard.
"""

import logging
import os
from typing import Optional
from contextlib import asynccontextmanager
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Supabase client singleton
_supabase_client: Optional[Client] = None


def get_supabase() -> Client:
    """
    Get Supabase client singleton.

    Returns:
        Supabase Client instance
    """
    global _supabase_client

    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment"
            )

        _supabase_client = create_client(url, key)
        logger.info(f"✓ Supabase client initialized: {url}")

    return _supabase_client


async def initialize_database() -> None:
    """
    Initialize Supabase connection and verify tables exist.

    Tables are created via supabase_migration.sql in the Supabase dashboard.
    This function just verifies the connection works.
    """
    logger.info("Initializing Supabase connection...")

    try:
        client = get_supabase()

        # Verify connection by checking users table
        result = client.table("users").select("user_id", count="exact").limit(0).execute()
        logger.info("✓ Supabase connection verified - tables ready")

    except Exception as e:
        logger.error(f"✗ Supabase connection failed: {e}")
        raise


async def get_database_stats() -> dict:
    """
    Get statistics about the database.

    Returns:
        dict: Database statistics (user count, meal count, etc.)
    """
    client = get_supabase()

    users = client.table("users").select("user_id", count="exact").limit(0).execute()
    user_count = users.count or 0

    meals = client.table("meals").select("meal_id", count="exact").limit(0).execute()
    meal_count = meals.count or 0

    foods = client.table("meal_foods").select("id", count="exact").limit(0).execute()
    food_count = foods.count or 0

    return {
        "users": user_count,
        "meals": meal_count,
        "foods_logged": food_count,
        "database": "Supabase PostgreSQL",
    }


@asynccontextmanager
async def get_db():
    """
    Compatibility context manager - returns Supabase client.

    Usage:
        async with get_db() as db:
            # db is the Supabase client
    """
    yield get_supabase()


async def reset_database() -> None:
    """
    WARNING: Deletes all data from all tables.
    """
    logger.warning("⚠️ Resetting database - deleting all data!")

    client = get_supabase()

    # Delete in order (respect foreign keys)
    tables_with_key = [
        ("user_recommendation_responses", "id"),
        ("user_food_frequency", "user_id"),
        ("user_nutrition_stats", "user_id"),
        ("daily_nutrients", "id"),
        ("meal_foods", "id"),
        ("meals", "meal_id"),
        ("user_health", "user_id"),
        ("users", "user_id"),
    ]

    for table, key_col in tables_with_key:
        try:
            client.table(table).delete().neq(key_col, "___impossible___").execute()
        except Exception as e:
            logger.warning(f"Could not clear {table}: {e}")

    logger.info("✓ Database reset complete")


# =============================================================================
# CLI Testing
# =============================================================================

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_database():
        """Test database setup"""
        print("\n" + "="*60)
        print("Testing Supabase Connection")
        print("="*60 + "\n")

        await initialize_database()

        stats = await get_database_stats()
        print("\nDatabase Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

        print("\n✓ Database setup test complete!\n")

    asyncio.run(test_database())

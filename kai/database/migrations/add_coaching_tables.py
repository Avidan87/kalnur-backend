"""
Database Migration: Add Coaching System Tables

Creates 3 new tables for dynamic coaching:
- user_nutrition_stats: Pre-computed user statistics for fast coaching
- user_food_frequency: Track user food eating patterns
- user_recommendation_responses: Track recommendation effectiveness

Run this migration to update existing database.
"""

import aiosqlite
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Database file location (same as main db_setup.py)
DB_PATH = Path("kai_database.db")


async def run_migration(db_path: Path = None) -> None:
    """
    Run migration to add coaching system tables.

    Args:
        db_path: Optional custom database path
    """
    path = db_path or DB_PATH
    logger.info(f"🔄 Running coaching tables migration on: {path}")

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # =====================================================================
        # Table 1: user_nutrition_stats
        # =====================================================================
        logger.info("Creating user_nutrition_stats table...")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_nutrition_stats (
                user_id TEXT PRIMARY KEY,

                -- Learning Phase Tracking
                total_meals_logged INTEGER DEFAULT 0,
                account_age_days INTEGER DEFAULT 0,
                learning_phase_complete BOOLEAN DEFAULT 0,

                -- Streak Tracking
                current_logging_streak INTEGER DEFAULT 0,
                longest_logging_streak INTEGER DEFAULT 0,
                last_logged_date TEXT,

                -- Week 1 Averages (Last 7 days)
                week1_avg_calories REAL DEFAULT 0,
                week1_avg_protein REAL DEFAULT 0,
                week1_avg_carbs REAL DEFAULT 0,
                week1_avg_fat REAL DEFAULT 0,
                week1_avg_iron REAL DEFAULT 0,
                week1_avg_calcium REAL DEFAULT 0,
                week1_avg_potassium REAL DEFAULT 0,
                week1_avg_zinc REAL DEFAULT 0,

                -- Week 2 Averages (8-14 days ago, for comparison)
                week2_avg_calories REAL DEFAULT 0,
                week2_avg_protein REAL DEFAULT 0,
                week2_avg_carbs REAL DEFAULT 0,
                week2_avg_fat REAL DEFAULT 0,
                week2_avg_iron REAL DEFAULT 0,
                week2_avg_calcium REAL DEFAULT 0,
                week2_avg_potassium REAL DEFAULT 0,
                week2_avg_zinc REAL DEFAULT 0,

                -- Nutrient Trends (improving, declining, stable)
                calories_trend TEXT DEFAULT 'stable',
                protein_trend TEXT DEFAULT 'stable',
                carbs_trend TEXT DEFAULT 'stable',
                fat_trend TEXT DEFAULT 'stable',
                iron_trend TEXT DEFAULT 'stable',
                calcium_trend TEXT DEFAULT 'stable',
                potassium_trend TEXT DEFAULT 'stable',
                zinc_trend TEXT DEFAULT 'stable',

                -- Last Calculated
                last_calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # =====================================================================
        # Table 2: user_food_frequency
        # =====================================================================
        logger.info("Creating user_food_frequency table...")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_food_frequency (
                user_id TEXT NOT NULL,
                food_name TEXT NOT NULL,

                -- Frequency Counts
                count_7d INTEGER DEFAULT 0,        -- Last 7 days
                count_total INTEGER DEFAULT 0,      -- All time

                -- Last Eaten
                last_eaten_date TEXT,

                -- Average Nutrition (when eaten)
                avg_iron_per_serving REAL DEFAULT 0,
                avg_protein_per_serving REAL DEFAULT 0,
                avg_calories_per_serving REAL DEFAULT 0,

                -- Categorization
                food_category TEXT,  -- 'rice_dishes', 'soups', 'proteins', etc.

                PRIMARY KEY (user_id, food_name),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # Index for fast food frequency queries
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_food_frequency_7d
            ON user_food_frequency(user_id, count_7d DESC)
        """)

        # =====================================================================
        # Table 3: user_recommendation_responses
        # =====================================================================
        logger.info("Creating user_recommendation_responses table...")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_recommendation_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                recommended_food TEXT NOT NULL,
                recommendation_date TEXT NOT NULL,

                -- Response Tracking
                followed BOOLEAN DEFAULT 0,
                followed_date TEXT,
                days_to_follow INTEGER,  -- How long until they tried it

                -- Recommendation Details
                recommendation_tier TEXT,  -- 'quick_win', 'easy_upgrade', 'full_dish', 'budget_friendly'
                target_nutrient TEXT,      -- 'iron', 'protein', 'calcium', etc.

                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # Index for recommendation tracking queries
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_recommendations
            ON user_recommendation_responses(user_id, recommendation_date DESC)
        """)

        await db.commit()
        logger.info("✅ Coaching tables migration completed successfully!")


async def rollback_migration(db_path: Path = None) -> None:
    """
    Rollback migration (drop coaching tables).

    WARNING: This deletes all coaching data!

    Args:
        db_path: Optional custom database path
    """
    path = db_path or DB_PATH
    logger.warning(f"⚠️ Rolling back coaching tables migration on: {path}")

    async with aiosqlite.connect(path) as db:
        await db.execute("DROP TABLE IF EXISTS user_recommendation_responses")
        await db.execute("DROP TABLE IF EXISTS user_food_frequency")
        await db.execute("DROP TABLE IF EXISTS user_nutrition_stats")
        await db.commit()

    logger.info("✅ Rollback completed")


# =============================================================================
# CLI Testing
# =============================================================================

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_migration():
        """Test migration"""
        print("\n" + "="*60)
        print("Testing Coaching Tables Migration")
        print("="*60 + "\n")

        # Run migration
        await run_migration()

        # Verify tables exist
        async with aiosqlite.connect(DB_PATH) as db:
            # Check user_nutrition_stats
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_nutrition_stats'"
            )
            result = await cursor.fetchone()
            if result:
                print("✅ user_nutrition_stats table created")
            else:
                print("❌ user_nutrition_stats table NOT found")

            # Check user_food_frequency
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_food_frequency'"
            )
            result = await cursor.fetchone()
            if result:
                print("✅ user_food_frequency table created")
            else:
                print("❌ user_food_frequency table NOT found")

            # Check user_recommendation_responses
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_recommendation_responses'"
            )
            result = await cursor.fetchone()
            if result:
                print("✅ user_recommendation_responses table created")
            else:
                print("❌ user_recommendation_responses table NOT found")

            # Check indexes
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_food_frequency_7d'"
            )
            result = await cursor.fetchone()
            if result:
                print("✅ idx_food_frequency_7d index created")
            else:
                print("❌ idx_food_frequency_7d index NOT found")

            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_recommendations'"
            )
            result = await cursor.fetchone()
            if result:
                print("✅ idx_recommendations index created")
            else:
                print("❌ idx_recommendations index NOT found")

        print("\n✓ Migration test complete!\n")

    asyncio.run(test_migration())

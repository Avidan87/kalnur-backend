"""
Database Migration: Add All Nutrients to Food Frequency Table

Adds carbs, fat, calcium, potassium, zinc columns to user_food_frequency table.

Previously only tracked: iron, protein, calories
Now tracks: ALL 8 nutrients
"""

import aiosqlite
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("kai_database.db")


async def run_migration(db_path: Path = None) -> None:
    """Add nutrient columns to user_food_frequency table."""
    path = db_path or DB_PATH
    logger.info(f"🔄 Adding all nutrient columns to user_food_frequency table")

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # Add missing nutrient columns
        try:
            await db.execute("""
                ALTER TABLE user_food_frequency
                ADD COLUMN avg_carbs_per_serving REAL DEFAULT 0
            """)
            logger.info("✓ Added avg_carbs_per_serving")
        except Exception as e:
            logger.warning(f"Column avg_carbs_per_serving may already exist: {e}")

        try:
            await db.execute("""
                ALTER TABLE user_food_frequency
                ADD COLUMN avg_fat_per_serving REAL DEFAULT 0
            """)
            logger.info("✓ Added avg_fat_per_serving")
        except Exception as e:
            logger.warning(f"Column avg_fat_per_serving may already exist: {e}")

        try:
            await db.execute("""
                ALTER TABLE user_food_frequency
                ADD COLUMN avg_calcium_per_serving REAL DEFAULT 0
            """)
            logger.info("✓ Added avg_calcium_per_serving")
        except Exception as e:
            logger.warning(f"Column avg_calcium_per_serving may already exist: {e}")

        try:
            await db.execute("""
                ALTER TABLE user_food_frequency
                ADD COLUMN avg_potassium_per_serving REAL DEFAULT 0
            """)
            logger.info("✓ Added avg_potassium_per_serving")
        except Exception as e:
            logger.warning(f"Column avg_potassium_per_serving may already exist: {e}")

        try:
            await db.execute("""
                ALTER TABLE user_food_frequency
                ADD COLUMN avg_zinc_per_serving REAL DEFAULT 0
            """)
            logger.info("✓ Added avg_zinc_per_serving")
        except Exception as e:
            logger.warning(f"Column avg_zinc_per_serving may already exist: {e}")

        await db.commit()
        logger.info("✅ All nutrient columns added successfully!")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(run_migration())
    print("\n✅ Migration complete: user_food_frequency now tracks ALL 8 nutrients!\n")

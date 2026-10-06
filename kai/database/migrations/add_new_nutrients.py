"""
Database Migration: Add 8 New Nutrients

Adds the following columns to meal_foods and daily_nutrients tables:
- fiber
- sodium
- magnesium
- vitamin_a
- vitamin_c
- vitamin_d
- vitamin_b12
- folate

Run this ONCE to migrate from 8 nutrients to 16 nutrients.
"""

import asyncio
import aiosqlite
from pathlib import Path


DATABASE_PATH = Path("kai_database.db")

# New nutrient columns to add
NEW_NUTRIENTS = [
    "fiber",
    "sodium",
    "magnesium",
    "vitamin_a",
    "vitamin_c",
    "vitamin_d",
    "vitamin_b12",
    "folate"
]


async def check_column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]
    return column in column_names


async def migrate():
    """Add new nutrient columns to database tables."""

    if not DATABASE_PATH.exists():
        print(f"Database not found at {DATABASE_PATH}")
        print("Run the app first to create the database, then run this migration.")
        return False

    print("=" * 50)
    print("DATABASE MIGRATION: Adding 8 New Nutrients")
    print("=" * 50)

    async with aiosqlite.connect(DATABASE_PATH) as db:

        # ============================================
        # Step 1: Add columns to meal_foods table
        # ============================================
        print("\n[1/2] Adding columns to meal_foods table...")

        for nutrient in NEW_NUTRIENTS:
            if await check_column_exists(db, "meal_foods", nutrient):
                print(f"  - {nutrient}: already exists, skipping")
            else:
                await db.execute(f"""
                    ALTER TABLE meal_foods
                    ADD COLUMN {nutrient} REAL DEFAULT 0.0
                """)
                print(f"  - {nutrient}: added")

        # ============================================
        # Step 2: Add columns to daily_nutrients table
        # ============================================
        print("\n[2/2] Adding columns to daily_nutrients table...")

        for nutrient in NEW_NUTRIENTS:
            column_name = f"total_{nutrient}"
            if await check_column_exists(db, "daily_nutrients", column_name):
                print(f"  - {column_name}: already exists, skipping")
            else:
                await db.execute(f"""
                    ALTER TABLE daily_nutrients
                    ADD COLUMN {column_name} REAL DEFAULT 0.0
                """)
                print(f"  - {column_name}: added")

        await db.commit()

        # ============================================
        # Verify migration
        # ============================================
        print("\n" + "=" * 50)
        print("VERIFICATION")
        print("=" * 50)

        # Check meal_foods
        cursor = await db.execute("PRAGMA table_info(meal_foods)")
        columns = await cursor.fetchall()
        meal_foods_cols = [col[1] for col in columns]
        print(f"\nmeal_foods columns ({len(meal_foods_cols)}):")
        nutrient_cols = [c for c in meal_foods_cols if c not in ['id', 'meal_id', 'food_name', 'food_id', 'portion_grams', 'confidence']]
        print(f"  Nutrients: {nutrient_cols}")

        # Check daily_nutrients
        cursor = await db.execute("PRAGMA table_info(daily_nutrients)")
        columns = await cursor.fetchall()
        daily_cols = [col[1] for col in columns]
        print(f"\ndaily_nutrients columns ({len(daily_cols)}):")
        total_cols = [c for c in daily_cols if c.startswith('total_')]
        print(f"  Totals: {total_cols}")

        print("\n" + "=" * 50)
        print("MIGRATION COMPLETE!")
        print("=" * 50)

        return True


async def rollback():
    """
    Note: SQLite doesn't support DROP COLUMN easily.
    To rollback, you'd need to recreate the tables.
    This is left as a manual operation if needed.
    """
    print("Rollback not implemented - SQLite doesn't support DROP COLUMN.")
    print("To rollback, manually recreate the tables or restore from backup.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        asyncio.run(rollback())
    else:
        asyncio.run(migrate())

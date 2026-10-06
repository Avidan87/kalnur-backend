"""
Database Migration: Expand Health Goals to 8 Options

Updates the user_health table CHECK constraint to support all 8 health goals:
- lose_weight, gain_muscle, maintain_weight, general_wellness (original 4)
- pregnancy, heart_health, energy_boost, bone_health (new 4)

SQLite doesn't support ALTER CONSTRAINT, so we need to recreate the table.

Run this migration to update existing database.
"""

import asyncio
import aiosqlite
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Database file location (same as main db_setup.py)
DB_PATH = Path("kai_database.db")


async def run_migration(db_path: Path = None) -> None:
    """
    Run migration to expand health_goals to 8 options.

    Args:
        db_path: Optional custom database path
    """
    path = db_path or DB_PATH
    logger.info(f"🔄 Running health goals expansion migration on: {path}")

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = OFF")

        # Check if migration is needed by looking at the current constraint
        # We'll do this by trying to see the table schema
        cursor = await db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_health'"
        )
        row = await cursor.fetchone()

        if not row:
            logger.info("✓ user_health table doesn't exist yet - no migration needed")
            return

        current_schema = row[0]

        # Check if new goals are already in the constraint
        if "pregnancy" in current_schema:
            logger.info("✓ Migration already applied - health_goals already includes new goals")
            return

        logger.info("📋 Current schema needs update - recreating table with expanded goals")

        # Step 1: Rename old table
        await db.execute("ALTER TABLE user_health RENAME TO user_health_old")

        # Step 2: Create new table with expanded constraint (matching original schema)
        await db.execute("""
            CREATE TABLE user_health (
                user_id TEXT PRIMARY KEY,

                -- Body Metrics (required for BMR/TDEE calculation)
                weight_kg REAL,
                height_cm REAL,

                -- Lifestyle & Goals
                activity_level TEXT CHECK(activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')),
                health_goals TEXT CHECK(health_goals IN ('lose_weight', 'gain_muscle', 'maintain_weight', 'general_wellness', 'pregnancy', 'heart_health', 'energy_boost', 'bone_health')),
                target_weight_kg REAL,

                -- Calorie Goals (calculated and custom)
                calculated_calorie_goal REAL,
                custom_calorie_goal REAL,
                active_calorie_goal REAL,

                -- Other
                dietary_restrictions TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # Step 3: Copy data from old table
        await db.execute("""
            INSERT INTO user_health (
                user_id, weight_kg, height_cm, activity_level, health_goals,
                target_weight_kg, calculated_calorie_goal, custom_calorie_goal,
                active_calorie_goal, dietary_restrictions, updated_at
            )
            SELECT
                user_id, weight_kg, height_cm, activity_level, health_goals,
                target_weight_kg, calculated_calorie_goal, custom_calorie_goal,
                active_calorie_goal, dietary_restrictions, updated_at
            FROM user_health_old
        """)

        # Step 4: Drop old table
        await db.execute("DROP TABLE user_health_old")

        # Re-enable foreign keys
        await db.execute("PRAGMA foreign_keys = ON")

        await db.commit()
        logger.info("✅ Migration complete - health_goals now supports 8 options")


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("\n" + "=" * 60)
    print("HEALTH GOALS EXPANSION MIGRATION")
    print("=" * 60)
    print("\nExpanding health_goals to include:")
    print("  Original: lose_weight, gain_muscle, maintain_weight, general_wellness")
    print("  New: pregnancy, heart_health, energy_boost, bone_health")
    print()

    asyncio.run(run_migration())

    print("\n✅ Migration complete!\n")

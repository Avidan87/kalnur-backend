"""
Database Migration: Replace vitamin_a with potassium

This migration:
1. Adds potassium columns to all relevant tables
2. Sets all potassium values to 0 (zero-out approach)
3. Drops vitamin_a columns from all tables

Tables affected:
- meal_foods (vitamin_a → potassium)
- daily_nutrients (total_vitamin_a → total_potassium)
- user_nutrition_stats (week1_avg_vitamin_a, week2_avg_vitamin_a, vitamin_a_trend)

Run this ONCE to migrate from vitamin A tracking to potassium tracking.
"""

import sqlite3
import sys
from pathlib import Path

# Set UTF-8 encoding for console output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DATABASE_PATH = Path("kai_database.db")


def migrate():
    """Execute the migration"""

    if not DATABASE_PATH.exists():
        print(f"❌ Database not found at {DATABASE_PATH}")
        print("   Please ensure the database exists before running migration.")
        return False

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        print("=" * 60)
        print("🔄 Database Migration: vitamin_a → potassium")
        print("=" * 60)

        # Step 1: Add potassium columns
        print("\n📝 Step 1: Adding potassium columns...")

        # meal_foods table
        try:
            cursor.execute("ALTER TABLE meal_foods ADD COLUMN potassium REAL DEFAULT 0")
            print("  ✓ Added potassium column to meal_foods")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  ⚠️  potassium column already exists in meal_foods")
            else:
                raise

        # daily_nutrients table
        try:
            cursor.execute("ALTER TABLE daily_nutrients ADD COLUMN total_potassium REAL DEFAULT 0")
            print("  ✓ Added total_potassium column to daily_nutrients")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  ⚠️  total_potassium column already exists in daily_nutrients")
            else:
                raise

        # user_nutrition_stats table (week1, week2, trend)
        try:
            cursor.execute("ALTER TABLE user_nutrition_stats ADD COLUMN week1_avg_potassium REAL DEFAULT 0")
            print("  ✓ Added week1_avg_potassium column to user_nutrition_stats")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  ⚠️  week1_avg_potassium column already exists in user_nutrition_stats")
            else:
                raise

        try:
            cursor.execute("ALTER TABLE user_nutrition_stats ADD COLUMN week2_avg_potassium REAL DEFAULT 0")
            print("  ✓ Added week2_avg_potassium column to user_nutrition_stats")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  ⚠️  week2_avg_potassium column already exists in user_nutrition_stats")
            else:
                raise

        try:
            cursor.execute("ALTER TABLE user_nutrition_stats ADD COLUMN potassium_trend TEXT DEFAULT 'stable'")
            print("  ✓ Added potassium_trend column to user_nutrition_stats")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  ⚠️  potassium_trend column already exists in user_nutrition_stats")
            else:
                raise

        # Step 2: Set all potassium values to 0 (zero-out approach)
        print("\n📝 Step 2: Initializing potassium values to 0...")

        cursor.execute("UPDATE meal_foods SET potassium = 0")
        cursor.execute("UPDATE daily_nutrients SET total_potassium = 0")
        cursor.execute("UPDATE user_nutrition_stats SET week1_avg_potassium = 0, week2_avg_potassium = 0, potassium_trend = 'stable'")

        print("  ✓ All potassium values initialized to 0")

        # Step 3: Drop vitamin_a columns
        print("\n📝 Step 3: Removing vitamin_a columns...")

        # SQLite doesn't support DROP COLUMN directly (before version 3.35.0)
        # We need to use the recreate table approach for each table

        # For meal_foods table
        print("  🔄 Migrating meal_foods table...")
        cursor.execute("""
            CREATE TABLE meal_foods_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meal_id TEXT NOT NULL,
                food_name TEXT NOT NULL,
                food_id TEXT,
                portion_grams REAL NOT NULL,
                calories REAL DEFAULT 0,
                protein REAL DEFAULT 0,
                carbohydrates REAL DEFAULT 0,
                fat REAL DEFAULT 0,
                iron REAL DEFAULT 0,
                calcium REAL DEFAULT 0,
                potassium REAL DEFAULT 0,
                zinc REAL DEFAULT 0,
                confidence REAL DEFAULT 1.0,
                FOREIGN KEY (meal_id) REFERENCES meals (meal_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            INSERT INTO meal_foods_new
            SELECT id, meal_id, food_name, food_id, portion_grams,
                   calories, protein, carbohydrates, fat, iron, calcium,
                   potassium, zinc, confidence
            FROM meal_foods
        """)
        cursor.execute("DROP TABLE meal_foods")
        cursor.execute("ALTER TABLE meal_foods_new RENAME TO meal_foods")
        print("  ✓ Migrated meal_foods table")

        # For daily_nutrients table
        print("  🔄 Migrating daily_nutrients table...")
        cursor.execute("""
            CREATE TABLE daily_nutrients_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                total_calories REAL DEFAULT 0,
                total_protein REAL DEFAULT 0,
                total_carbohydrates REAL DEFAULT 0,
                total_fat REAL DEFAULT 0,
                total_iron REAL DEFAULT 0,
                total_calcium REAL DEFAULT 0,
                total_potassium REAL DEFAULT 0,
                total_zinc REAL DEFAULT 0,
                meal_count INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date)
            )
        """)
        cursor.execute("""
            INSERT INTO daily_nutrients_new
            SELECT id, user_id, date, total_calories, total_protein, total_carbohydrates,
                   total_fat, total_iron, total_calcium, total_potassium, total_zinc,
                   meal_count, updated_at
            FROM daily_nutrients
        """)
        cursor.execute("DROP TABLE daily_nutrients")
        cursor.execute("ALTER TABLE daily_nutrients_new RENAME TO daily_nutrients")
        print("  ✓ Migrated daily_nutrients table")

        # For user_nutrition_stats table
        print("  🔄 Migrating user_nutrition_stats table...")
        cursor.execute("""
            CREATE TABLE user_nutrition_stats_new (
                user_id TEXT PRIMARY KEY,
                total_meals_logged INTEGER DEFAULT 0,
                account_age_days INTEGER DEFAULT 0,
                learning_phase_complete BOOLEAN DEFAULT 0,
                current_logging_streak INTEGER DEFAULT 0,
                longest_logging_streak INTEGER DEFAULT 0,
                last_logged_date TEXT,
                week1_avg_calories REAL DEFAULT 0,
                week1_avg_protein REAL DEFAULT 0,
                week1_avg_carbs REAL DEFAULT 0,
                week1_avg_fat REAL DEFAULT 0,
                week1_avg_iron REAL DEFAULT 0,
                week1_avg_calcium REAL DEFAULT 0,
                week1_avg_potassium REAL DEFAULT 0,
                week1_avg_zinc REAL DEFAULT 0,
                week2_avg_calories REAL DEFAULT 0,
                week2_avg_protein REAL DEFAULT 0,
                week2_avg_carbs REAL DEFAULT 0,
                week2_avg_fat REAL DEFAULT 0,
                week2_avg_iron REAL DEFAULT 0,
                week2_avg_calcium REAL DEFAULT 0,
                week2_avg_potassium REAL DEFAULT 0,
                week2_avg_zinc REAL DEFAULT 0,
                calories_trend TEXT DEFAULT 'stable',
                protein_trend TEXT DEFAULT 'stable',
                carbs_trend TEXT DEFAULT 'stable',
                fat_trend TEXT DEFAULT 'stable',
                iron_trend TEXT DEFAULT 'stable',
                calcium_trend TEXT DEFAULT 'stable',
                potassium_trend TEXT DEFAULT 'stable',
                zinc_trend TEXT DEFAULT 'stable',
                last_calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            INSERT INTO user_nutrition_stats_new
            SELECT user_id, total_meals_logged, account_age_days, learning_phase_complete,
                   current_logging_streak, longest_logging_streak, last_logged_date,
                   week1_avg_calories, week1_avg_protein, week1_avg_carbs, week1_avg_fat,
                   week1_avg_iron, week1_avg_calcium, week1_avg_potassium, week1_avg_zinc,
                   week2_avg_calories, week2_avg_protein, week2_avg_carbs, week2_avg_fat,
                   week2_avg_iron, week2_avg_calcium, week2_avg_potassium, week2_avg_zinc,
                   calories_trend, protein_trend, carbs_trend, fat_trend,
                   iron_trend, calcium_trend, potassium_trend, zinc_trend,
                   last_calculated_at
            FROM user_nutrition_stats
        """)
        cursor.execute("DROP TABLE user_nutrition_stats")
        cursor.execute("ALTER TABLE user_nutrition_stats_new RENAME TO user_nutrition_stats")
        print("  ✓ Migrated user_nutrition_stats table")

        # Commit all changes
        conn.commit()

        print("\n" + "=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)
        print("\n📊 Summary:")
        print("  • Added potassium columns to 3 tables")
        print("  • Removed vitamin_a columns from 3 tables")
        print("  • All existing data preserved (potassium values set to 0)")
        print("\n🎉 KAI now tracks potassium instead of vitamin A!")

        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def rollback():
    """
    Rollback migration (restore vitamin_a columns)

    WARNING: This will lose all potassium data!
    Only use if you need to revert the migration.
    """
    print("⚠️  Rollback not implemented yet.")
    print("   If you need to rollback, restore from backup.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback()
    else:
        success = migrate()
        sys.exit(0 if success else 1)

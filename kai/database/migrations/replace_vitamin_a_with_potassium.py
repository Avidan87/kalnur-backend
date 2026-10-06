"""
Database Migration: Replace vitamin_a with potassium

This migration:
1. Adds potassium column to all relevant tables
2. Sets all potassium values to 0 (zero-out approach)
3. Drops vitamin_a column from all tables

Tables affected:
- meals
- food_frequency
- user_stats (week1_avg_vitamin_a → week1_avg_potassium)
- daily_nutrition_cache

Run this ONCE to migrate from vitamin A tracking to potassium tracking.
"""

import sqlite3
import sys
from pathlib import Path

# Set UTF-8 encoding for console output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DATABASE_PATH = Path("kai.db")


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

        tables_to_update = [
            ("meals", "potassium REAL DEFAULT 0"),
            ("food_frequency", "potassium REAL DEFAULT 0"),
            ("user_stats", "week1_avg_potassium REAL DEFAULT 0"),
            ("daily_nutrition_cache", "potassium REAL DEFAULT 0"),
        ]

        for table_name, column_def in tables_to_update:
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_def}")
                print(f"  ✓ Added potassium column to {table_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"  ⚠️  potassium column already exists in {table_name}")
                else:
                    raise

        # Step 2: Set all potassium values to 0 (zero-out approach)
        print("\n📝 Step 2: Initializing potassium values to 0...")

        cursor.execute("UPDATE meals SET potassium = 0")
        cursor.execute("UPDATE food_frequency SET potassium = 0")
        cursor.execute("UPDATE user_stats SET week1_avg_potassium = 0")
        cursor.execute("UPDATE daily_nutrition_cache SET potassium = 0")

        print("  ✓ All potassium values initialized to 0")

        # Step 3: Drop vitamin_a columns
        print("\n📝 Step 3: Removing vitamin_a columns...")

        # SQLite doesn't support DROP COLUMN directly
        # We need to use the recreate table approach for each table

        # For meals table
        print("  🔄 Migrating meals table...")
        cursor.execute("""
            CREATE TABLE meals_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                food_name TEXT NOT NULL,
                portion_grams REAL NOT NULL,
                calories REAL DEFAULT 0,
                protein REAL DEFAULT 0,
                carbohydrates REAL DEFAULT 0,
                fat REAL DEFAULT 0,
                iron REAL DEFAULT 0,
                calcium REAL DEFAULT 0,
                potassium REAL DEFAULT 0,
                zinc REAL DEFAULT 0,
                meal_type TEXT,
                notes TEXT
            )
        """)
        cursor.execute("""
            INSERT INTO meals_new
            SELECT id, user_id, timestamp, food_name, portion_grams,
                   calories, protein, carbohydrates, fat, iron, calcium,
                   potassium, zinc, meal_type, notes
            FROM meals
        """)
        cursor.execute("DROP TABLE meals")
        cursor.execute("ALTER TABLE meals_new RENAME TO meals")
        print("  ✓ Migrated meals table")

        # For food_frequency table
        print("  🔄 Migrating food_frequency table...")
        cursor.execute("""
            CREATE TABLE food_frequency_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                food_name TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                last_eaten DATETIME DEFAULT CURRENT_TIMESTAMP,
                avg_portion_grams REAL DEFAULT 0,
                total_calories REAL DEFAULT 0,
                total_protein REAL DEFAULT 0,
                total_carbohydrates REAL DEFAULT 0,
                total_fat REAL DEFAULT 0,
                total_iron REAL DEFAULT 0,
                total_calcium REAL DEFAULT 0,
                potassium REAL DEFAULT 0,
                total_zinc REAL DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT INTO food_frequency_new
            SELECT id, user_id, food_name, count, last_eaten, avg_portion_grams,
                   total_calories, total_protein, total_carbohydrates, total_fat,
                   total_iron, total_calcium, potassium, total_zinc
            FROM food_frequency
        """)
        cursor.execute("DROP TABLE food_frequency")
        cursor.execute("ALTER TABLE food_frequency_new RENAME TO food_frequency")
        print("  ✓ Migrated food_frequency table")

        # For user_stats table
        print("  🔄 Migrating user_stats table...")
        cursor.execute("""
            CREATE TABLE user_stats_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                total_meals_logged INTEGER DEFAULT 0,
                current_logging_streak INTEGER DEFAULT 0,
                longest_logging_streak INTEGER DEFAULT 0,
                last_meal_logged DATETIME,
                learning_phase_complete BOOLEAN DEFAULT 0,
                week1_avg_calories REAL DEFAULT 0,
                week1_avg_protein REAL DEFAULT 0,
                week1_avg_carbs REAL DEFAULT 0,
                week1_avg_fat REAL DEFAULT 0,
                week1_avg_iron REAL DEFAULT 0,
                week1_avg_calcium REAL DEFAULT 0,
                week1_avg_potassium REAL DEFAULT 0,
                week1_avg_zinc REAL DEFAULT 0,
                calories_trend TEXT DEFAULT 'stable',
                protein_trend TEXT DEFAULT 'stable',
                carbs_trend TEXT DEFAULT 'stable',
                fat_trend TEXT DEFAULT 'stable',
                iron_trend TEXT DEFAULT 'stable',
                calcium_trend TEXT DEFAULT 'stable',
                potassium_trend TEXT DEFAULT 'stable',
                zinc_trend TEXT DEFAULT 'stable',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT INTO user_stats_new
            SELECT id, user_id, total_meals_logged, current_logging_streak,
                   longest_logging_streak, last_meal_logged, learning_phase_complete,
                   week1_avg_calories, week1_avg_protein, week1_avg_carbs, week1_avg_fat,
                   week1_avg_iron, week1_avg_calcium, week1_avg_potassium, week1_avg_zinc,
                   calories_trend, protein_trend, carbs_trend, fat_trend,
                   iron_trend, calcium_trend, potassium_trend, zinc_trend,
                   updated_at
            FROM user_stats
        """)
        cursor.execute("DROP TABLE user_stats")
        cursor.execute("ALTER TABLE user_stats_new RENAME TO user_stats")
        print("  ✓ Migrated user_stats table")

        # For daily_nutrition_cache table
        print("  🔄 Migrating daily_nutrition_cache table...")
        cursor.execute("""
            CREATE TABLE daily_nutrition_cache_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date DATE NOT NULL,
                calories REAL DEFAULT 0,
                protein REAL DEFAULT 0,
                carbohydrates REAL DEFAULT 0,
                fat REAL DEFAULT 0,
                iron REAL DEFAULT 0,
                calcium REAL DEFAULT 0,
                potassium REAL DEFAULT 0,
                zinc REAL DEFAULT 0,
                meal_count INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date)
            )
        """)
        cursor.execute("""
            INSERT INTO daily_nutrition_cache_new
            SELECT id, user_id, date, calories, protein, carbohydrates, fat,
                   iron, calcium, potassium, zinc, meal_count, updated_at
            FROM daily_nutrition_cache
        """)
        cursor.execute("DROP TABLE daily_nutrition_cache")
        cursor.execute("ALTER TABLE daily_nutrition_cache_new RENAME TO daily_nutrition_cache")
        print("  ✓ Migrated daily_nutrition_cache table")

        # Commit all changes
        conn.commit()

        print("\n" + "=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)
        print("\n📊 Summary:")
        print("  • Added potassium columns to 4 tables")
        print("  • Removed vitamin_a columns from 4 tables")
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

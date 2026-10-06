"""
Migration: Remove Unused Tables

Removes two tables that were defined but never integrated into the application:
- user_food_frequency (food frequency tracking - never called)
- user_recommendation_responses (recommendation system - never implemented)

SAFETY: These tables have no active usage in the codebase.
Run this script ONLY AFTER verifying no production data exists in these tables.
"""

import logging
from kai.database.db_setup import get_supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def remove_unused_tables():
    """
    Drop unused tables from Supabase.

    Tables being removed:
    1. user_food_frequency
    2. user_recommendation_responses

    These tables were created in previous migrations but never integrated
    into the application workflow.
    """
    client = get_supabase()

    print("\n" + "="*70)
    print("MIGRATION: Remove Unused Tables")
    print("="*70 + "\n")

    # Check if tables have any data before deletion
    tables_to_remove = [
        "user_food_frequency",
        "user_recommendation_responses"
    ]

    for table in tables_to_remove:
        try:
            result = client.table(table).select("*", count="exact").limit(0).execute()
            count = result.count if hasattr(result, 'count') else 0

            if count > 0:
                logger.warning(f"⚠️  Table '{table}' contains {count} rows!")
                response = input(f"   Continue with deletion? (yes/no): ")
                if response.lower() != 'yes':
                    logger.info(f"   Skipping {table}")
                    continue
            else:
                logger.info(f"✓ Table '{table}' is empty (0 rows)")

        except Exception as e:
            logger.warning(f"Could not check {table}: {e}")

    print("\n" + "-"*70)
    print("EXECUTING SQL DROP STATEMENTS")
    print("-"*70 + "\n")

    sql_statements = """
    -- Drop user_food_frequency table
    DROP TABLE IF EXISTS user_food_frequency CASCADE;

    -- Drop user_recommendation_responses table
    DROP TABLE IF EXISTS user_recommendation_responses CASCADE;

    -- Drop related indexes (if any)
    DROP INDEX IF EXISTS idx_food_frequency_7d;
    DROP INDEX IF EXISTS idx_recommendations;
    """

    print("SQL to execute in Supabase SQL Editor:")
    print("-"*70)
    print(sql_statements)
    print("-"*70)

    print("\n⚠️  IMPORTANT: Execute the SQL above manually in Supabase SQL Editor")
    print("   Reason: supabase-py doesn't support DDL operations (DROP TABLE)")
    print("   Location: Supabase Dashboard → SQL Editor → New Query\n")

    print("✅ After running SQL, you can safely delete these functions from stats_operations.py:")
    print("   - update_food_frequency()")
    print("   - reset_weekly_food_frequency()")
    print("   - get_user_food_frequency()")
    print("   - log_recommendation()")
    print("   - mark_recommendation_followed()")
    print("   - get_recommendation_stats()")

    print("\n" + "="*70)
    print("MIGRATION COMPLETE (Pending SQL Execution)")
    print("="*70 + "\n")


if __name__ == "__main__":
    remove_unused_tables()

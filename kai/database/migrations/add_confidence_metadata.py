"""
Add confidence metadata to meal_foods table.

Adds three columns to track detection quality:
- vision_confidence: How confident the Vision Agent was (0.0-1.0)
- knowledge_similarity: How well the Knowledge Agent matched the food (0.0-1.0)
- portion_validation: Whether the portion is within reasonable bounds (ok/low/high)

This enables:
1. Transparency when detections are uncertain
2. Debugging accuracy issues
3. Analytics on detection quality over time

Run: python -m kai.database.migrations.add_confidence_metadata
"""

import asyncio
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()


async def run_migration():
    """Add confidence metadata columns to meal_foods table."""

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

    supabase = create_client(supabase_url, supabase_key)

    print("🔧 Adding confidence metadata columns to meal_foods table...")

    # SQL to add three new columns
    migration_sql = """
    -- Add vision confidence (0.0-1.0, default 1.0 for existing rows)
    ALTER TABLE meal_foods
    ADD COLUMN IF NOT EXISTS vision_confidence REAL DEFAULT 1.0;

    -- Add knowledge similarity (0.0-1.0, default 1.0 for existing rows)
    ALTER TABLE meal_foods
    ADD COLUMN IF NOT EXISTS knowledge_similarity REAL DEFAULT 1.0;

    -- Add portion validation flag (ok/low/high, default 'ok' for existing rows)
    ALTER TABLE meal_foods
    ADD COLUMN IF NOT EXISTS portion_validation TEXT DEFAULT 'ok';

    -- Add check constraints
    ALTER TABLE meal_foods
    ADD CONSTRAINT vision_confidence_range CHECK (vision_confidence >= 0.0 AND vision_confidence <= 1.0);

    ALTER TABLE meal_foods
    ADD CONSTRAINT knowledge_similarity_range CHECK (knowledge_similarity >= 0.0 AND knowledge_similarity <= 1.0);

    ALTER TABLE meal_foods
    ADD CONSTRAINT portion_validation_values CHECK (portion_validation IN ('ok', 'low', 'high'));
    """

    try:
        # Supabase doesn't support exec_sql by default
        # Use PostgREST raw SQL execution via the REST API
        import requests

        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
        }

        # Split migration into individual statements (Supabase REST API limitation)
        statements = [
            "ALTER TABLE meal_foods ADD COLUMN IF NOT EXISTS vision_confidence REAL DEFAULT 1.0;",
            "ALTER TABLE meal_foods ADD COLUMN IF NOT EXISTS knowledge_similarity REAL DEFAULT 1.0;",
            "ALTER TABLE meal_foods ADD COLUMN IF NOT EXISTS portion_validation TEXT DEFAULT 'ok';",
            "ALTER TABLE meal_foods ADD CONSTRAINT vision_confidence_range CHECK (vision_confidence >= 0.0 AND vision_confidence <= 1.0);",
            "ALTER TABLE meal_foods ADD CONSTRAINT knowledge_similarity_range CHECK (knowledge_similarity >= 0.0 AND knowledge_similarity <= 1.0);",
            "ALTER TABLE meal_foods ADD CONSTRAINT portion_validation_values CHECK (portion_validation IN ('ok', 'low', 'high'));",
        ]

        print("⚠️ This script requires manual SQL execution.")
        print("\n📝 Run this SQL in Supabase SQL Editor (Dashboard → SQL Editor):\n")
        print(migration_sql)
        print("\nOr copy-paste each statement above into the SQL Editor.")

    except Exception as e:
        print(f"❌ Migration prep failed: {e}")
        print("\n📝 Manual SQL (run this in Supabase SQL Editor):")
        print(migration_sql)
        raise


if __name__ == "__main__":
    asyncio.run(run_migration())

"""
Migration: Add show_sugar column to user_health table

Adds a boolean preference column so the AI coach (Kally) can adjust
sugar-impact coaching based on whether the user has sugar tracking enabled.

Run with:
    python -m kai.database.migrations.add_show_sugar_preference
"""

import asyncio
import logging

from kai.database.db_setup import get_supabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SQL = """
ALTER TABLE user_health ADD COLUMN IF NOT EXISTS show_sugar BOOLEAN DEFAULT FALSE;
"""


async def run_migration() -> None:
    """Add show_sugar column to user_health table."""
    logger.info("Running migration: add show_sugar to user_health…")

    try:
        client = get_supabase()
        # Use the Supabase rpc / postgrest raw SQL endpoint
        client.rpc("run_sql", {"query": SQL}).execute()
        logger.info("✓ Migration complete: show_sugar column added (or already existed).")
    except Exception as e:
        # Supabase JS-style clients may not expose run_sql.
        # Log clearly so the developer can run the SQL manually if needed.
        logger.error(
            f"✗ Migration failed: {e}\n"
            "If the Supabase client does not support raw SQL via rpc('run_sql', …), "
            "run the following SQL manually in the Supabase dashboard:\n\n"
            f"    {SQL.strip()}\n"
        )
        raise


if __name__ == "__main__":
    asyncio.run(run_migration())

"""
Missing Foods Operations

Tracks food names that users add during real-time analysis
but are not found in the Kalnur knowledge base.

Avidan reviews this table, researches nutrition data, and adds to the KB.
"""

import logging
from typing import Optional
from .db_setup import get_supabase

logger = logging.getLogger(__name__)


async def log_missing_food(food_name: str, user_id: Optional[str] = None) -> bool:
    """
    Log a food that was not found in the knowledge base.

    If the food already exists in the table, increments requested_count
    and appends user_id to user_ids array. If it's new, creates a fresh row.

    Returns:
        True if this is the FIRST TIME this specific user has flagged this food
        (i.e. Email 1 should be sent). False otherwise.
    """
    if not food_name or not food_name.strip():
        return False

    food_name_clean = food_name.strip().lower()

    try:
        supabase = get_supabase()

        # Check if this food already exists (case-insensitive)
        existing = (
            supabase.table("missing_foods")
            .select("id, requested_count, unique_users, user_ids, notified_user_ids")
            .ilike("food_name", food_name_clean)
            .limit(1)
            .execute()
        )

        if existing.data:
            row = existing.data[0]
            existing_user_ids = row.get("user_ids") or []
            notified_user_ids = row.get("notified_user_ids") or []

            # Has this user already been notified? If so, don't send Email 1 again
            already_notified = user_id and user_id in notified_user_ids
            is_first_time_for_user = user_id and user_id not in existing_user_ids

            new_count = row["requested_count"] + 1
            new_unique = row["unique_users"] + (1 if is_first_time_for_user else 0)
            new_user_ids = list(set(existing_user_ids + ([user_id] if user_id else [])))

            supabase.table("missing_foods").update({
                "requested_count": new_count,
                "unique_users": new_unique,
                "user_ids": new_user_ids,
                "last_seen": "now()",
            }).eq("id", row["id"]).execute()

            logger.info("📋 Missing food count updated: '%s' (×%d)", food_name_clean, new_count)
            return bool(is_first_time_for_user and not already_notified)

        else:
            # First time this food is requested — create new row
            supabase.table("missing_foods").insert({
                "food_name": food_name_clean,
                "requested_count": 1,
                "unique_users": 1 if user_id else 0,
                "user_ids": [user_id] if user_id else [],
                "notified_user_ids": [],
                "status": "pending",
            }).execute()

            logger.info("📋 New missing food logged: '%s'", food_name_clean)
            return True  # Always send Email 1 for brand new missing food request

    except Exception as e:
        # Never fail the main flow because of missing foods logging
        logger.warning("⚠️ Failed to log missing food '%s': %s", food_name, e)
        return False


async def mark_user_notified(food_name: str, user_id: str) -> None:
    """Mark that Email 1 has been sent to this user for this food."""
    try:
        supabase = get_supabase()
        existing = (
            supabase.table("missing_foods")
            .select("id, notified_user_ids")
            .ilike("food_name", food_name.strip().lower())
            .limit(1)
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            updated = list(set((row.get("notified_user_ids") or []) + [user_id]))
            supabase.table("missing_foods").update({
                "notified_user_ids": updated
            }).eq("id", row["id"]).execute()
    except Exception as e:
        logger.warning("⚠️ Failed to mark user notified for '%s': %s", food_name, e)


async def get_missing_foods(status: Optional[str] = None, limit: int = 50):
    """
    Retrieve missing foods ordered by most requested.

    Args:
        status: Filter by status ('pending', 'researching', 'added') or None for all
        limit: Max rows to return

    Returns:
        List of missing food rows
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("missing_foods")
            .select("*")
            .order("requested_count", desc=True)
            .limit(limit)
        )

        if status:
            query = query.eq("status", status)

        result = query.execute()
        return result.data or []

    except Exception as e:
        logger.error("❌ Failed to get missing foods: %s", e)
        return []


async def update_missing_food_status(food_name: str, status: str) -> bool:
    """
    Update the status of a missing food entry.

    Args:
        food_name: The food name to update
        status: New status ('pending', 'researching', 'added')

    Returns:
        True if updated successfully
    """
    try:
        supabase = get_supabase()
        supabase.table("missing_foods").update({
            "status": status
        }).ilike("food_name", food_name.strip().lower()).execute()
        return True
    except Exception as e:
        logger.error("❌ Failed to update missing food status: %s", e)
        return False

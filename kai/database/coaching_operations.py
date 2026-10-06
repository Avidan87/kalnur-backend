"""
Coaching Database Operations - Supabase

CRUD operations for user coaching context (persistent coaching memory).
Stores barrier, food habits, and motivation score collected during
the coaching flow — used to personalize KAI's coaching long-term.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .db_setup import get_supabase

logger = logging.getLogger(__name__)


async def get_user_coaching(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch user's coaching profile.

    Args:
        user_id: User identifier

    Returns:
        Dict with coaching data or None if not found
    """
    client = get_supabase()

    try:
        result = client.table("user_coaching") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        if not result.data:
            return None

        return result.data[0]

    except Exception as e:
        logger.error(f"Failed to fetch user coaching: {e}")
        return None


async def is_coaching_complete(user_id: str) -> bool:
    """
    Check if user has completed the coaching flow.

    Args:
        user_id: User identifier

    Returns:
        True if coaching is complete, False otherwise
    """
    coaching = await get_user_coaching(user_id)
    if not coaching:
        return False
    return coaching.get("coaching_complete", False)


async def save_user_coaching(
    user_id: str,
    barrier: Optional[str] = None,
    food_habits: Optional[str] = None,
    favourite_meal: Optional[str] = None,
    motivation_score: Optional[int] = None,
) -> bool:
    """
    Save or update user's coaching answers (upsert).

    Args:
        user_id: User identifier
        barrier: User's biggest challenge (goal-specific) — Q1
        food_habits: User's eating habits answer — Q2
        favourite_meal: User's favourite Nigerian meal — Q3
        motivation_score: Self-rated motivation 1-10 — Q4

    Returns:
        True if saved successfully
    """
    client = get_supabase()

    try:
        data: Dict[str, Any] = {"user_id": user_id}
        if barrier is not None:
            data["barrier"] = barrier
        if food_habits is not None:
            data["food_habits"] = food_habits
        if favourite_meal is not None:
            data["favourite_meal"] = favourite_meal
        if motivation_score is not None:
            data["motivation_score"] = motivation_score

        client.table("user_coaching").upsert(data).execute()
        logger.info(f"✓ Saved coaching data for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to save user coaching: {e}")
        return False


async def reset_coaching_step(user_id: str, step: str) -> bool:
    """
    Reset (null out) a specific coaching answer so the user can re-answer it.
    Used when the user goes back during the coaching flow.

    Args:
        user_id: User identifier
        step: One of "barrier", "food_habits", "motivation_score"

    Returns:
        True if reset successfully
    """
    valid_steps = {"barrier", "food_habits", "motivation_score"}
    if step not in valid_steps:
        logger.warning(f"Invalid coaching step to reset: {step}")
        return False

    client = get_supabase()
    try:
        client.table("user_coaching") \
            .update({step: None}) \
            .eq("user_id", user_id) \
            .execute()
        logger.info(f"✓ Reset coaching step '{step}' for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to reset coaching step: {e}")
        return False


async def reset_coaching_full(user_id: str) -> bool:
    """
    Fully reset the coaching flow for a user — nulls all answers and sets
    coaching_complete back to False so the flow runs again from the start.
    """
    client = get_supabase()
    try:
        client.table("user_coaching").update({
            "barrier": None,
            "food_habits": None,
            "favourite_meal": None,
            "motivation_score": None,
            "coaching_complete": False,
            "completed_at": None,
        }).eq("user_id", user_id).execute()
        logger.info(f"✓ Full coaching reset for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to full-reset coaching: {e}")
        return False


async def mark_coaching_complete(user_id: str) -> bool:
    """
    Mark the coaching flow as complete for this user.
    This ensures the coaching flow never runs again.

    Args:
        user_id: User identifier

    Returns:
        True if updated successfully
    """
    client = get_supabase()

    try:
        client.table("user_coaching").upsert({
            "user_id": user_id,
            "coaching_complete": True,
            "completed_at": datetime.now().isoformat(),
        }).execute()

        logger.info(f"✓ Coaching marked complete for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to mark coaching complete: {e}")
        return False

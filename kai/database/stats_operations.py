"""
User Statistics Operations - Supabase

Functions for managing user nutrition statistics.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from .db_setup import get_supabase

logger = logging.getLogger(__name__)


# =============================================================================
# User Nutrition Stats Operations
# =============================================================================

async def get_user_stats(user_id: str) -> Optional[Dict]:
    """
    Get pre-computed user nutrition statistics.

    Args:
        user_id: User ID

    Returns:
        Dict with user stats or None if not found
    """
    client = get_supabase()

    result = client.table("user_nutrition_stats").select("*").eq("user_id", user_id).execute()

    if not result.data:
        return None

    return result.data[0]


async def initialize_user_stats(user_id: str) -> Dict:
    """
    Initialize stats entry for new user.

    Args:
        user_id: User ID

    Returns:
        Dict with initialized stats
    """
    existing = await get_user_stats(user_id)
    if existing:
        return existing

    client = get_supabase()

    client.table("user_nutrition_stats").insert({
        "user_id": user_id,
    }).execute()

    logger.info(f"✓ Initialized stats for user {user_id}")
    return await get_user_stats(user_id)


async def update_user_stats(
    user_id: str,
    total_meals_logged: Optional[int] = None,
    account_age_days: Optional[int] = None,
    learning_phase_complete: Optional[bool] = None,
    current_logging_streak: Optional[int] = None,
    longest_logging_streak: Optional[int] = None,
    last_logged_date: Optional[str] = None,
    week1_averages: Optional[Dict[str, float]] = None,
    week2_averages: Optional[Dict[str, float]] = None,
    trends: Optional[Dict[str, str]] = None,
) -> Dict:
    """
    Update user nutrition statistics.

    Args:
        user_id: User ID
        total_meals_logged: Total meals logged count
        account_age_days: Account age in days
        learning_phase_complete: Whether learning phase is complete
        current_logging_streak: Current consecutive days logged
        longest_logging_streak: Longest streak ever
        last_logged_date: Last date user logged a meal
        week1_averages: Dict of Week 1 nutrient averages
        week2_averages: Dict of Week 2 nutrient averages
        trends: Dict of nutrient trends

    Returns:
        Updated user stats dict
    """
    # Ensure user stats exist
    await initialize_user_stats(user_id)

    client = get_supabase()

    updates = {"last_calculated_at": datetime.now().isoformat()}

    if total_meals_logged is not None:
        updates["total_meals_logged"] = total_meals_logged
    if account_age_days is not None:
        updates["account_age_days"] = account_age_days
    if learning_phase_complete is not None:
        updates["learning_phase_complete"] = learning_phase_complete
    if current_logging_streak is not None:
        updates["current_logging_streak"] = current_logging_streak
    if longest_logging_streak is not None:
        updates["longest_logging_streak"] = longest_logging_streak
    if last_logged_date is not None:
        updates["last_logged_date"] = last_logged_date

    # Week 1 averages
    if week1_averages:
        for nutrient, value in week1_averages.items():
            updates[f"week1_avg_{nutrient}"] = value

    # Week 2 averages
    if week2_averages:
        for nutrient, value in week2_averages.items():
            updates[f"week2_avg_{nutrient}"] = value

    # Trends
    if trends:
        for nutrient, trend in trends.items():
            updates[f"{nutrient}_trend"] = trend

    client.table("user_nutrition_stats").update(updates).eq("user_id", user_id).execute()

    return await get_user_stats(user_id)


async def get_nutrient_trends(
    user_id: str,
    nutrient: str,
    weeks: int = 4
) -> Optional[Dict]:
    """
    Get trend data for a specific nutrient over time.

    Args:
        user_id: User ID
        nutrient: Nutrient name (e.g., "protein", "folate")
        weeks: Number of weeks to analyze (default: 4)

    Returns:
        Dict with trend data:
        {
            "current_week_avg": 28.5,
            "last_week_avg": 24.2,
            "4_week_avg": 21.3,
            "trend": "improving",  # improving/declining/stable
            "change_pct": 18.5,
            "data_points": 15  # Number of days with data
        }
        Or None if insufficient data
    """
    try:
        client = get_supabase()

        # Get daily totals for past N weeks
        start_date = (datetime.now() - timedelta(weeks=weeks)).date().isoformat()

        result = client.table("daily_nutrients").select(
            f"date, total_{nutrient}"
        ).eq("user_id", user_id).gte("date", start_date).order("date").execute()

        if not result.data or len(result.data) < 3:
            return None  # Need at least 3 data points

        # Extract values
        data = [(row["date"], row.get(f"total_{nutrient}", 0)) for row in result.data]

        # Calculate current week average (last 7 days)
        now = datetime.now().date()
        current_week_start = (now - timedelta(days=7)).isoformat()
        current_week_data = [val for date, val in data if date >= current_week_start]

        if not current_week_data:
            return None

        current_week_avg = sum(current_week_data) / len(current_week_data)

        # Calculate last week average (8-14 days ago)
        last_week_start = (now - timedelta(days=14)).isoformat()
        last_week_end = (now - timedelta(days=8)).isoformat()
        last_week_data = [val for date, val in data if last_week_start <= date < last_week_end]

        if not last_week_data:
            # Not enough historical data, compare to overall average
            all_values = [val for _, val in data]
            overall_avg = sum(all_values) / len(all_values)
            last_week_avg = overall_avg
        else:
            last_week_avg = sum(last_week_data) / len(last_week_data)

        # Calculate 4-week average
        all_values = [val for _, val in data]
        four_week_avg = sum(all_values) / len(all_values)

        # Determine trend
        if current_week_avg > last_week_avg * 1.15:
            trend = "improving"
        elif current_week_avg < last_week_avg * 0.85:
            trend = "declining"
        else:
            trend = "stable"

        # Calculate percentage change
        if last_week_avg > 0:
            change_pct = ((current_week_avg - last_week_avg) / last_week_avg) * 100
        else:
            change_pct = 0.0

        return {
            "current_week_avg": round(current_week_avg, 1),
            "last_week_avg": round(last_week_avg, 1),
            "4_week_avg": round(four_week_avg, 1),
            "trend": trend,
            "change_pct": round(change_pct, 1),
            "data_points": len(data)
        }

    except Exception as e:
        logger.error(f"Get nutrient trends error: {e}")
        return None

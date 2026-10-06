"""
Background Job: Update User Statistics

Automatically updates user nutrition statistics after meal logging:
- Weekly nutrient averages (Week 1 & Week 2)
- Nutrient trends (improving/declining/stable)
- Logging streaks
- Total meals logged
- Learning phase completion
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from kai.database import (
    get_user_stats,
    initialize_user_stats,
    update_user_stats,
    get_user_meals,
    get_user,
)

logger = logging.getLogger(__name__)


async def calculate_and_update_user_stats(user_id: str) -> Dict:
    """
    Calculate all user stats and update database.

    This should be called after every meal log.

    Args:
        user_id: User ID

    Returns:
        Updated user stats dict
    """
    logger.info(f"🔄 Calculating stats for user {user_id}")

    # Ensure stats entry exists
    stats = await get_user_stats(user_id)
    if not stats:
        stats = await initialize_user_stats(user_id)

    # Get user creation date for account age
    user = await get_user(user_id)
    created_at = datetime.fromisoformat(user["created_at"])
    # Use timezone-aware now() to match Supabase's timezone-aware timestamps
    account_age_days = (datetime.now(timezone.utc) - created_at).days

    # Get all user meals
    all_meals = await get_user_meals(user_id, limit=1000)  # Get up to 1000 meals

    # Calculate total meals logged
    total_meals = len(all_meals)

    # Calculate logging streak
    current_streak, longest_streak = _calculate_streaks(all_meals)

    # Get last logged date
    last_logged_date = all_meals[0]["meal_date"] if all_meals else None

    # Calculate weekly averages
    week1_averages = _calculate_weekly_averages(all_meals, days_ago=0, days_range=7)
    week2_averages = _calculate_weekly_averages(all_meals, days_ago=7, days_range=7)

    # Calculate trends
    trends = _calculate_trends(week1_averages, week2_averages)

    # Determine if learning phase is complete
    # Learning phase = first 7 days OR first 21 meals
    learning_phase_complete = (account_age_days >= 7 and total_meals >= 21) or total_meals >= 21

    # Update stats in database
    updated_stats = await update_user_stats(
        user_id=user_id,
        total_meals_logged=total_meals,
        account_age_days=account_age_days,
        learning_phase_complete=learning_phase_complete,
        current_logging_streak=current_streak,
        longest_logging_streak=longest_streak,
        last_logged_date=last_logged_date,
        week1_averages=week1_averages,
        week2_averages=week2_averages,
        trends=trends,
    )

    logger.info(f"✅ Stats updated for {user_id}: {total_meals} meals, {current_streak} day streak")
    return updated_stats


def _calculate_streaks(meals: list) -> tuple[int, int]:
    """
    Calculate current and longest logging streaks.

    Args:
        meals: List of meals ordered by date DESC

    Returns:
        Tuple of (current_streak, longest_streak) in days
    """
    if not meals:
        return 0, 0

    # Group meals by date
    dates = sorted(set(meal["meal_date"] for meal in meals), reverse=True)

    # Calculate longest streak
    longest_streak = 0
    temp_streak = 1

    for i in range(1, len(dates)):
        prev_date = datetime.fromisoformat(dates[i - 1]).date()
        curr_date = datetime.fromisoformat(dates[i]).date()

        if (prev_date - curr_date).days == 1:
            temp_streak += 1
            longest_streak = max(longest_streak, temp_streak)
        else:
            temp_streak = 1

    # Calculate current streak
    # Streak is alive if the most recent log was today OR yesterday
    # (yesterday counts because the user may not have logged yet today)
    today = datetime.now().date()
    most_recent = datetime.fromisoformat(dates[0]).date()

    if most_recent == today:
        offset = 0
    elif most_recent == today - timedelta(days=1):
        offset = 1
    else:
        # Most recent log was 2+ days ago — streak is broken
        longest_streak = max(longest_streak, temp_streak, 1)
        return 0, longest_streak

    current_streak = 0
    for i, date_str in enumerate(dates):
        date = datetime.fromisoformat(date_str).date()
        expected_date = today - timedelta(days=i + offset)

        if date == expected_date:
            current_streak += 1
        else:
            break

    longest_streak = max(longest_streak, current_streak, 1)

    return current_streak, longest_streak


def _calculate_weekly_averages(
    meals: list,
    days_ago: int = 0,
    days_range: int = 7
) -> Dict[str, float]:
    """
    Calculate average nutrient intake for a week period.

    Args:
        meals: List of all meals
        days_ago: Start N days ago (0 = today, 7 = week 2)
        days_range: Number of days to average (default 7)

    Returns:
        Dict of nutrient averages: {
            "calories": 1850.5,
            "protein": 45.2,
            "carbs": 220.0,
            ...
        }
    """
    today = datetime.now().date()
    start_date = today - timedelta(days=days_ago + days_range)
    end_date = today - timedelta(days=days_ago)

    # Filter meals in this date range
    period_meals = [
        meal for meal in meals
        if start_date <= datetime.fromisoformat(meal["meal_date"]).date() < end_date
    ]

    if not period_meals:
        return {
            "calories": 0, "protein": 0, "carbs": 0, "fat": 0,
            "iron": 0, "calcium": 0, "potassium": 0, "zinc": 0
        }

    # Sum all nutrients from meal_foods (stored in foods field)
    totals = {
        "calories": 0, "protein": 0, "carbs": 0, "fat": 0,
        "iron": 0, "calcium": 0, "potassium": 0, "zinc": 0
    }

    for meal in period_meals:
        foods = meal.get("foods", [])
        for food in foods:
            totals["calories"] += food.get("calories", 0)
            totals["protein"] += food.get("protein", 0)
            totals["carbs"] += food.get("carbohydrates", 0)
            totals["fat"] += food.get("fat", 0)
            totals["iron"] += food.get("iron", 0)
            totals["calcium"] += food.get("calcium", 0)
            totals["potassium"] += food.get("potassium", 0)
            totals["zinc"] += food.get("zinc", 0)

    # Calculate averages (per day)
    num_days = len(set(meal["meal_date"] for meal in period_meals))
    if num_days == 0:
        num_days = 1

    averages = {
        nutrient: total / num_days
        for nutrient, total in totals.items()
    }

    return averages


def _calculate_trends(week1: Dict[str, float], week2: Dict[str, float]) -> Dict[str, str]:
    """
    Calculate nutrient trends (improving, declining, stable).

    Args:
        week1: Week 1 averages (last 7 days)
        week2: Week 2 averages (8-14 days ago)

    Returns:
        Dict of trends: {"iron": "improving", "protein": "stable", ...}
    """
    trends = {}

    for nutrient in ["calories", "protein", "carbs", "fat", "iron", "calcium", "potassium", "zinc"]:
        week1_val = week1.get(nutrient, 0)
        week2_val = week2.get(nutrient, 0)

        # Avoid division by zero
        if week2_val == 0:
            trends[nutrient] = "stable"
            continue

        # Calculate percent change
        percent_change = ((week1_val - week2_val) / week2_val) * 100

        # Threshold: >10% change = trend
        if percent_change > 10:
            trends[nutrient] = "improving"
        elif percent_change < -10:
            trends[nutrient] = "declining"
        else:
            trends[nutrient] = "stable"

    return trends


# =============================================================================
# CLI Testing
# =============================================================================

if __name__ == "__main__":
    import asyncio
    from kai.database import create_user

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_stats_calculation():
        """Test stats calculation"""
        print("\n" + "="*60)
        print("Testing Stats Calculation Job")
        print("="*60 + "\n")

        # Create test user
        user_id = "test_stats_job_001"
        try:
            user = await create_user(
                user_id=user_id,
                email="teststats@kai.com",
                name="Test Stats",
                gender="female",
                age=28
            )
            print(f"✅ Created test user: {user['name']}")
        except Exception as e:
            print(f"User may already exist: {e}")

        # Calculate stats
        stats = await calculate_and_update_user_stats(user_id)

        print("\n📊 Calculated Stats:")
        print(f"  Total meals: {stats['total_meals_logged']}")
        print(f"  Account age: {stats['account_age_days']} days")
        print(f"  Current streak: {stats['current_logging_streak']} days")
        print(f"  Learning phase complete: {stats['learning_phase_complete']}")
        print(f"\n  Week 1 Averages:")
        print(f"    Calories: {stats['week1_avg_calories']:.1f} kcal")
        print(f"    Protein: {stats['week1_avg_protein']:.1f}g")
        print(f"    Iron: {stats['week1_avg_iron']:.1f}mg")
        print(f"    Calcium: {stats['week1_avg_calcium']:.1f}mg")
        print(f"\n  Trends:")
        print(f"    Iron: {stats['iron_trend']}")
        print(f"    Protein: {stats['protein_trend']}")

        print("\n✅ Stats calculation complete!\n")

    asyncio.run(test_stats_calculation())

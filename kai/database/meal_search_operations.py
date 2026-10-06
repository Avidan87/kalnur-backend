"""
Meal Search Operations - Supabase

Advanced search operations for meal history:
- Date range filtering
- Food name search
- Meal pattern analysis
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .db_setup import get_supabase

logger = logging.getLogger(__name__)


async def get_meals_by_date_range(
    user_id: str,
    start_date: str,
    end_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get meals for a date range (optimized with JOIN).

    Args:
        user_id: User identifier
        start_date: Start date (ISO format YYYY-MM-DD)
        end_date: End date (ISO format YYYY-MM-DD), defaults to start_date

    Returns:
        List[dict]: Meals in date range with foods

    Examples:
        - Single day: get_meals_by_date_range("user123", "2026-02-12")
        - Date range: get_meals_by_date_range("user123", "2026-02-10", "2026-02-12")
    """
    end_date = end_date or start_date
    client = get_supabase()

    # Optimized: Single query with JOIN
    result = client.table("meals").select(
        "*, meal_foods("
        "food_name, food_id, portion_grams, "
        "calories, protein, carbohydrates, fat, fiber, "
        "iron, calcium, zinc, potassium, sodium, magnesium, "
        "vitamin_a, vitamin_c, vitamin_d, vitamin_b12, folate, confidence"
        ")"
    ).eq(
        "user_id", user_id
    ).gte(
        "meal_date", start_date
    ).lte(
        "meal_date", end_date
    ).order(
        "meal_date", desc=False
    ).order(
        "meal_time", desc=False
    ).execute()

    # Transform result
    meals = []
    for row in result.data:
        meal = dict(row)
        meal["foods"] = meal.pop("meal_foods", [])
        meals.append(meal)

    logger.info(f"📅 Found {len(meals)} meals between {start_date} and {end_date}")
    return meals


async def search_meals_by_food(
    user_id: str,
    food_name: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search for meals containing a specific food (case-insensitive).

    Args:
        user_id: User identifier
        food_name: Food name to search for (partial match supported)
        limit: Maximum number of meals to return

    Returns:
        List[dict]: Meals containing the food, most recent first

    Examples:
        - search_meals_by_food("user123", "jollof rice")
        - search_meals_by_food("user123", "chicken")
        - search_meals_by_food("user123", "plantain")
    """
    client = get_supabase()

    # Step 1: Find meal_ids that contain the food (case-insensitive search)
    food_search = client.table("meal_foods").select(
        "meal_id"
    ).ilike(
        "food_name", f"%{food_name}%"
    ).execute()

    if not food_search.data:
        logger.info(f"🔍 No meals found with food: {food_name}")
        return []

    # Extract unique meal_ids
    meal_ids = list(set([row["meal_id"] for row in food_search.data]))

    # Step 2: Get full meal details with foods (optimized with JOIN)
    result = client.table("meals").select(
        "*, meal_foods("
        "food_name, food_id, portion_grams, "
        "calories, protein, carbohydrates, fat, fiber, "
        "iron, calcium, zinc, potassium, sodium, magnesium, "
        "vitamin_a, vitamin_c, vitamin_d, vitamin_b12, folate, confidence"
        ")"
    ).eq(
        "user_id", user_id
    ).in_(
        "meal_id", meal_ids
    ).order(
        "meal_date", desc=True
    ).order(
        "meal_time", desc=True
    ).limit(limit).execute()

    # Transform result
    meals = []
    for row in result.data:
        meal = dict(row)
        meal["foods"] = meal.pop("meal_foods", [])
        meals.append(meal)

    logger.info(f"🔍 Found {len(meals)} meals with '{food_name}'")
    return meals


async def get_food_frequency(
    user_id: str,
    food_name: str,
    days: int = 7
) -> Dict[str, Any]:
    """
    Get frequency of a specific food in the last N days.

    Args:
        user_id: User identifier
        food_name: Food name to analyze
        days: Number of days to look back (default 7)

    Returns:
        Dict with frequency stats:
        - count: Number of times eaten
        - first_date: First time eaten in this period
        - last_date: Most recent time eaten
        - meals: List of meals containing the food
    """
    client = get_supabase()

    # Calculate date range
    end_date = datetime.now().date().isoformat()
    start_date = (datetime.now() - timedelta(days=days)).date().isoformat()

    # Search for meals with this food in date range
    meals = await search_meals_by_food(user_id, food_name, limit=100)

    # Filter by date range
    filtered_meals = [
        meal for meal in meals
        if start_date <= meal.get("meal_date", "") <= end_date
    ]

    if not filtered_meals:
        return {
            "count": 0,
            "days_analyzed": days,
            "food_name": food_name,
            "meals": []
        }

    # Calculate stats
    dates = [meal.get("meal_date") for meal in filtered_meals]

    return {
        "count": len(filtered_meals),
        "days_analyzed": days,
        "food_name": food_name,
        "first_date": min(dates),
        "last_date": max(dates),
        "meals": filtered_meals
    }


def parse_relative_date(date_string: str) -> tuple[str, Optional[str]]:
    """
    Parse relative date strings into ISO format dates.

    Args:
        date_string: Natural language date (e.g., "today", "yesterday", "last week")

    Returns:
        Tuple of (start_date, end_date) in ISO format

    Examples:
        - "today" → ("2026-02-12", "2026-02-12")
        - "yesterday" → ("2026-02-11", "2026-02-11")
        - "last week" → ("2026-02-05", "2026-02-12")
    """
    today = datetime.now().date()
    date_lower = date_string.lower().strip()

    if date_lower == "today":
        return (today.isoformat(), today.isoformat())

    elif date_lower == "yesterday":
        yesterday = today - timedelta(days=1)
        return (yesterday.isoformat(), yesterday.isoformat())

    elif date_lower in ["last week", "this week", "past week"]:
        start = today - timedelta(days=7)
        return (start.isoformat(), today.isoformat())

    elif date_lower in ["last month", "this month", "past month"]:
        start = today - timedelta(days=30)
        return (start.isoformat(), today.isoformat())

    else:
        # Assume it's already an ISO date or invalid
        return (date_string, date_string)

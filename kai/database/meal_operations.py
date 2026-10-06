"""
Meal Logging Database Operations - Supabase

Operations for logging meals, tracking foods, and calculating daily nutrition totals.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import uuid

from .db_setup import get_supabase
from kai.utils.meal_title import generate_meal_title

logger = logging.getLogger(__name__)


async def log_meal(
    user_id: str,
    meal_type: str,
    foods: List[Dict[str, Any]],
    meal_date: Optional[str] = None,
    image_url: Optional[str] = None,
    user_description: Optional[str] = None,
    scene_description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Log a meal with detected foods and nutrition data.

    Args:
        user_id: User identifier
        meal_type: Type of meal (breakfast, lunch, dinner, snack)
        foods: List of food dicts with nutrition data
        meal_date: Date of meal (ISO format YYYY-MM-DD), defaults to today
        image_url: Optional URL of meal image
        user_description: Optional user description

    Returns:
        dict: Logged meal data with totals
    """
    meal_date = meal_date or date.today().isoformat()
    meal_time = datetime.now().time().isoformat()
    meal_id = f"meal_{uuid.uuid4().hex}"

    client = get_supabase()

    # Insert meal record
    client.table("meals").insert({
        "meal_id": meal_id,
        "user_id": user_id,
        "meal_type": meal_type,
        "meal_date": meal_date,
        "meal_time": meal_time,
        "image_url": image_url,
        "user_description": user_description,
        "scene_description": scene_description,
        "created_at": datetime.now().isoformat(),
    }).execute()

    # Initialize totals for all 16 nutrients
    total_calories = 0.0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0
    total_fiber = 0.0
    total_iron = 0.0
    total_calcium = 0.0
    total_zinc = 0.0
    total_potassium = 0.0
    total_sodium = 0.0
    total_magnesium = 0.0
    total_vitamin_a = 0.0
    total_vitamin_c = 0.0
    total_vitamin_d = 0.0
    total_vitamin_b12 = 0.0
    total_folate = 0.0

    # Insert foods in batch
    food_rows = []
    for food in foods:
        food_row = {
            "meal_id": meal_id,
            "food_name": food["food_name"],
            "food_id": food.get("food_id"),
            "portion_grams": food["portion_grams"],
            "calories": food["calories"],
            "protein": food["protein"],
            "carbohydrates": food["carbohydrates"],
            "fat": food["fat"],
            "fiber": food.get("fiber", 0.0),
            "iron": food["iron"],
            "calcium": food["calcium"],
            "zinc": food["zinc"],
            "potassium": food["potassium"],
            "sodium": food.get("sodium", 0.0),
            "magnesium": food.get("magnesium", 0.0),
            "vitamin_a": food.get("vitamin_a", 0.0),
            "vitamin_c": food.get("vitamin_c", 0.0),
            "vitamin_d": food.get("vitamin_d", 0.0),
            "vitamin_b12": food.get("vitamin_b12", 0.0),
            "folate": food.get("folate", 0.0),
            "confidence": food.get("confidence", 1.0),
        }
        food_rows.append(food_row)

        # Accumulate totals
        total_calories += food["calories"]
        total_protein += food["protein"]
        total_carbs += food["carbohydrates"]
        total_fat += food["fat"]
        total_fiber += food.get("fiber", 0.0)
        total_iron += food["iron"]
        total_calcium += food["calcium"]
        total_zinc += food["zinc"]
        total_potassium += food["potassium"]
        total_sodium += food.get("sodium", 0.0)
        total_magnesium += food.get("magnesium", 0.0)
        total_vitamin_a += food.get("vitamin_a", 0.0)
        total_vitamin_c += food.get("vitamin_c", 0.0)
        total_vitamin_d += food.get("vitamin_d", 0.0)
        total_vitamin_b12 += food.get("vitamin_b12", 0.0)
        total_folate += food.get("folate", 0.0)

    # Batch insert all foods
    if food_rows:
        client.table("meal_foods").insert(food_rows).execute()

    # Update daily nutrient totals
    await _update_daily_nutrients(
        client, user_id, meal_date,
        calories=total_calories, protein=total_protein,
        carbs=total_carbs, fat=total_fat, fiber=total_fiber,
        iron=total_iron, calcium=total_calcium, zinc=total_zinc,
        potassium=total_potassium, sodium=total_sodium, magnesium=total_magnesium,
        vitamin_a=total_vitamin_a, vitamin_c=total_vitamin_c,
        vitamin_d=total_vitamin_d, vitamin_b12=total_vitamin_b12, folate=total_folate,
    )

    logger.info(f"Logged meal: {meal_id} for user {user_id} ({len(foods)} foods)")

    return {
        "meal_id": meal_id,
        "user_id": user_id,
        "meal_type": meal_type,
        "meal_date": meal_date,
        "meal_time": meal_time,
        "foods_count": len(foods),
        "totals": {
            "calories": round(total_calories, 1),
            "protein": round(total_protein, 1),
            "carbohydrates": round(total_carbs, 1),
            "fat": round(total_fat, 1),
            "fiber": round(total_fiber, 1),
            "iron": round(total_iron, 2),
            "calcium": round(total_calcium, 1),
            "zinc": round(total_zinc, 2),
            "potassium": round(total_potassium, 1),
            "sodium": round(total_sodium, 1),
            "magnesium": round(total_magnesium, 1),
            "vitamin_a": round(total_vitamin_a, 1),
            "vitamin_c": round(total_vitamin_c, 1),
            "vitamin_d": round(total_vitamin_d, 2),
            "vitamin_b12": round(total_vitamin_b12, 2),
            "folate": round(total_folate, 1),
        }
    }


async def _update_daily_nutrients(
    client,
    user_id: str,
    date_str: str,
    *,
    calories: float, protein: float, carbs: float, fat: float, fiber: float,
    iron: float, calcium: float, zinc: float, potassium: float,
    sodium: float, magnesium: float,
    vitamin_a: float, vitamin_c: float, vitamin_d: float,
    vitamin_b12: float, folate: float,
) -> None:
    """
    Update or create daily nutrient totals - all 16 nutrients.
    """
    # Check if record exists
    existing = client.table("daily_nutrients").select("id, meal_count, total_calories, total_protein, total_carbohydrates, total_fat, total_fiber, total_iron, total_calcium, total_zinc, total_potassium, total_sodium, total_magnesium, total_vitamin_a, total_vitamin_c, total_vitamin_d, total_vitamin_b12, total_folate").eq("user_id", user_id).eq("date", date_str).execute()

    if existing.data:
        row = existing.data[0]
        # Update existing record - add to current totals
        client.table("daily_nutrients").update({
            "total_calories": (row["total_calories"] or 0) + calories,
            "total_protein": (row["total_protein"] or 0) + protein,
            "total_carbohydrates": (row["total_carbohydrates"] or 0) + carbs,
            "total_fat": (row["total_fat"] or 0) + fat,
            "total_fiber": (row["total_fiber"] or 0) + fiber,
            "total_iron": (row["total_iron"] or 0) + iron,
            "total_calcium": (row["total_calcium"] or 0) + calcium,
            "total_zinc": (row["total_zinc"] or 0) + zinc,
            "total_potassium": (row["total_potassium"] or 0) + potassium,
            "total_sodium": (row["total_sodium"] or 0) + sodium,
            "total_magnesium": (row["total_magnesium"] or 0) + magnesium,
            "total_vitamin_a": (row["total_vitamin_a"] or 0) + vitamin_a,
            "total_vitamin_c": (row["total_vitamin_c"] or 0) + vitamin_c,
            "total_vitamin_d": (row["total_vitamin_d"] or 0) + vitamin_d,
            "total_vitamin_b12": (row["total_vitamin_b12"] or 0) + vitamin_b12,
            "total_folate": (row["total_folate"] or 0) + folate,
            "meal_count": (row["meal_count"] or 0) + 1,
            "updated_at": datetime.now().isoformat(),
        }).eq("id", row["id"]).execute()
    else:
        # Create new record
        client.table("daily_nutrients").insert({
            "user_id": user_id,
            "date": date_str,
            "total_calories": calories,
            "total_protein": protein,
            "total_carbohydrates": carbs,
            "total_fat": fat,
            "total_fiber": fiber,
            "total_iron": iron,
            "total_calcium": calcium,
            "total_zinc": zinc,
            "total_potassium": potassium,
            "total_sodium": sodium,
            "total_magnesium": magnesium,
            "total_vitamin_a": vitamin_a,
            "total_vitamin_c": vitamin_c,
            "total_vitamin_d": vitamin_d,
            "total_vitamin_b12": vitamin_b12,
            "total_folate": folate,
            "meal_count": 1,
            "updated_at": datetime.now().isoformat(),
        }).execute()


async def get_user_meals(
    user_id: str,
    limit: int = 20,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Get user's recent meals with foods (optimized with JOIN).

    Args:
        user_id: User identifier
        limit: Number of meals to return
        offset: Number of meals to skip

    Returns:
        List[dict]: List of meals with foods

    Performance: Single query with JOIN instead of N+1 queries
    """
    client = get_supabase()

    # Optimized: Get meals with foods in a single query using JOIN
    # Supabase syntax: select("meals.*, meal_foods(*)")
    result = client.table("meals").select(
        "*, meal_foods("
        "food_name, food_id, portion_grams, "
        "calories, protein, carbohydrates, fat, fiber, "
        "iron, calcium, zinc, potassium, sodium, magnesium, "
        "vitamin_a, vitamin_c, vitamin_d, vitamin_b12, folate, confidence"
        ")"
    ).eq(
        "user_id", user_id
    ).order(
        "meal_date", desc=True
    ).order(
        "meal_time", desc=True
    ).range(offset, offset + limit - 1).execute()

    # Transform result: Supabase returns nested meal_foods array
    meals = []
    for row in result.data:
        meal = dict(row)
        # Rename meal_foods to foods for consistency
        meal["foods"] = meal.pop("meal_foods", [])
        # Generate smart meal title from food names
        food_names = [f["food_name"] for f in meal["foods"] if f.get("food_name")]
        meal["meal_title"] = generate_meal_title(food_names) if food_names else None
        meals.append(meal)

    return meals


async def get_meals_by_date(
    user_id: str,
    start_date: str,
    end_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get meals for a date range.

    Args:
        user_id: User identifier
        start_date: Start date (ISO format YYYY-MM-DD)
        end_date: End date (ISO format), defaults to start_date

    Returns:
        List[dict]: Meals in date range
    """
    end_date = end_date or start_date
    client = get_supabase()

    result = client.table("meals").select("*").eq(
        "user_id", user_id
    ).gte("meal_date", start_date).lte("meal_date", end_date).order(
        "meal_date"
    ).order("meal_time").execute()

    meals = []
    for row in result.data:
        meal = dict(row)

        foods_result = client.table("meal_foods").select(
            "food_name, food_id, portion_grams, "
            "calories, protein, carbohydrates, fat, fiber, "
            "iron, calcium, zinc, potassium, sodium, magnesium, "
            "vitamin_a, vitamin_c, vitamin_d, vitamin_b12, folate, confidence"
        ).eq("meal_id", meal["meal_id"]).execute()

        meal["foods"] = foods_result.data
        meals.append(meal)

    return meals


async def get_daily_nutrition_totals(
    user_id: str,
    date_str: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get daily nutrition totals for a specific date.

    Args:
        user_id: User identifier
        date_str: Date (ISO format), defaults to today

    Returns:
        dict: Daily nutrition totals or None if no meals logged
    """
    date_str = date_str or datetime.today().date().isoformat()
    client = get_supabase()

    result = client.table("daily_nutrients").select("*").eq(
        "user_id", user_id
    ).eq("date", date_str).execute()

    if not result.data:
        return None

    return result.data[0]


async def get_nutrition_history(
    user_id: str,
    days: int = 7
) -> List[Dict[str, Any]]:
    """
    Get nutrition history for the past N days.

    Args:
        user_id: User identifier
        days: Number of days to retrieve

    Returns:
        List[dict]: Daily nutrition totals for each day
    """
    from datetime import timedelta

    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=days - 1)

    client = get_supabase()

    result = client.table("daily_nutrients").select("*").eq(
        "user_id", user_id
    ).gte("date", start_date.isoformat()).lte(
        "date", end_date.isoformat()
    ).order("date", desc=True).execute()

    return result.data


async def delete_meal(meal_id: str) -> bool:
    """
    Delete a meal and recalculate daily totals.

    Args:
        meal_id: Meal identifier

    Returns:
        bool: True if deleted, False if not found
    """
    client = get_supabase()

    # Get meal info before deleting
    meal_result = client.table("meals").select("user_id, meal_date").eq("meal_id", meal_id).execute()

    if not meal_result.data:
        return False

    user_id = meal_result.data[0]["user_id"]
    meal_date = meal_result.data[0]["meal_date"]

    # Get meal food totals
    foods_result = client.table("meal_foods").select(
        "calories, protein, carbohydrates, fat, fiber, "
        "iron, calcium, zinc, potassium, sodium, magnesium, "
        "vitamin_a, vitamin_c, vitamin_d, vitamin_b12, folate"
    ).eq("meal_id", meal_id).execute()

    # Calculate totals to subtract
    totals = {}
    for key in ["calories", "protein", "carbohydrates", "fat", "fiber",
                 "iron", "calcium", "zinc", "potassium", "sodium", "magnesium",
                 "vitamin_a", "vitamin_c", "vitamin_d", "vitamin_b12", "folate"]:
        totals[key] = sum(f.get(key, 0) or 0 for f in foods_result.data)

    # Delete meal (meal_foods will cascade)
    client.table("meals").delete().eq("meal_id", meal_id).execute()

    # Update daily totals (subtract this meal)
    daily = client.table("daily_nutrients").select("*").eq(
        "user_id", user_id
    ).eq("date", meal_date).execute()

    if daily.data:
        row = daily.data[0]
        client.table("daily_nutrients").update({
            "total_calories": max(0, (row["total_calories"] or 0) - totals["calories"]),
            "total_protein": max(0, (row["total_protein"] or 0) - totals["protein"]),
            "total_carbohydrates": max(0, (row["total_carbohydrates"] or 0) - totals["carbohydrates"]),
            "total_fat": max(0, (row["total_fat"] or 0) - totals["fat"]),
            "total_fiber": max(0, (row["total_fiber"] or 0) - totals["fiber"]),
            "total_iron": max(0, (row["total_iron"] or 0) - totals["iron"]),
            "total_calcium": max(0, (row["total_calcium"] or 0) - totals["calcium"]),
            "total_zinc": max(0, (row["total_zinc"] or 0) - totals["zinc"]),
            "total_potassium": max(0, (row["total_potassium"] or 0) - totals["potassium"]),
            "total_sodium": max(0, (row["total_sodium"] or 0) - totals["sodium"]),
            "total_magnesium": max(0, (row["total_magnesium"] or 0) - totals["magnesium"]),
            "total_vitamin_a": max(0, (row["total_vitamin_a"] or 0) - totals["vitamin_a"]),
            "total_vitamin_c": max(0, (row["total_vitamin_c"] or 0) - totals["vitamin_c"]),
            "total_vitamin_d": max(0, (row["total_vitamin_d"] or 0) - totals["vitamin_d"]),
            "total_vitamin_b12": max(0, (row["total_vitamin_b12"] or 0) - totals["vitamin_b12"]),
            "total_folate": max(0, (row["total_folate"] or 0) - totals["folate"]),
            "meal_count": max(0, (row["meal_count"] or 0) - 1),
            "updated_at": datetime.now().isoformat(),
        }).eq("id", row["id"]).execute()

    logger.info(f"Deleted meal: {meal_id}")
    return True

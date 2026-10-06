"""
User Database Operations - Supabase

CRUD operations for user profiles and health information.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .db_setup import get_supabase

logger = logging.getLogger(__name__)


async def create_user(
    user_id: str,
    email: Optional[str] = None,
    name: Optional[str] = None,
    gender: str = "female",
    age: int = 25
) -> Dict[str, Any]:
    """
    Create a new user profile.

    Args:
        user_id: Unique user identifier
        email: User email (optional)
        name: User name (optional)
        gender: User gender (male/female)
        age: User age (13-120)

    Returns:
        dict: Created user data

    Raises:
        ValueError: If user already exists or invalid data
    """
    client = get_supabase()

    # Check if user exists
    existing = client.table("users").select("user_id").eq("user_id", user_id).execute()
    if existing.data:
        raise ValueError(f"User {user_id} already exists")

    now = datetime.now().isoformat()

    # Create user
    client.table("users").insert({
        "user_id": user_id,
        "email": email,
        "name": name,
        "gender": gender,
        "age": age,
        "created_at": now,
        "updated_at": now,
    }).execute()

    # Create default health profile
    client.table("user_health").insert({
        "user_id": user_id,
        "updated_at": now,
    }).execute()

    logger.info(f"✓ Created user: {user_id}")

    return {
        "user_id": user_id,
        "email": email,
        "name": name,
        "gender": gender,
        "age": age,
    }


async def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user profile by ID.

    Args:
        user_id: User identifier

    Returns:
        dict: User data or None if not found
    """
    client = get_supabase()

    result = client.table("users").select(
        "*, user_health(weight_kg, height_cm, activity_level, health_goals, "
        "dietary_restrictions, target_weight_kg, calculated_calorie_goal, "
        "custom_calorie_goal, active_calorie_goal, show_sugar)"
    ).eq("user_id", user_id).execute()

    if not result.data:
        return None

    row = result.data[0]
    health = row.get("user_health", {})
    # user_health comes back as a list or dict depending on the join
    if isinstance(health, list):
        health = health[0] if health else {}

    return {
        "user_id": row["user_id"],
        "email": row.get("email"),
        "name": row.get("name"),
        "gender": row.get("gender"),
        "age": row.get("age"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "weight_kg": health.get("weight_kg"),
        "height_cm": health.get("height_cm"),
        "activity_level": health.get("activity_level"),
        "health_goals": health.get("health_goals"),
        "dietary_restrictions": health.get("dietary_restrictions"),
        "target_weight_kg": health.get("target_weight_kg"),
        "calculated_calorie_goal": health.get("calculated_calorie_goal"),
        "custom_calorie_goal": health.get("custom_calorie_goal"),
        "active_calorie_goal": health.get("active_calorie_goal"),
        "show_sugar": health.get("show_sugar", False),
    }


async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Get user profile by email.

    Args:
        email: User email

    Returns:
        dict: User data or None if not found
    """
    client = get_supabase()

    result = client.table("users").select(
        "*, user_health(weight_kg, height_cm, activity_level, health_goals, "
        "dietary_restrictions, target_weight_kg, calculated_calorie_goal, "
        "custom_calorie_goal, active_calorie_goal, show_sugar)"
    ).eq("email", email).execute()

    if not result.data:
        return None

    row = result.data[0]
    health = row.get("user_health", {})
    if isinstance(health, list):
        health = health[0] if health else {}

    return {
        "user_id": row["user_id"],
        "email": row.get("email"),
        "name": row.get("name"),
        "gender": row.get("gender"),
        "age": row.get("age"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "weight_kg": health.get("weight_kg"),
        "height_cm": health.get("height_cm"),
        "activity_level": health.get("activity_level"),
        "health_goals": health.get("health_goals"),
        "dietary_restrictions": health.get("dietary_restrictions"),
        "target_weight_kg": health.get("target_weight_kg"),
        "calculated_calorie_goal": health.get("calculated_calorie_goal"),
        "custom_calorie_goal": health.get("custom_calorie_goal"),
        "active_calorie_goal": health.get("active_calorie_goal"),
        "show_sugar": health.get("show_sugar", False),
    }


async def update_user(
    user_id: str,
    email: Optional[str] = None,
    name: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None
) -> Dict[str, Any]:
    """
    Update user profile.

    Args:
        user_id: User identifier
        email: Updated email
        name: Updated name
        gender: Updated gender
        age: Updated age

    Returns:
        dict: Updated user data

    Raises:
        ValueError: If user not found
    """
    existing = await get_user(user_id)
    if not existing:
        raise ValueError(f"User {user_id} not found")

    client = get_supabase()

    updates = {"updated_at": datetime.now().isoformat()}
    if email is not None:
        updates["email"] = email
    if name is not None:
        updates["name"] = name
    if gender is not None:
        updates["gender"] = gender
    if age is not None:
        updates["age"] = age

    client.table("users").update(updates).eq("user_id", user_id).execute()

    logger.info(f"✓ Updated user: {user_id}")
    return await get_user(user_id)


async def update_user_health(
    user_id: str,
    weight_kg: Optional[float] = None,
    height_cm: Optional[float] = None,
    activity_level: Optional[str] = None,
    health_goals: Optional[str] = None,
    dietary_restrictions: Optional[str] = None,
    target_weight_kg: Optional[float] = None,
    calculated_calorie_goal: Optional[float] = None,
    custom_calorie_goal: Optional[float] = None,
    active_calorie_goal: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Update user health information.

    Args:
        user_id: User identifier
        weight_kg: Current weight in kilograms
        height_cm: Height in centimeters
        activity_level: Activity level
        health_goals: Health goals
        dietary_restrictions: Dietary restrictions text
        target_weight_kg: Goal weight
        calculated_calorie_goal: KAI's calculated calorie recommendation
        custom_calorie_goal: User's manual calorie override
        active_calorie_goal: The active calorie goal being used

    Returns:
        dict: Updated user data

    Raises:
        ValueError: If user not found
    """
    existing = await get_user(user_id)
    if not existing:
        raise ValueError(f"User {user_id} not found")

    client = get_supabase()

    updates = {"updated_at": datetime.now().isoformat()}
    if weight_kg is not None:
        updates["weight_kg"] = weight_kg
    if height_cm is not None:
        updates["height_cm"] = height_cm
    if activity_level is not None:
        updates["activity_level"] = activity_level
    if health_goals is not None:
        updates["health_goals"] = health_goals
    if dietary_restrictions is not None:
        updates["dietary_restrictions"] = dietary_restrictions
    if target_weight_kg is not None:
        updates["target_weight_kg"] = target_weight_kg
    if calculated_calorie_goal is not None:
        updates["calculated_calorie_goal"] = calculated_calorie_goal
    if custom_calorie_goal is not None:
        updates["custom_calorie_goal"] = custom_calorie_goal
    if active_calorie_goal is not None:
        updates["active_calorie_goal"] = active_calorie_goal

    client.table("user_health").update(updates).eq("user_id", user_id).execute()

    logger.info(f"✓ Updated health info for user: {user_id}")
    return await get_user(user_id)


async def update_sugar_preference(user_id: str, show_sugar: bool) -> Dict[str, Any]:
    """
    Update the user's sugar tracking preference.

    Args:
        user_id: User identifier
        show_sugar: Whether the user wants sugar impact shown in coaching

    Returns:
        dict: Updated user data

    Raises:
        ValueError: If user not found
    """
    existing = await get_user(user_id)
    if not existing:
        raise ValueError(f"User {user_id} not found")

    client = get_supabase()
    client.table("user_health").update({
        "show_sugar": show_sugar,
        "updated_at": datetime.now().isoformat(),
    }).eq("user_id", user_id).execute()

    logger.info(f"✓ Updated sugar preference for user: {user_id} → show_sugar={show_sugar}")
    return await get_user(user_id)


async def get_user_health_profile(user_id: str) -> Dict[str, Any]:
    """
    Get user health profile with RDV calculations.

    Returns user health info plus calculated RDV values based on
    gender, age, weight, height, activity level, and health goals.

    Args:
        user_id: User identifier

    Returns:
        dict: User health profile with RDV values

    Raises:
        ValueError: If user not found
    """
    user = await get_user(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Check if profile is complete
    profile_complete = all([
        user.get("weight_kg"),
        user.get("height_cm"),
        user.get("activity_level"),
        user.get("health_goals")
    ])

    # Calculate RDV using V2 (BMR/TDEE-based, full 16-nutrient system)
    rdv = None
    if profile_complete:
        from kai.utils.nutrition_rdv import calculate_user_rdv_v2
        try:
            rdv_result = calculate_user_rdv_v2(user)
            rdv = rdv_result["rdv"]
        except (ValueError, KeyError) as e:
            logger.warning(f"Error calculating BMR/TDEE RDV for user {user_id}: {e}. RDV unavailable.")
    else:
        logger.info(f"User {user_id} has incomplete profile — RDV not calculated.")

    return {
        "user_id": user_id,
        "email": user.get("email"),
        "name": user["name"],
        "gender": user["gender"],
        "age": user["age"],
        "weight_kg": user.get("weight_kg"),
        "height_cm": user.get("height_cm"),
        "activity_level": user.get("activity_level"),
        "health_goals": user.get("health_goals"),
        "dietary_restrictions": user.get("dietary_restrictions"),
        "target_weight_kg": user.get("target_weight_kg"),
        "calculated_calorie_goal": user.get("calculated_calorie_goal"),
        "custom_calorie_goal": user.get("custom_calorie_goal"),
        "active_calorie_goal": user.get("active_calorie_goal"),
        "show_sugar": user.get("show_sugar", False),
        "profile_complete": profile_complete,
        "rdv": rdv or {},
    }


async def delete_user(user_id: str) -> bool:
    """
    Delete user and all associated data.

    Args:
        user_id: User identifier

    Returns:
        bool: True if deleted, False if not found
    """
    client = get_supabase()

    result = client.table("users").delete().eq("user_id", user_id).execute()

    deleted = len(result.data) > 0

    if deleted:
        logger.info(f"✓ Deleted user: {user_id}")
    else:
        logger.warning(f"User not found: {user_id}")

    return deleted

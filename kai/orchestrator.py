"""
KAI Orchestrator

Simplified workflow for food logging: Vision → Knowledge → Save to DB

Chat is now handled separately by ChatAgent.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from kai.agents.vision_agent import VisionAgent
from kai.agents.knowledge_agent import KnowledgeAgent
from kai.models.agent_models import VisionResult, KnowledgeResult, DetectedFood
from kai.database import (
    create_user,
    get_user,
    log_meal,
)
from kai.jobs import calculate_and_update_user_stats
from kai.food_registry import get_food_registry, get_ingredient_portion


logger = logging.getLogger(__name__)


# Confidence threshold - warn user if detection confidence is below this
LOW_CONFIDENCE_THRESHOLD = 0.5


VALID_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}


def _infer_meal_type_from_time() -> str:
    """
    Infer meal type based on current time of day.

    Returns:
        'breakfast' (5-11am), 'lunch' (11am-4pm),
        'dinner' (4-9pm), or 'snack' (9pm-5am)
    """
    hour = datetime.now().hour
    if 5 <= hour < 11:
        return "breakfast"
    elif 11 <= hour < 16:
        return "lunch"
    elif 16 <= hour < 21:
        return "dinner"
    else:
        return "snack"


def _normalize_meal_type(meal_type: Optional[str]) -> str:
    """
    Normalize and validate meal_type, falling back to time-based inference.

    Args:
        meal_type: Raw meal type from API (could be None, empty, or invalid)

    Returns:
        Valid meal type: 'breakfast', 'lunch', 'dinner', or 'snack'
    """
    if meal_type:
        normalized = meal_type.strip().lower()
        if normalized in VALID_MEAL_TYPES:
            return normalized
    # Fall back to time-based inference
    return _infer_meal_type_from_time()


# ============================================================================
# Singleton Agent Instances
# ============================================================================

_agent_instances = {
    "vision": None,
    "knowledge": None,
}


def _get_agent(agent_type: str):
    """Get or create singleton agent instance."""
    if _agent_instances[agent_type] is None:
        if agent_type == "vision":
            _agent_instances[agent_type] = VisionAgent()
            logger.info("✓ Initialized Vision Agent (GPT-4o)")
        elif agent_type == "knowledge":
            _agent_instances[agent_type] = KnowledgeAgent()
            logger.info("✓ Initialized Knowledge Agent (ChromaDB RAG)")

    return _agent_instances[agent_type]


def _extract_foods_from_vision(
    vision_result: VisionResult
) -> Tuple[List[str], List[float], List[float], List[Optional[str]], List[List[str]]]:
    """
    Extract food names, portions, confidence scores, oil levels, and visible
    ingredients from VisionResult.

    Uses food-specific typical portions from database instead of generic 200g fallback.
    Validates portions against reasonable ranges per food type.

    Returns:
        Tuple of (names, grams, confidences, oil_levels, visible_ingredients)
    """
    names: List[str] = []
    grams: List[float] = []
    confidences: List[float] = []
    oil_levels: List[Optional[str]] = []
    visible_ingredients: List[List[str]] = []

    registry = get_food_registry()

    for item in vision_result.detected_foods:
        names.append(item.name)
        confidences.append(item.confidence)
        oil_levels.append(getattr(item, 'oil_amount_estimate', None))
        visible_ingredients.append(getattr(item, 'visible_ingredients', []) or [])

        # Get food-specific portion info from registry
        food_info = registry.get_food_info(item.name)
        typical_g = food_info.get('typical_portion_g', 150) if food_info else 150
        min_g = food_info.get('min_reasonable_g', 30) if food_info else 30
        max_g = food_info.get('max_reasonable_g', 500) if food_info else 500

        count_based = (
            float(item.item_count) * float(typical_g)
            if (item.item_count and item.item_count > 0)
            else None
        )

        vision_based = None
        if item.estimated_grams and item.estimated_grams > 0:
            clamped = float(item.estimated_grams)
            if clamped < min_g:
                logger.warning(
                    "⚠️ Portion too small for %s: %.0fg < min %.0fg, using min",
                    item.name, clamped, min_g
                )
                clamped = min_g
            elif clamped > max_g:
                logger.warning(
                    "⚠️ Portion too large for %s: %.0fg > max %.0fg, capping",
                    item.name, clamped, max_g
                )
                clamped = max_g
            vision_based = clamped

        # Combine count-based and vision-based estimates context-aware:
        #
        # ≤3 items (whole loaf, 2 slices, 1 fish): vision dominates (70/30).
        #   Count-based is unreliable here — item_count=1 × typical_g massively
        #   underestimates whole items (e.g. 1 loaf × 30g = 30g vs real 400g).
        #
        # 4+ items (fried yam chunks, akara balls, puff puff): average both (50/50).
        #   Many-piece foods inflate badly with max() — averaging keeps it honest
        #   while still respecting the count signal.
        if count_based and vision_based:
            if item.item_count and item.item_count <= 3:
                portion = (count_based * 0.3) + (vision_based * 0.7)
                logger.info(
                    "🔢 %s: few items (%d) → vision-weighted (count=%.0fg × 0.3 + vision=%.0fg × 0.7) = %.0fg",
                    item.name, item.item_count, count_based, vision_based, portion
                )
            else:
                portion = (count_based + vision_based) / 2
                logger.info(
                    "🔢 %s: many items (%d) → average(count=%.0fg, vision=%.0fg) = %.0fg",
                    item.name, item.item_count, count_based, vision_based, portion
                )
        elif count_based:
            portion = count_based
            logger.info(
                "🔢 %s: %d items × %.0fg = %.0fg",
                item.name, item.item_count, typical_g, portion
            )
        elif vision_based:
            portion = vision_based
        else:
            logger.warning(
                "⚠️ No portion estimate for %s, using typical: %.0fg",
                item.name, typical_g
            )
            portion = float(typical_g)

        grams.append(portion)

    # --- Ingredient Promotion Pass ---
    # Promote food-grade visible ingredients to standalone nutrition lookups.
    # These are ingredients ADDED to dishes (e.g. carrots in indomie) that
    # are not part of the standard recipe and need their own KB lookup.
    main_names_lower = {n.lower() for n in names}

    # Collect all unique ingredients across all detected foods
    all_ingredients: set = set()
    for ing_list in visible_ingredients:
        for ing in ing_list:
            all_ingredients.add(ing.lower().strip())

    for ingredient in all_ingredients:
        portion = get_ingredient_portion(ingredient)
        if portion is None:
            continue  # Not a promotable food-grade ingredient

        # Skip if already covered by a main food (substring dedup, both directions)
        already_covered = any(
            ingredient in main_name or main_name in ingredient
            for main_name in main_names_lower
        )
        if already_covered:
            continue

        # Promote to standalone food entry
        names.append(ingredient)
        grams.append(float(portion))
        confidences.append(0.7)
        oil_levels.append(None)
        visible_ingredients.append([])
        main_names_lower.add(ingredient)  # prevent duplicate promotions
        logger.info("🥕 Promoted ingredient: %s (%.0fg)", ingredient, float(portion))

    # --- Meal-level total weight sanity cap ---
    # A single Nigerian plate realistically weighs 400–700g. Stacking independent
    # per-item estimates can push totals to 900g+ without any single item hitting
    # its own max_reasonable_g. Scale all portions down proportionally when exceeded.
    MEAL_WEIGHT_SOFT_CAP = 750   # warn above this
    MEAL_WEIGHT_HARD_CAP = 900   # scale down above this
    total_grams = sum(grams)
    if total_grams > MEAL_WEIGHT_HARD_CAP and len(grams) > 0:
        scale = MEAL_WEIGHT_HARD_CAP / total_grams
        grams = [round(g * scale, 1) for g in grams]
        logger.warning(
            "⚠️ Meal total %.0fg exceeded hard cap (%dg) — scaled all portions by %.2f → %.0fg",
            total_grams, MEAL_WEIGHT_HARD_CAP, scale, sum(grams),
        )
    elif total_grams > MEAL_WEIGHT_SOFT_CAP:
        logger.warning(
            "⚠️ Meal total %.0fg exceeds soft cap (%dg) — review portions: %s",
            total_grams, MEAL_WEIGHT_SOFT_CAP,
            ", ".join(f"{n}={g:.0f}g" for n, g in zip(names, grams)),
        )

    return names, grams, confidences, oil_levels, visible_ingredients


async def handle_user_request(
    user_message: str,
    *,
    image_base64: Optional[str] = None,
    image_url: Optional[str] = None,
    user_id: str = "",
    user_gender: str = "female",
    user_age: int = 25,
    meal_type: Optional[str] = None,
    conversation_history: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Food logging orchestrator: Vision → Knowledge → Save to DB

    For chat/conversations, use ChatAgent directly.

    Args:
        meal_type: Optional meal type (breakfast, lunch, dinner, snack).
                   Used for meal-type aware portion estimation.

    Returns dict with:
    - vision: VisionResult
    - nutrition: KnowledgeResult
    - meal_id: saved meal ID
    """
    logger.info(f"🚀 Orchestrator: Food logging for user {user_id}, meal_type={meal_type}")

    # Step 1: Vision - Detect foods from image
    vision = _get_agent("vision")
    vision_result: VisionResult = await asyncio.wait_for(
        vision.analyze_image(
            image_base64=image_base64 or "",
            image_url=image_url,
            meal_type=meal_type,  # Pass meal_type for portion estimation
        ),
        timeout=200.0,
    )
    logger.info(f"   → Detected: {len(vision_result.detected_foods)} foods")

    # Step 2: Extract foods with validation (including oil detection data)
    food_names, portions_grams, confidences, oil_levels, visible_ingredients = _extract_foods_from_vision(vision_result)

    # Log confidence warnings for uncertain detections
    low_confidence_foods = [
        (name, conf) for name, conf in zip(food_names, confidences)
        if conf < LOW_CONFIDENCE_THRESHOLD
    ]
    if low_confidence_foods:
        for name, conf in low_confidence_foods:
            logger.warning(
                "⚠️ Low confidence detection: %s (%.0f%%) - may be inaccurate",
                name, conf * 100
            )

    # Step 3: Knowledge - Retrieve nutrition data
    knowledge = _get_agent("knowledge")

    knowledge_result: KnowledgeResult = await asyncio.wait_for(
        knowledge.retrieve_nutrition(
            food_names=food_names,
            portions_grams=portions_grams,
            vision_confidences=confidences,
            oil_levels=oil_levels,
            visible_ingredients=visible_ingredients,
        ),
        timeout=45.0,
    )
    logger.info(
        "   → Nutrition: %.0f cal, %.1fg protein",
        knowledge_result.total_calories,
        knowledge_result.total_protein
    )

    # Step 3: Save meal to database
    meal_id = None
    if user_id:
        try:
            # Ensure user exists
            user = await get_user(user_id)
            if not user:
                logger.info(f"   → Creating new user: {user_id}")
                await create_user(
                    user_id=user_id,
                    gender=user_gender,
                    age=user_age
                )

            # Prepare foods for database - ALL 16 NUTRIENTS + CONFIDENCE METADATA
            foods_for_db = []
            for i, food in enumerate(knowledge_result.foods):
                nutrients = food.total_nutrients
                portion_g = food.portion_consumed_grams

                # Validate portion against reasonable bounds
                # Note: These bounds are returned by knowledge agent from the food database
                min_g = getattr(food, 'min_reasonable_g', 50) if hasattr(food, 'min_reasonable_g') else 50
                max_g = getattr(food, 'max_reasonable_g', 500) if hasattr(food, 'max_reasonable_g') else 500

                if portion_g < min_g:
                    portion_validation = "low"
                elif portion_g > max_g:
                    portion_validation = "high"
                else:
                    portion_validation = "ok"

                foods_for_db.append({
                    "food_name": food.name,
                    "food_id": food.food_id,
                    "portion_grams": portion_g,
                    # Macros (5)
                    "calories": nutrients.calories,
                    "protein": nutrients.protein,
                    "carbohydrates": nutrients.carbohydrates,
                    "fat": nutrients.fat,
                    "fiber": nutrients.fiber,
                    # Minerals (6)
                    "iron": nutrients.iron,
                    "calcium": nutrients.calcium,
                    "zinc": nutrients.zinc,
                    "potassium": nutrients.potassium,
                    "sodium": nutrients.sodium,
                    "magnesium": nutrients.magnesium,
                    # Vitamins (5)
                    "vitamin_a": nutrients.vitamin_a,
                    "vitamin_c": nutrients.vitamin_c,
                    "vitamin_d": nutrients.vitamin_d,
                    "vitamin_b12": nutrients.vitamin_b12,
                    "folate": nutrients.folate,
                    "confidence": food.similarity_score,
                    # Confidence metadata (for transparency and debugging)
                    "vision_confidence": confidences[i] if i < len(confidences) else 1.0,
                    "knowledge_similarity": food.similarity_score,
                    "portion_validation": portion_validation,
                })

            # Log meal with validated meal_type (normalizes and falls back to time-based)
            actual_meal_type = _normalize_meal_type(meal_type)
            meal_record = await log_meal(
                user_id=user_id,
                meal_type=actual_meal_type,
                foods=foods_for_db,
                image_url=image_url,
            )
            meal_id = meal_record['meal_id']
            logger.info(f"   → Saved meal: {meal_id}")

            # Update user stats (async, don't wait)
            asyncio.create_task(calculate_and_update_user_stats(user_id))

        except Exception as db_error:
            logger.error(f"Database error: {db_error}")

    return {
        "workflow": "food_logging",
        "vision": vision_result,
        "nutrition": knowledge_result,
        "meal_id": meal_id,
    }


def handle_user_request_sync(**kwargs: Any) -> Dict[str, Any]:
    """Synchronous wrapper."""
    return asyncio.run(handle_user_request(**kwargs))

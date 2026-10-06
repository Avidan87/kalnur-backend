"""
Food Logging Stream

Real-time SSE streaming endpoint for food analysis.

Flow:
  Phase 1 — Vision runs, Kally narrates each detection event as it happens
  Phase 2 — Correction window opens (15s), SAM2 runs in parallel during this time
  Phase 3 — User confirms corrected food list → Knowledge Agent calculates nutrition

Two endpoints:
  POST /api/v1/food-logging-stream    — SSE stream (Vision + ingredient promotion)
  POST /api/v1/food-logging-calculate — Final nutrition calc on confirmed food list
"""

import asyncio
import base64
import json
import logging
import time
import traceback
from typing import AsyncGenerator, Optional

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from kai.agents.vision_agent import VisionAgent
from kai.agents.knowledge_agent import KnowledgeAgent
from kai.auth import get_current_user_id
from kai.database import (
    get_user,
    create_user,
    get_user_health_profile,
    log_meal,
    log_missing_food,
    mark_user_notified,
)
from kai.services.email_service import send_missing_food_email
from kai.food_registry import get_food_registry, get_ingredient_portion, PROMOTABLE_INGREDIENTS, get_canonical_food_name
from kai.jobs import calculate_and_update_user_stats
from kai.jobs.push_scheduler import send_milestone_notifications
from kai.orchestrator import _normalize_meal_type, _extract_foods_from_vision
from kai.services import get_goal_context
from kai.utils.meal_title import generate_meal_title

logger = logging.getLogger(__name__)

# Confidence threshold below which Kally asks a clarification question
CLARIFICATION_THRESHOLD = 0.80

# Similarity threshold below which a user-added food is considered "not in KB"
MISSING_FOOD_SIMILARITY_THRESHOLD = 0.60


# ============================================================================
# SSE Helper
# ============================================================================

def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


# ============================================================================
# Streaming Generator
# ============================================================================

async def stream_food_analysis(
    image_base64: str,
    meal_type: Optional[str],
    user_id: str,
) -> AsyncGenerator[str, None]:
    """
    Core SSE generator.

    Yields SSE events as the pipeline progresses:
      step            — general progress message
      detection       — main dishes detected by Vision Agent
      ingredients     — added ingredients promoted from visible_ingredients
      clarification_needed — low-confidence food needs user input
      correction_window   — signals frontend to show correction UI
      error           — something went wrong
    """
    try:
        # ----------------------------------------------------------------
        # Event 1 — Start
        # ----------------------------------------------------------------
        yield _sse({
            "type": "step",
            "step": "start",
            "message": "Let me take a proper look at this plate... 👀",
            "progress": 5,
        })

        # ----------------------------------------------------------------
        # Event 2 — Vision Agent
        # ----------------------------------------------------------------
        yield _sse({
            "type": "step",
            "step": "vision",
            "message": "Scanning for Nigerian foods...",
            "progress": 15,
        })

        vision_agent = VisionAgent()
        vision_result = await asyncio.wait_for(
            vision_agent.analyze_image(
                image_base64=image_base64,
                meal_type=meal_type,
            ),
            timeout=200.0,
        )

        detected = vision_result.detected_foods
        if not detected:
            yield _sse({
                "type": "error",
                "message": "I couldn't detect any food in this image. Try a clearer photo 📸",
                "progress": 100,
            })
            return

        # ----------------------------------------------------------------
        # Event 3 — Main dishes detected
        # ----------------------------------------------------------------
        main_food_names = [f.name for f in detected]
        main_food_confidences = [f.confidence for f in detected]

        # Build message based on number of foods found
        if len(main_food_names) == 1:
            detection_msg = f"I can see {main_food_names[0]}!"
        elif len(main_food_names) == 2:
            detection_msg = f"I can see {main_food_names[0]} and {main_food_names[1]}!"
        else:
            foods_str = ", ".join(main_food_names[:-1]) + f" and {main_food_names[-1]}"
            detection_msg = f"I can see {foods_str}!"

        yield _sse({
            "type": "detection",
            "step": "vision",
            "foods": main_food_names,
            "confidences": main_food_confidences,
            "message": detection_msg,
            "progress": 35,
        })

        # ----------------------------------------------------------------
        # Event 4 — Clarification for low-confidence foods
        # ----------------------------------------------------------------
        # For each food below the confidence threshold, fire a clarification event.
        # The frontend shows quick-pick buttons from the top-2 KB matches.
        knowledge_agent = KnowledgeAgent()
        registry = get_food_registry()

        for food in detected:
            if food.confidence < CLARIFICATION_THRESHOLD:
                # Find top-2 closest matches from KB to offer as options
                try:
                    matches = await asyncio.to_thread(
                        knowledge_agent.vector_db.search, food.name, 2
                    )
                    options = [m["metadata"]["name"] for m in matches if m.get("metadata")]
                except Exception:
                    options = []

                yield _sse({
                    "type": "clarification_needed",
                    "step": "vision",
                    "food_name": food.name,
                    "confidence": round(food.confidence, 2),
                    "message": f"I'm not 100% sure about this one — is this {' or '.join(options) if options else 'the right dish'}? 🤔",
                    "options": options,
                    "progress": 40,
                })

        # ----------------------------------------------------------------
        # Event 5 — Added ingredients promoted
        # ----------------------------------------------------------------
        all_added_ingredients = []
        main_names_lower = {f.name.lower() for f in detected}

        for food in detected:
            ingredients = getattr(food, "visible_ingredients", []) or []
            for ing in ingredients:
                ing_lower = ing.lower().strip()
                portion = get_ingredient_portion(ing_lower)
                if portion is None:
                    continue
                # Dedup against main foods
                already_covered = any(
                    ing_lower in main_name or main_name in ing_lower
                    for main_name in main_names_lower
                )
                if already_covered or ing_lower in [a["name"] for a in all_added_ingredients]:
                    continue
                all_added_ingredients.append({"name": ing_lower, "portion": portion})
                main_names_lower.add(ing_lower)

        if all_added_ingredients:
            names_str = ", ".join(a["name"] for a in all_added_ingredients)
            yield _sse({
                "type": "ingredients",
                "step": "ingredients",
                "added": [a["name"] for a in all_added_ingredients],
                "message": f"Wait — I also spotted {names_str} in there 🥕",
                "progress": 50,
            })

        # ----------------------------------------------------------------
        # Event 6 — Correction window
        # Build the full working food list for the frontend to display as chips.
        # Use the same portion logic as _extract_foods_from_vision so realtime
        # and quick mode produce consistent numbers:
        #   Priority 1 — item_count × typical_portion_g  (countable foods)
        #   Priority 2 — Vision's estimated_grams         (volume foods)
        #   Priority 3 — KB typical_portion_g fallback
        # ----------------------------------------------------------------
        def _compute_portion(f) -> float:
            food_info = registry.get_food_info(f.name)
            typical_g = food_info.get("typical_portion_g", 150) if food_info else 150
            min_g     = food_info.get("min_reasonable_g", 30)   if food_info else 30
            max_g     = food_info.get("max_reasonable_g", 500)  if food_info else 500
            item_count = getattr(f, "item_count", None)
            estimated  = getattr(f, "estimated_grams", None)

            count_based  = float(item_count) * float(typical_g) if (item_count and item_count > 0) else None
            vision_based = float(max(min_g, min(estimated, max_g))) if (estimated and estimated > 0) else None

            # Take the larger of the two estimates.
            # This prevents item_count=1 from overriding a large visual estimate
            # (e.g. a whole loaf photographed returns item_count=1 × 30g = 30g,
            # but Vision's estimated_grams might correctly say 300g — we want 300g).
            if count_based and vision_based:
                return max(count_based, vision_based)
            if count_based:
                return count_based
            if vision_based:
                return vision_based
            return float(typical_g)

        all_foods = [
            {
                "name": f.name,
                "confidence": round(f.confidence, 2),
                "promoted": False,
                "portion_grams": _compute_portion(f),
                "oil_level": getattr(f, "oil_amount_estimate", None),
                "visible_ingredients": getattr(f, "visible_ingredients", []) or [],
            }
            for f in detected
        ] + [
            {"name": a["name"], "confidence": 0.7, "promoted": True, "portion_grams": a["portion"], "oil_level": None, "visible_ingredients": []}
            for a in all_added_ingredients
        ]

        yield _sse({
            "type": "correction_window",
            "step": "waiting",
            "foods": all_foods,
            "message": "Does this look right? Fix anything I got wrong before I calculate 🙏",
            "timeout_seconds": 60,
            "progress": 55,
        })

        # ----------------------------------------------------------------
        # Event 7 — SAM2 segmentation (runs in background, no await needed here —
        # the frontend fires /food-logging-calculate after user confirms,
        # and the orchestrator handles SAM2 there. We just narrate the step.)
        # ----------------------------------------------------------------
        yield _sse({
            "type": "step",
            "step": "segmentation",
            "message": "Measuring portions while you review...",
            "progress": 65,
        })

    except asyncio.TimeoutError:
        yield _sse({
            "type": "error",
            "message": "Analysis timed out — please try again 🙏",
            "progress": 100,
        })
    except Exception as e:
        logger.error("❌ SSE stream error: %s\n%s", e, traceback.format_exc())
        yield _sse({
            "type": "error",
            "message": "Something went wrong during analysis — please try again 🙏",
            "progress": 100,
        })


async def _send_missing_food_notification(
    user_id: str,
    missing_foods: list[str],
    logged_foods: list[str],
    food_name: str,
) -> None:
    """
    Fire Email 1 for a missing food, delayed by 1 hour.

    The delay ensures the email doesn't feel redundant — the user just
    saw Kally's in-app message. An hour later it serves as a considered
    follow-up rather than an immediate automated ping.
    """
    try:
        await asyncio.sleep(3600)  # 1 hour

        # Re-check: did this user already get notified while we were waiting?
        # (e.g. they triggered the same food again within the hour)
        from kai.database.missing_foods_operations import log_missing_food as _check
        # Reuse mark_user_notified check indirectly — just attempt to send,
        # notified_user_ids guard in log_missing_food will have caught duplicates
        user = await get_user(user_id)
        if not user:
            return
        email = user.get("email")
        name = user.get("first_name") or user.get("full_name") or "there"
        if not email:
            return
        send_missing_food_email(
            to=email,
            name=name,
            missing_foods=missing_foods,
            logged_foods=logged_foods,
        )
        await mark_user_notified(food_name, user_id)
        logger.info("📧 Missing food email sent to %s for '%s' (1hr delay)", email, food_name)
    except asyncio.CancelledError:
        logger.info("📧 Missing food email task cancelled for '%s'", food_name)
    except Exception as e:
        logger.warning("⚠️ Failed to send missing food email: %s", e)


# ============================================================================
# Calculate Endpoint Handler
# ============================================================================

async def calculate_nutrition(
    confirmed_foods: list[dict],
    image_base64: str,
    meal_type: Optional[str],
    user_id: str,
    scene_description: Optional[str] = None,
) -> dict:
    """
    Run Knowledge Agent on the user-confirmed food list and save to DB.

    Args:
        confirmed_foods: List of {"name": str, "portion_grams": float | None}
                         User has already corrected/added/removed foods.
        image_base64: Original image (for SAM2 portion estimation if portions missing)
        meal_type: breakfast / lunch / dinner / snack
        user_id: Authenticated user

    Returns:
        Full nutrition result dict (same shape as existing food-logging-upload response)
    """
    start = time.time()

    # ----------------------------------------------------------------
    # Step 0a — Upload meal image to Supabase Storage.
    # Converts image_base64 → JPEG bytes → uploads to meal-images bucket.
    # Saves the public URL so history/dashboard can show the photo thumbnail.
    # Non-fatal: if upload fails we log a warning and continue without image_url.
    # ----------------------------------------------------------------
    image_url: Optional[str] = None
    if image_base64:
        try:
            from kai.database.db_setup import get_supabase
            raw_b64 = image_base64
            if "," in image_base64:
                raw_b64 = image_base64.split(",", 1)[1]
            image_bytes = base64.b64decode(raw_b64)
            storage_path = f"{user_id}/{int(time.time() * 1000)}.jpg"
            supabase_client = get_supabase()
            supabase_client.storage.from_("meal-images").upload(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": "image/jpeg", "upsert": "false"},
            )
            supabase_url = supabase_client.supabase_url
            image_url = f"{supabase_url}/storage/v1/object/public/meal-images/{storage_path}"
            logger.info("🖼️ Meal image uploaded: %s", image_url)
        except Exception as _upload_err:
            logger.warning("⚠️ Meal image upload failed: %s — saving without image_url", _upload_err)

    # ----------------------------------------------------------------
    # Step 0b — Get scene_description from vision if not already provided.
    # Run a quick vision pass on the image to get meal_context (GPT-4o's
    # plain-English description of what it sees). This is saved to DB so
    # Kally can answer visual questions about meals later ("how many fish?").
    # Only runs if no scene_description was passed in AND image is available.
    # ----------------------------------------------------------------
    if not scene_description and image_base64:
        try:
            raw_b64 = image_base64
            if "," in image_base64:
                raw_b64 = image_base64.split(",", 1)[1]
            _scene_agent = VisionAgent()
            _scene_result = await asyncio.wait_for(
                _scene_agent.analyze_image(
                    image_base64=raw_b64,
                    meal_type=meal_type,
                ),
                timeout=90.0,
            )
            scene_description = _scene_result.meal_context or None
            logger.info("🖼️ Scene description captured: %s", (scene_description or "")[:80])
        except Exception as _e:
            logger.warning("⚠️ Scene description extraction failed: %s — proceeding without it", _e)

    # ----------------------------------------------------------------
    # Step 1 — Resolve portion_grams for every confirmed food.
    #
    # Priority order:
    #   1. Frontend already sent portion_grams > 0 (from correction_window) → use it
    #   2. Food has no portion (user manually added it) → run full Vision re-scan
    #      on the original image asking specifically for that food (GPT-4o + SAM2 + Depth)
    #   3. Vision re-scan finds nothing → KB canonical typical_portion_g fallback
    # ----------------------------------------------------------------
    food_names = [f["name"] for f in confirmed_foods]
    portions_grams = []

    registry = get_food_registry()
    knowledge_agent = KnowledgeAgent()

    MAIN_DISH_CATEGORIES = {"starch", "swallow", "protein", "soup", "protein_dish", "snack"}
    MEAL_TYPE_SCALE = {"breakfast": 0.75, "snack": 0.65, "lunch": 1.0, "dinner": 1.0}

    def _kb_typical(food_name: str) -> float:
        """KB canonical typical portion — last resort fallback."""
        canonical_name = get_canonical_food_name(food_name)
        info = registry.get_food_info(canonical_name)
        if info:
            typical = info.get("typical_portion_g", 150)
            min_g = info.get("min_reasonable_g", 50)
            max_g = info.get("max_reasonable_g", 300)
            category = info.get("category", "")
            if category in MAIN_DISH_CATEGORIES:
                scale = MEAL_TYPE_SCALE.get(meal_type or "lunch", 1.0)
                typical = max(min_g, min(typical * scale, max_g))
            return float(typical)
        return 150.0

    # Quantity label → gram multiplier relative to KB typical portion
    # "small" = 0.6×, "medium" = 1.0×, "large" = 1.5×
    QUANTITY_SCALE = {"small": 0.6, "medium": 1.0, "large": 1.5}

    def _label_based_portion(food_name: str, food_role: str | None, quantity_label: str | None) -> float:
        """
        Estimate portion purely from food_role + quantity_label when Vision finds nothing.
        Uses KB typical as the medium baseline and scales from there.
        """
        base = _kb_typical(food_name)
        scale = QUANTITY_SCALE.get(quantity_label or "medium", 1.0)
        # Ingredients are always smaller — cap at half the main-dish base
        if food_role == "ingredient":
            base = min(base, 50.0)
        portion = base * scale
        logger.info(
            "📐 Label-based portion for '%s' (role=%s, qty=%s): %.0fg",
            food_name, food_role, quantity_label, portion,
        )
        return portion

    async def _vision_rescan_portion(food_name: str, food_role: str | None, quantity_label: str | None) -> float:
        """
        Run the full Vision pipeline (GPT-4o + SAM2 + Depth) on the original image,
        targeted at a specific food the user added manually.

        Priority:
          1. Vision finds the food → use Vision estimate (guided by label hint)
          2. Vision finds nothing  → fall back to label-based portion
          3. No label either       → fall back to KB typical
        """
        if not image_base64:
            # No image — go straight to label fallback
            return _label_based_portion(food_name, food_role, quantity_label)
        try:
            logger.info("🔍 Vision re-scan for user-added food: '%s'", food_name)
            # Strip data URL prefix if present — GPT-4o expects raw base64 only
            # Frontend stores full data URLs: "data:image/jpeg;base64,/9j/..."
            raw_base64 = image_base64
            if "," in image_base64:
                raw_base64 = image_base64.split(",", 1)[1]

            # Build a richer description using the label context if available
            label_hint = ""
            if food_role and quantity_label:
                label_hint = f" The user said it is a {food_role.replace('_', ' ')} and the amount is {quantity_label}."
            vision_agent = VisionAgent()
            vision_result = await asyncio.wait_for(
                vision_agent.analyze_image(
                    image_base64=raw_base64,
                    user_description=(
                        f"Focus specifically on '{food_name}' in this image."
                        f" Estimate its portion size accurately.{label_hint}"
                    ),
                    meal_type=meal_type,
                ),
                timeout=120.0,
            )
            # Find the matching food in Vision's result
            for detected in vision_result.detected_foods:
                if get_canonical_food_name(detected.name) == get_canonical_food_name(food_name):
                    portion = detected.estimated_grams
                    if portion and portion > 0:
                        logger.info("✅ Vision re-scan found '%s': %.0fg", food_name, portion)
                        return float(portion)
            logger.warning("⚠️ Vision re-scan did not find '%s' — using label fallback", food_name)
        except Exception as e:
            logger.warning("⚠️ Vision re-scan failed for '%s': %s — using label fallback", food_name, e)

        # Vision blind — use food_role + quantity_label if present, else KB typical
        if food_role and quantity_label:
            return _label_based_portion(food_name, food_role, quantity_label)
        return _kb_typical(food_name)

    # Identify which foods need a Vision re-scan (no portion from correction_window)
    foods_needing_rescan = [
        f for f in confirmed_foods
        if not (f.get("portion_grams") and f["portion_grams"] > 0)
    ]

    # Run all re-scans in parallel — one Vision call per missing food
    rescan_portions: dict[str, float] = {}
    if foods_needing_rescan:
        rescan_results = await asyncio.gather(
            *[
                _vision_rescan_portion(
                    f["name"],
                    f.get("food_role"),
                    f.get("quantity_label"),
                )
                for f in foods_needing_rescan
            ],
            return_exceptions=False,
        )
        rescan_portions = {
            f["name"]: portion
            for f, portion in zip(foods_needing_rescan, rescan_results)
        }

    # Build final portions list in confirmed_foods order
    for food in confirmed_foods:
        if food.get("portion_grams") and food["portion_grams"] > 0:
            portions_grams.append(float(food["portion_grams"]))
        else:
            portions_grams.append(rescan_portions.get(food["name"], _kb_typical(food["name"])))

    confidences = [f.get("confidence", 0.8) for f in confirmed_foods]
    oil_levels = [f.get("oil_level", None) for f in confirmed_foods]
    visible_ingredients = [f.get("visible_ingredients", []) or [] for f in confirmed_foods]

    # ----------------------------------------------------------------
    # Step 2 — Identify missing foods + build partial confirmed list
    #
    # Use FoodRegistry (in-memory JSONL) as the source of truth — NOT
    # the vector index. The vector index can be stale if new foods were
    # added to the JSONL but pgvector was not re-indexed, which caused
    # foods that exist in the Nigerian foods database to be incorrectly
    # flagged as missing.
    #
    # We separate confirmed_foods into:
    #   known_foods   → proceed to nutrition calc
    #   missing_foods → flag, fire email, exclude from calc
    # ----------------------------------------------------------------
    known_indices: list[int] = []
    flagged_missing: list[str] = []

    for i, food_name in enumerate(food_names):
        try:
            canonical = get_canonical_food_name(food_name)
            if registry.get_food_info(canonical):
                known_indices.append(i)
            else:
                flagged_missing.append(food_name)
                should_email = await log_missing_food(food_name, user_id)
                logger.info("📋 Logged missing food: '%s' (email=%s)", food_name, should_email)
                if should_email:
                    # Fire Email 1 in background — don't block the response
                    asyncio.create_task(_send_missing_food_notification(
                        user_id=user_id,
                        missing_foods=flagged_missing,
                        logged_foods=[food_names[j] for j in known_indices],
                        food_name=food_name,
                    ))
        except Exception as e:
            # On error, include the food — better to calculate with it than skip
            known_indices.append(i)
            logger.warning("⚠️ KB check failed for '%s': %s — including in calc", food_name, e)

    # If ALL foods are missing — stop entirely, nothing to calculate
    if not known_indices:
        return {
            "success": False,
            "message": "I don't have nutritional data for the foods you added yet. I've flagged them and we'll add them soon — I'll let you know when they're ready.",
            "detected_foods": [],
            "priority_nutrients": {},
            "meal_id": None,
            "missing_foods": flagged_missing,
            "processing_time_ms": int((time.time() - start) * 1000),
        }

    # Filter lists to known foods only for the nutrition pipeline
    confirmed_foods_known = [confirmed_foods[i] for i in known_indices]
    food_names      = [food_names[i] for i in known_indices]
    portions_grams  = [portions_grams[i] for i in known_indices]
    confidences     = [confidences[i] for i in known_indices]
    oil_levels      = [oil_levels[i] for i in known_indices]
    visible_ingredients = [visible_ingredients[i] for i in known_indices]

    # ----------------------------------------------------------------
    # Step 3 — Knowledge Agent nutrition lookup (known foods only)
    # ----------------------------------------------------------------
    knowledge_result = await asyncio.wait_for(
        knowledge_agent.retrieve_nutrition(
            food_names=food_names,
            portions_grams=portions_grams,
            vision_confidences=confidences,
            oil_levels=oil_levels,
            visible_ingredients=visible_ingredients,
        ),
        timeout=45.0,
    )

    # ----------------------------------------------------------------
    # Step 4 — Save meal to DB
    # ----------------------------------------------------------------
    meal_id = None
    try:
        user = await get_user(user_id)
        if not user:
            await create_user(user_id=user_id, gender="female", age=25)

        actual_meal_type = _normalize_meal_type(meal_type)

        foods_for_db = []
        for i, food in enumerate(knowledge_result.foods):
            nutrients = food.total_nutrients
            foods_for_db.append({
                "food_name": food.name,
                "food_id": food.food_id,
                "portion_grams": food.portion_consumed_grams,
                "calories": nutrients.calories,
                "protein": nutrients.protein,
                "carbohydrates": nutrients.carbohydrates,
                "fat": nutrients.fat,
                "fiber": nutrients.fiber,
                "iron": nutrients.iron,
                "calcium": nutrients.calcium,
                "zinc": nutrients.zinc,
                "potassium": nutrients.potassium,
                "sodium": nutrients.sodium,
                "magnesium": nutrients.magnesium,
                "vitamin_a": nutrients.vitamin_a,
                "vitamin_c": nutrients.vitamin_c,
                "vitamin_d": nutrients.vitamin_d,
                "vitamin_b12": nutrients.vitamin_b12,
                "folate": nutrients.folate,
                "confidence": food.similarity_score,
                "vision_confidence": confidences[i] if i < len(confidences) else 0.8,
                "knowledge_similarity": food.similarity_score,
                "portion_validation": "ok",
            })

        meal_record = await log_meal(
            user_id=user_id,
            meal_type=actual_meal_type,
            foods=foods_for_db,
            image_url=image_url,
            scene_description=scene_description,
        )
        meal_id = meal_record["meal_id"]
        logger.info("✅ Meal saved: %s", meal_id)

        # Background stats update
        asyncio.create_task(calculate_and_update_user_stats(user_id))
        asyncio.create_task(send_milestone_notifications(user_id))

    except Exception as db_error:
        logger.error("❌ DB save failed: %s", db_error)

    # ----------------------------------------------------------------
    # Step 5 — Build response with priority nutrients
    # ----------------------------------------------------------------
    profile = await get_user_health_profile(user_id)
    health_goal = profile.get("health_goals", "general_wellness") if profile else "general_wellness"
    gender = profile.get("gender") if profile else None
    age = profile.get("age") if profile else None
    active_calorie_goal = (
        profile.get("custom_calorie_goal") or profile.get("active_calorie_goal")
    ) if profile else None

    goal_context = get_goal_context(health_goal, gender, age, active_calorie_goal)

    def get_nutrient(name: str) -> float:
        attr_name = f"total_{name}" if not name.startswith("total_") else name
        return getattr(knowledge_result, attr_name, 0.0)

    priority_nutrients = {
        nutrient: get_nutrient(nutrient)
        for nutrient in goal_context["priority_nutrients"]
    }
    # Always include calories regardless of health goal
    priority_nutrients["calories"] = get_nutrient("calories")

    partial = len(flagged_missing) > 0
    message = (
        f"Meal logged! I couldn't find data for {', '.join(flagged_missing)} — I've flagged it and will let you know when it's added."
        if partial
        else "Meal logged! Ask Kally in chat for feedback 💬"
    )

    detected_foods_list = [
        {
            "name": f.name,
            "nigerian_name": None,
            "confidence": f.similarity_score,
            "estimated_portion": f"{int(f.portion_consumed_grams)}g",
            "estimated_grams": f.portion_consumed_grams,
            "visible_ingredients": [],
            "cooking_method": None,
            "oil_sheen_visible": None,
            "oil_amount_estimate": None,
        }
        for f in knowledge_result.foods
    ]

    meal_title = generate_meal_title([f["name"] for f in detected_foods_list])

    return {
        "success": True,
        "message": message,
        "detected_foods": detected_foods_list,
        "priority_nutrients": priority_nutrients,
        "meal_id": meal_id,
        "meal_title": meal_title,
        "missing_foods": flagged_missing,
        "processing_time_ms": int((time.time() - start) * 1000),
    }

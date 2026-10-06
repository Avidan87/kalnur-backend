"""
Vision Agent - Nigerian Food Detection and Analysis

Uses GPT-4o to detect and analyze Nigerian foods from images.
Specialized for recognizing 80+ Nigerian dishes with cultural context.

Uses OpenAI Agents SDK for orchestrator consistency.
"""

import asyncio
import base64
import io
import json
import logging
from typing import Dict, Any, Optional, List, Annotated
from datetime import datetime
from openai import AsyncOpenAI
from agents import Agent, function_tool
from dotenv import load_dotenv
import os
import httpx

from kai.models import VisionResult, DetectedFood
from kai.mcp_servers.depth_estimation_client import get_portion_estimate, get_portions_batch, get_depth_client
from kai.food_registry import get_food_registry, get_canonical_food_name
import numpy as np
from PIL import Image

load_dotenv()
logger = logging.getLogger(__name__)


# Meal-type aware portion limits (grams)
# Based on Nigerian portion research and nutritional guidelines
MEAL_PORTION_LIMITS = {
    "breakfast": {"max_total": 500.0, "max_per_food": 300.0},
    "lunch": {"max_total": 800.0, "max_per_food": 450.0},
    "dinner": {"max_total": 700.0, "max_per_food": 400.0},
    "snack": {"max_total": 250.0, "max_per_food": 150.0},
    "default": {"max_total": 700.0, "max_per_food": 400.0},
}


def get_portion_limits(meal_type: Optional[str]) -> dict:
    """Get portion limits based on meal type."""
    if meal_type and meal_type.lower() in MEAL_PORTION_LIMITS:
        return MEAL_PORTION_LIMITS[meal_type.lower()]
    return MEAL_PORTION_LIMITS["default"]


class VisionAgent:
    """
    Vision Agent for detecting Nigerian foods from meal images.

    Uses OpenAI Agents SDK with vision tools for orchestrator integration.

    Capabilities:
    - Detect multiple Nigerian foods in a single image
    - Estimate portion sizes (grams)
    - Identify cooking methods and visible ingredients
    - Provide confidence scores for each detection
    - Handle various image qualities and lighting conditions
    """

    def __init__(self, openai_api_key: Optional[str] = None):
        """Initialize Vision Agent with GPT-4o."""
        openai_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise ValueError("OPENAI_API_KEY not found")
        self.client = AsyncOpenAI(api_key=openai_key)
        self.model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")

        self.max_image_size = 2048  # Max dimension for processing

        # Load canonical food names from the knowledge base registry
        # This ensures Vision outputs match exactly what Knowledge Agent expects
        self.food_registry = get_food_registry()
        self.known_foods = self.food_registry.get_all_names()

        logger.info(f"✓ Vision Agent loaded {len(self.known_foods)} canonical food names from registry")

        # Setup agent with vision tools
        self._setup_agent()

    def _setup_agent(self):
        """
        Setup OpenAI Agent with Nigerian food detection tools using @function_tool decorator.
        """
        # Create agent instructions
        agent_instructions = f"""You are Kalnur's Vision Agent, an expert in Nigerian food recognition.

Your mission is to accurately detect and identify Nigerian foods from meal images to help Nigerians track their nutrition intake.

**Your Expertise:**
- 80+ Nigerian dishes including: {', '.join(self.known_foods[:10])}... and more
- Portion size estimation using typical Nigerian serving sizes
- Ingredient identification from visual appearance
- Cooking method recognition
- Cultural context and regional variations

**Your Approach:**
1. Carefully analyze meal images for all visible Nigerian foods
2. Estimate portions based on typical Nigerian serving sizes
3. Assign confidence scores based on visual clarity
4. Request clarification when uncertain
5. Provide culturally relevant context

**Detection Priorities:**
- Accuracy over speed - Nigerians' health depends on correct tracking
- Cultural awareness - recognize regional variations and local names
- Practical portions - use real-world Nigerian serving sizes
- Clear communication - explain what you see and why

Use the analyze_nigerian_food_image tool to process images and return structured detection results."""

        # Create tool using @function_tool decorator
        analyze_food_tool = self._create_analyze_food_tool()

        self.agent = Agent(
            name="Kalnur Vision Agent",
            instructions=agent_instructions,
            model=self.model,  # OpenAI model for SDK agent wrapper
            tools=[analyze_food_tool]
        )

        logger.info(f"✓ Vision Agent initialized (model: {self.model})")

    def _create_analyze_food_tool(self):
        """
        Create the analyze_nigerian_food_image tool with @function_tool decorator.

        NOTE: This tool is created for SDK compatibility but the actual analysis
        is done via _tool_analyze_nigerian_food_image which uses _build_detection_prompt.
        This ensures we use the latest prompt with all food names from the registry.
        """
        # Capture self for use in the tool function
        vision_agent = self

        @function_tool
        async def analyze_nigerian_food_image(
            image_base64: Annotated[str, "Base64 encoded meal image"],
            user_description: Annotated[Optional[str], "Optional user description of the meal"] = None,
            meal_type: Annotated[Optional[str], "Type of meal (breakfast, lunch, dinner, snack)"] = None
        ) -> str:
            """
            Analyze a meal image to detect and identify Nigerian foods.
            Returns detailed information about detected dishes including names, portions,
            ingredients, cooking methods, and confidence scores.
            """
            # Delegate to the main tool function which uses the updated prompt
            return await vision_agent._tool_analyze_nigerian_food_image(
                image_base64=image_base64,
                user_description=user_description,
                meal_type=meal_type
            )

        return analyze_nigerian_food_image

    async def _warmup_modal_servers(self) -> None:
        """
        Fire health-check pings to SAM and Depth Modal servers concurrently.
        Called in parallel with the GPT-4o call so cold-start latency is hidden
        behind GPT-4o's processing time (~3-5s).
        """
        sam_url = os.getenv("SAM_SEGMENTATION_URL")
        depth_client = get_depth_client()

        async def ping_sam():
            if not sam_url:
                return
            try:
                async with httpx.AsyncClient(timeout=30.0) as c:
                    await c.get(f"{sam_url.rstrip('/')}/health")
                logger.info("🔥 SAM Modal server warmed up")
            except Exception:
                pass  # Warmup failure is non-fatal

        async def ping_depth():
            try:
                await depth_client.health_check()
                logger.info("🔥 Depth Modal server warmed up")
            except Exception:
                pass  # Warmup failure is non-fatal

        await asyncio.gather(ping_sam(), ping_depth())

    async def analyze_image(
        self,
        image_base64: str,
        image_url: Optional[str] = None,
        user_description: Optional[str] = None,
        meal_type: Optional[str] = None
    ) -> VisionResult:
        """
        Analyze meal image and detect Nigerian foods.
        """
        try:
            logger.info("🔍 Starting Nigerian food vision analysis (SDK mode)")

            # Run vision call AND Modal server warm-up pings in parallel.
            # By the time vision finishes (~3-5s), SAM + Depth containers are warm.
            result_json, _ = await asyncio.gather(
                self._tool_analyze_nigerian_food_image(
                    image_base64=image_base64,
                    user_description=user_description,
                    meal_type=meal_type
                ),
                self._warmup_modal_servers()
            )

            # Parse tool result
            result_dict = json.loads(result_json)

            depth_estimation_used = False
            portion_grams = None

            # (We need detected_foods info for portion logic)
            detected_foods = result_dict.get("detected_foods", [])
            if (image_url or image_base64) and detected_foods:
                logger.info("📏 Starting per-food portion estimation with SAM segmentation")

                # Decode image for SAM segmentation
                img_array = None
                if image_base64:
                    img_bytes = base64.b64decode(image_base64)
                    img_array = np.array(Image.open(io.BytesIO(img_bytes)))
                elif image_url:
                    # Fetch image from URL
                    response = httpx.get(image_url, timeout=30.0)
                    img_array = np.array(Image.open(io.BytesIO(response.content)))

                # Use SAM 2 for pixel-perfect food segmentation
                # OPTIMIZATION: Use SAM 2 for 2+ foods (skip for single dishes)
                # Single dishes don't need segmentation (portion = whole plate)
                # 2+ foods benefit from accurate segmentation (different portion sizes)
                use_sam = len(detected_foods) >= 2 and img_array is not None

                if use_sam:
                    try:
                        logger.info("🔍 Using SAM 2 (Modal GPU) for pixel-perfect food segmentation")

                        # Extract food names for segmentation
                        food_names = [food.get("name") for food in detected_foods]

                        # Call Modal SAM 2 endpoint (async HTTP — non-blocking)
                        sam_url = os.getenv("SAM_SEGMENTATION_URL")
                        if not sam_url:
                            raise ValueError("SAM_SEGMENTATION_URL not set in environment")

                        async with httpx.AsyncClient(timeout=60.0) as sam_client:
                            sam_response = await sam_client.post(
                                f"{sam_url.rstrip('/')}/segment",
                                json={
                                    "image_base64": image_base64,
                                    "food_names": food_names,
                                }
                            )
                            sam_response.raise_for_status()
                            sam_data = sam_response.json()

                        # Convert JSON lists back to numpy boolean arrays
                        food_masks = {
                            name: np.array(mask, dtype=bool)
                            for name, mask in sam_data["masks"].items()
                        }

                        logger.info(f"✓ SAM 2 (Modal) generated {len(food_masks)} pixel masks for {len(detected_foods)} foods")

                        # Convert masks to bboxes for batch depth estimation
                        # (MCP server currently expects bboxes, we'll update it later to accept masks)
                        # Use meal-type aware portion limits
                        portion_limits = get_portion_limits(meal_type)
                        MAX_REASONABLE_PORTION_PER_FOOD = portion_limits["max_per_food"]
                        img_height, img_width = img_array.shape[:2]

                        bboxes_for_batch = []
                        food_types_for_batch = []
                        food_to_batch_index = {}

                        for idx, (food_name, mask) in enumerate(food_masks.items()):
                            # Convert pixel mask to bounding box (tight fit around masked region)
                            ys, xs = np.where(mask)

                            if len(xs) > 0 and len(ys) > 0:
                                x1, x2 = int(np.min(xs)), int(np.max(xs))
                                y1, y2 = int(np.min(ys)), int(np.max(ys))

                                bbox_area = (x2 - x1) * (y2 - y1)
                                mask_area = np.sum(mask)
                                coverage = mask_area / bbox_area if bbox_area > 0 else 0

                                logger.info(
                                    f"✓ {food_name}: mask covers {mask_area} pixels "
                                    f"({mask_area / (img_width * img_height):.1%} of image, "
                                    f"{coverage:.1%} fill ratio in bbox)"
                                )

                                food_to_batch_index[idx] = len(bboxes_for_batch)
                                bboxes_for_batch.append((x1, y1, x2, y2))
                                food_types_for_batch.append(food_name)
                            else:
                                # Empty mask - use default portion
                                logger.warning(f"⚠️ {food_name}: empty mask, will use default portion (150g)")
                                food_to_batch_index[idx] = None

                        # 🚀 BATCH PROCESSING: Single API call for all foods!
                        logger.info(f"🚀 Using BATCH API for {len(bboxes_for_batch)} foods (single depth estimation run)")

                        try:
                            batch_results = await get_portions_batch(
                                image_base64=image_base64,
                                bboxes=bboxes_for_batch,
                                food_types=food_types_for_batch,
                                reference_object="plate"
                            )

                            # Assign results to foods
                            for idx, food in enumerate(detected_foods):
                                batch_idx = food_to_batch_index.get(idx)

                                if batch_idx is not None:
                                    # Food has a mask - get result from batch
                                    result = batch_results[batch_idx]
                                    portion_grams = result.get("portion_grams", 200.0)

                                    # Cap at reasonable max
                                    if portion_grams > MAX_REASONABLE_PORTION_PER_FOOD:
                                        logger.warning(f"⚠️ {food.get('name')}: {portion_grams}g → capped at {MAX_REASONABLE_PORTION_PER_FOOD}g")
                                        portion_grams = MAX_REASONABLE_PORTION_PER_FOOD

                                    food["estimated_grams"] = portion_grams
                                    logger.info(
                                        f"✓ {food.get('name')}: {portion_grams:.1f}g "
                                        f"(confidence: {result.get('confidence', 0):.2f})"
                                    )
                                else:
                                    # Food has no mask - use default portion
                                    food["estimated_grams"] = 150.0
                                    logger.info(f"✓ {food.get('name')}: 150.0g (default, no mask)")

                        except Exception as e:
                            logger.error(f"❌ Batch estimation failed: {e}, using defaults")
                            # Fallback to defaults
                            for food in detected_foods:
                                food["estimated_grams"] = 200.0

                        # Check total meal portion and scale down if unrealistic
                        # Use meal-type aware limits (breakfast ~400g, lunch/dinner ~600g)
                        total_estimated = sum(food["estimated_grams"] for food in detected_foods)
                        MAX_REASONABLE_MEAL = portion_limits["max_total"]

                        if total_estimated > MAX_REASONABLE_MEAL:
                            scale_factor = MAX_REASONABLE_MEAL / total_estimated
                            logger.warning(
                                f"⚠️ Total meal {total_estimated:.0f}g exceeds realistic max ({MAX_REASONABLE_MEAL}g). "
                                f"Scaling all portions down by {scale_factor:.2f}x to prevent over-estimation."
                            )
                            for food in detected_foods:
                                original = food["estimated_grams"]
                                food["estimated_grams"] = original * scale_factor
                                logger.info(f"   📉 {food.get('name')}: {original:.0f}g → {food['estimated_grams']:.0f}g")
                        else:
                            logger.info(f"✅ Total meal portion {total_estimated:.0f}g is reasonable")

                        depth_estimation_used = True

                    except Exception as e:
                        logger.error(f"❌ SAM 2 segmentation failed: {e}, falling back to division method")
                        use_sam = False

                # Fallback: divide total portion by food-category density weights.
                # Swallows (eba, pounded yam) are denser and heavier than soups;
                # an even split systematically underestimates swallows and overestimates soups.
                if not use_sam:
                    try:
                        portion = await get_portion_estimate(
                            image_url=image_url,
                            image_base64=image_base64,
                            reference_object="plate"
                        )
                        portion_grams = portion.get("portion_grams")

                        # Use meal-type aware limits (consistent with SAM path)
                        portion_limits = get_portion_limits(meal_type)
                        MAX_REASONABLE_MEAL = portion_limits["max_total"]
                        if portion_grams and portion_grams > 0:
                            if portion_grams > MAX_REASONABLE_MEAL:
                                logger.warning(f"⚠️ Total portion {portion_grams}g exceeds max ({MAX_REASONABLE_MEAL}g) for {meal_type or 'unknown'} meal, capping")
                                portion_grams = MAX_REASONABLE_MEAL

                            MAX_PER_FOOD = portion_limits["max_per_food"]

                            # Density weights by food category.
                            # Swallows are dense solids; soups are mostly liquid.
                            # A typical plate of eba + egusi has ~60% swallow by weight.
                            CATEGORY_DENSITY_WEIGHT = {
                                "swallow": 1.4,
                                "starch": 1.2,
                                "protein_dish": 1.1,
                                "soup": 0.8,
                                "beverage": 0.6,
                            }

                            registry = get_food_registry()
                            weights = []
                            for food in detected_foods:
                                food_info = registry.get_food_info(food.get("name", ""))
                                category = food_info.get("category", "") if food_info else ""
                                weights.append(CATEGORY_DENSITY_WEIGHT.get(category, 1.0))

                            total_weight = sum(weights)
                            depth_estimation_used = True

                            for food, w in zip(detected_foods, weights):
                                share = (w / total_weight) * portion_grams if total_weight > 0 else portion_grams / len(detected_foods)
                                food["estimated_grams"] = min(share, MAX_PER_FOOD)

                            logger.info(
                                f"✅ Fallback (density-weighted): {portion_grams}g total → "
                                + ", ".join(f"{f.get('name')} {f['estimated_grams']:.0f}g" for f in detected_foods)
                            )
                        else:
                            logger.warning("⚠️ Depth estimation MCP returned invalid portion")
                    except Exception as e:
                        logger.error(f"❌ Depth estimation fallback failed: {e}")
                        depth_estimation_used = False
            # Now, build the VisionResult from result_dict and correct depth_estimation_used
            vision_result = self._parse_detection_result(result_dict, depth_estimation_used=depth_estimation_used)
            return vision_result
        except Exception as ex:
            logger.exception(f"VisionAgent.analyze_image failed: {str(ex)}")
            raise

    async def _tool_analyze_nigerian_food_image(
        self,
        image_base64: str,
        user_description: Optional[str] = None,
        meal_type: Optional[str] = None
    ) -> str:
        """
        Tool function for Nigerian food image analysis.

        This is the actual implementation of the analyze_nigerian_food_image tool.
        It wraps the GPT-4o Vision API call and returns structured JSON.

        Args:
            image_base64: Base64 encoded meal image
            user_description: Optional user description
            meal_type: Type of meal

        Returns:
            JSON string with detection results
        """
        logger.info(f"🔧 Tool: analyze_nigerian_food_image (meal_type={meal_type})")

        # Build analysis prompt
        prompt = self._build_detection_prompt(user_description, meal_type)

        return await self._call_gpt4o(prompt, image_base64, user_description)

    async def _call_gpt4o(
        self,
        prompt: str,
        image_base64: str,
        user_description: Optional[str]
    ) -> str:
        """Call GPT-4o Vision as fallback."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Analyze this Nigerian meal image. {user_description or ''}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
            seed=42,
            max_tokens=3000
        )

        usage = response.usage
        logger.info(
            f"Vision Agent (GPT-4o fallback): {usage.total_tokens} tokens "
            f"(~${usage.total_tokens * 2.5 / 1000:.4f})"
        )
        return response.choices[0].message.content

    def _build_detection_prompt(
        self,
        user_description: Optional[str],
        meal_type: Optional[str]
    ) -> str:
        """
        Build detection prompt for GPT-4o Vision.

        Structured in two clear phases:
        - Phase 1 (top): Visual identification guide — what to look for
        - Phase 2 (bottom): Output format — how to structure the JSON

        This ordering ensures GPT-4o reads the identification logic first
        and receives the naming constraint last (relaxed — free naming allowed,
        registry normalization handles mismatches after the fact).

        Args:
            user_description: User's description
            meal_type: Type of meal

        Returns:
            Formatted prompt for Nigerian food detection
        """
        meal_context = f"This is a {meal_type} meal. " if meal_type else ""

        # Get the full categorized food list from registry
        food_list_by_category = self.food_registry.get_vision_agent_food_list()

        return f"""You are an expert Nigerian food recognition AI. Your job is to look at a meal image and identify every food present with accuracy — both the dishes AND everything that was added to them.

**FOOD NAMING RULE — READ THIS FIRST:**
Always write food names as natural, clean English phrases. NEVER use parentheses or brackets.
- Bad: "Chicken (Grilled)" → Good: "Grilled Chicken"
- Bad: "Rice (Fried)" → Good: "Fried Rice"
- Bad: "Egg Sauce (Nigerian Style)" → Good: "Egg Sauce"
- Bad: "Plantain (Ripe, Fried)" → Good: "Fried Ripe Plantain"
- Bad: "Yam (Boiled)" → Good: "Boiled Yam"
Put the cooking method or descriptor directly in the name. If the descriptor is just a cultural origin tag (Nigerian Style, Local, Traditional) — drop it entirely, it adds no useful information.


{meal_context}

---

## PHASE 1 — TWO-LAYER IDENTIFICATION

You must identify foods at TWO layers for every dish on the plate:

**LAYER 1 — The dish itself** (e.g. "Indomie Noodles", "Egusi Soup", "Jollof Rice")
**LAYER 2 — What was ADDED to it** (e.g. carrots + green peas cooked into indomie, extra ugwu leaves in egusi, boiled egg on the side)

This two-layer scan is MANDATORY. You must explicitly check both layers for every food you detect.

---

### STEP 1: Scan the entire image region by region and name every dish you can see.

**First, mentally divide the image into zones — left, right, top, bottom, center, background.**
For each zone, ask: "What dish is here?" Treat each distinct dish as a separate entry.

**Key rules for mixed/scattered plates:**
- If you see rice AND beans separately on the same plate → list them as TWO separate foods
- If you see stew poured OVER rice → list the rice AND the stew separately
- If you see soup beside a swallow → list both separately
- If foods are physically touching but visually distinct → still list them separately
- Only call it a single combined dish (e.g. "Rice and Beans") if they are truly cooked together and inseparable

Use these visual cues to distinguish similar dishes:

**YAM**
- Boiled Yam → white/cream chunks, soft moist texture, NO golden or brown edges
- Fried Yam → golden-brown crispy exterior, oily surface, darker color

**PLANTAIN**
- Fried Plantain (Ripe) → yellow/brown slices, crispy golden edges, oily sheen
- Boiled Plantain (Ripe) → soft yellow/orange chunks, no crispy edges, moist
- Boiled Plantain (Unripe) → pale or greenish soft chunks
- Boli (Roasted Plantain) → charred black spots, smoky appearance, slightly wrinkled

**RICE**
- Jollof Rice → rice coated in red/orange tomato sauce
- Fried Rice → rice with visible mixed vegetables (carrots, peas, green beans) — NOTE: these veggies are STANDARD in fried rice, do NOT list them as added_ingredients
- White Rice (Boiled) → plain white, no sauce or color
- Coconut Rice → slightly brown tint, coconut aroma (may appear slightly glossy)

**SWALLOWS** (served as a smooth ball or mound alongside soup)
- Pounded Yam → white, very smooth, elastic texture
- Fufu (Cassava) → white, slightly softer/stickier than pounded yam
- Eba (Garri) → yellow or cream colored, cassava-based, slightly grainy surface
- Amala → dark brown or grey-black, yam flour based
- Semovita → white, fine semolina texture
- Tuwo Shinkafa → white, rice-based, Northern Nigerian

**EGGS — read carefully, these are commonly confused**
- Egg Sauce (Nigerian Style) → eggs scrambled INTO a tomato-pepper sauce — the egg is broken up and mixed throughout an orange/red sauce. The dish looks like a stew with egg pieces, NOT a standalone egg. There is always visible red/orange sauce.
- Scrambled Eggs → soft, fluffy pale yellow curds with NO tomato sauce, NO red color. Plain eggs cooked and folded. No sauce, no vegetables mixed in.
- Fried Eggs → flat egg with a clearly visible round yolk, cooked in oil. Crispy or set white edges around the yolk. Served flat on a plate or as a topping.
- Sunny Side Up Egg → exactly like fried egg — yolk is facing UP and is runny/bright yellow. White is set but yolk is not broken. Use this name when yolk is intact and visible from above.
- Omelette → eggs beaten and cooked flat as a folded pancake shape. No visible yolk, uniform surface. May be folded in half. Can contain fillings inside.
- Hard Boiled Eggs → whole round egg, peeled or unpeeled. No browning, no sauce, firm and compact shape.

**KEY RULE FOR EGGS:** Only call something "Egg Sauce" if you can see RED/ORANGE TOMATO SAUCE mixed with the egg. If there is no sauce — it is Scrambled Eggs, Fried Eggs, Sunny Side Up, or Omelette instead.

**SOUPS** (usually served with swallow or rice)
- Efo Riro → dark green leafy vegetables, palm oil base, visible meat/fish
- Edikang Ikong Soup → very dark green, two types of leaves (ugwu + waterleaf), rich palm oil
- Egusi Soup → thick orange/brown base, visible ground melon seeds, palm oil
- Ogbono Soup → dark, slimy/draw texture, pulls in strings when stirred
- Okro Soup → green/slimy texture from okro (okra), can be mixed with egusi
- Banga Soup → deep orange, made from palm nuts, very rich and oily
- Bitterleaf Soup (Ofe Onugbu) → greenish, slightly lighter than efo riro, with bitter leaves
- Oha Soup → light green oha leaves, cocoyam thickened, lighter color than egusi
- Afang Soup → dark green with shredded afang (okazi) leaves, palm oil
- Nigerian Tomato Stew → bright red/orange, smooth tomato base, very common sauce
- Pepper Soup (Goat) → clear/light brown watery broth, floating spices, very peppery look

**PROTEINS**
- Akara → round golden-brown bean balls, fried, no coating
- Moi Moi → steamed bean pudding, wrapped in leaves or foil, soft brownish surface
- Suya → thin strips of grilled spiced meat on a stick, dusty spice coating
- Beef (Stewed) → dark brown chunks in sauce/stew
- Goat Meat (Stewed) → similar to beef but often with visible bone
- Fried Fish / Fried Catfish → whole or fillet fish with golden crispy coating
- Grilled Tilapia → whole fish, no coating, visible grill marks or smoky surface
- Fried Chicken → golden crispy BATTERED coating covering the entire surface. Thick, crunchy-looking shell. Looks like KFC-style or battered Nigerian fried chicken.
- Grilled Chicken Breast → boneless flat fillet, no coating at all, slightly charred or browned surface with grill marks. Lean and flat.
- Stewed Chicken (Nigerian) → chicken pieces sitting IN or coated with a red/brown tomato-pepper sauce. Sauce is always visible. Usually bone-in pieces. This is the most common Nigerian party chicken.
- Peppered Chicken → chicken pieces heavily coated in thick blended pepper paste — very dark red/maroon coating, drier than stew sauce. Looks almost blackened with spice. Very common at Nigerian parties.
- Chicken Wings (Roasted) → small wing-shaped pieces, roasted golden-brown, no thick batter coating, clearly wing shape (drumette + flat). May have light seasoning crust.

**KEY RULE FOR CHICKEN:** Do NOT default to "Grilled Chicken Breast" unless you see a clearly boneless flat fillet with grill marks. If there is any sauce, coating, or the chicken is in pieces with bone — use the correct type above.
- Brown Beans (Boiled) → dark brown or black-eyed beans in a bowl, soft
- Ponmo (Cow Skin) → flat dark pieces of chewy cow hide
- Smoked Fish → dark, dried, smoky-looking fish pieces
- Stock Fish → very dry, pale/yellowish dried fish, strong smell implied by appearance
- Sardines (Canned) → small silvery flat fish pieces packed tightly, often in oil or sauce in a tin/plate
- Sausages (Cooked) → cylindrical brown/reddish meat links, smooth casing, cooked through. May be whole or sliced into rounds
- Turkey (Peppered) → similar to peppered chicken but turkey pieces are larger, white meat visible. Usually at parties alongside chicken
- Nkwobi → chunks of cow foot/leg in a thick yellowish-orange palm oil paste with visible utazi leaf garnish. Served in a wooden or clay bowl

**SOUPS (LIGHT / DRAW)**
- Ewedu Soup → very thin, slimy/draw green soup with strands that pull when stirred. Pale green color, served in small bowl alongside stew
- Fish Pepper Soup (Catfish) → clear, light brown watery broth with chunks of catfish, floating pepper soup leaves and spices. No oil sheen

**PASTA & NOODLES**
- Jollof Spaghetti → long spaghetti strands coated in red/orange tomato sauce — same red color as jollof rice but with pasta strands visible
- Indomie Noodles (Cooked) → thin yellow wavy noodles, usually with orange sauce. Shorter and curlier than spaghetti

**SALADS & SPECIALS**
- Abacha (African Salad) → pale/white shredded cassava strips mixed with dark ugba seeds, palm oil giving an orange tint, visible utazi leaves and fresh vegetables on top

**SIDES (GLOBAL)**
- Boiled Potatoes → soft white/cream chunks or whole small potatoes, no browning, no oil, no crispy edges. Plain and moist

**SNACKS & SIDES**
- Puff Puff → round golden dough balls, slightly irregular shape
- Chin Chin → small crunchy fried dough pieces, golden-brown
- Meat Pie → golden pastry crust, half-moon or rectangular shape
- Egg Roll → oval golden fried pastry with a boiled egg inside
- Masa → small round or flat Northern rice cakes, slightly crispy outside
- Akara → round golden bean fritters

---

### STEP 2: For each dish, run the TWO-LAYER ingredient scan.

**LAYER 1 — Standard ingredients (built into the dish's standard recipe):**
These are already factored into the dish's nutrition. List them in `standard_ingredients` for context only.
Examples: tomatoes/peppers in jollof rice base, palm oil in egusi soup, crayfish in most soups, carrots/peas in fried rice.

**LAYER 2 — Added ingredients (NOT part of the standard recipe — visibly added):**
These are EXTRA ingredients the cook added that change the nutrition. List them in `added_ingredients`.
You MUST scan carefully for these visual cues:

| What you see | Added ingredient name |
|---|---|
| Orange chunks or strips mixed in | "carrots" |
| Small round green balls | "green peas" or "peas" |
| White shredded strips | "cabbage" |
| Dark green leafy pieces (in non-leafy dish) | "ugwu" or "spinach" |
| Light green wilted leaves | "waterleaf" |
| Slightly bitter darker green leaves | "bitter leaf" |
| Long thin green strips | "green beans" |
| Colourful strips (red/yellow/green) | "bell pepper" |
| Red/orange chunks beyond the base sauce | "tomatoes" |
| Round item with visible yolk beside main dish | "boiled egg" or "fried egg" |
| Green circular slices | "cucumber" |
| Pale green layers | "lettuce" |
| White translucent pieces mixed in | "onions" |
| Small pink/orange curved pieces | "shrimp" or "prawns" |
| Bright yellow kernels (round, in clusters) | "sweet corn" |
| Thin green rings or sliced green tops | "spring onions" |
| Brown cylindrical sliced rounds | "sausage" |
| Dark green tree-shaped florets | "broccoli" |

**IMPORTANT distinction:**
- Indomie with carrots and peas cooked in → carrots and peas are ADDED (they are not standard indomie)
- Fried rice with carrots and peas → these are STANDARD (part of fried rice recipe) — do NOT add them
- Egusi soup with extra ugwu stirred in → ugwu is ADDED
- Efo Riro → ugwu IS the dish, not added

After scanning, populate `added_ingredients` with everything you found in Layer 2.
Also copy `added_ingredients` into `visible_ingredients` (for backward compatibility).

**Oil indicators (for soups, stews, porridges, rice dishes):**
- Orange or red sheen → palm oil present
- Clear or yellow sheen → vegetable oil present
- Glossy pooling on surface → heavy oil
- Slight sheen → moderate oil
- Matte/dull surface → light or no oil
- Rate as: "none" / "light" / "moderate" / "heavy"

---

### STEP 3: Match each dish to the reference list below if possible.

If you can find a match → use that exact name.
If there is NO good match → use your own clear descriptive name. Do NOT force a wrong match just to use a list name. The system will handle normalization automatically.

**Reference Food List:**
{food_list_by_category}

---

## PHASE 2 — FORMAT YOUR OUTPUT

### STEP 4: Return ONLY valid JSON (no markdown, no explanation).

**Counting rule — apply BEFORE filling in the JSON:**

For **countable/discrete foods** (individual items you can count one by one):
- Bread slices, eggs, pieces of chicken or fish, akara balls, puff puff, chin chin, meat pies, moi moi wraps, suya sticks, corn cobs
- Count the exact number of visible items → set `"item_count"` to that number
- Set `"estimated_grams"` = item_count × typical weight per item (e.g. 2 bread slices = 2 × 30g = 60g, 3 eggs = 3 × 50g = 150g)

For **volume/scoopable foods** (rice, soup, porridge, eba, stew, beans — you scoop them, not count them):
- Set `"item_count": null`
- Set `"estimated_grams"` based on visual volume

{{
  "detected_foods": [
    {{
      "name": "dish name — from reference list if matched, or your own descriptive name",
      "nigerian_name": "local Nigerian name if known, else null",
      "confidence": 0.0-1.0,
      "estimated_portion": "descriptive size (e.g. '1 plate', 'medium bowl', '2 pieces')",
      "estimated_grams": number,
      "item_count": number or null,
      "standard_ingredients": ["ingredient1", "ingredient2"],
      "added_ingredients": ["only ingredients visibly ADDED beyond the standard recipe"],
      "visible_ingredients": ["copy of added_ingredients — for backward compatibility"],
      "cooking_method": "boiled / fried / grilled / stewed / steamed / roasted",
      "oil_sheen_visible": true or false,
      "oil_amount_estimate": "none / light / moderate / heavy"
    }}
  ],
  "meal_context": "A detailed description of everything visible in the image — every dish present, how many pieces or items of each, cooking methods observed, visible garnishes or additions, oil level, and how the foods are arranged on the plate. This description will be used by an AI health assistant to answer specific questions about this meal later (e.g. 'how many fish were on the plate', 'was the food heavily oiled', 'what exactly did I eat'). Be specific and visual.",
  "cooking_method": "primary cooking method observed across the meal",
  "overall_confidence": 0.0-1.0,
  "needs_clarification": true or false,
  "clarification_questions": ["question if needed, else empty list"]
}}

**Confidence scale:**
- 0.9–1.0: Very certain (clear view, recognizable dish)
- 0.7–0.9: Confident (good visibility)
- 0.5–0.7: Moderate (some uncertainty or partial view)
- 0.3–0.5: Low (unclear, could be multiple dishes)
- <0.3: Very uncertain → set needs_clarification to true

**Typical Nigerian portion sizes (use for estimated_grams):**
- 1 plate of rice (jollof/fried/coconut) → 350–400g
- 1 wrap of swallow (eba/pounded yam/fufu) → 300–400g
- 1 piece of meat (beef/goat) → 80–150g
- 1 bowl of soup (with swallow) → 250–350g
- Side dishes (plantain, salad) → 80–150g
- 1 egg → 50g
- 1 plate of porridge (yam/beans/plantain) → 300–350g"""

    def _parse_detection_result(self, result_dict: Dict[str, Any], depth_estimation_used: bool = False) -> VisionResult:
        """
        Parse JSON result into VisionResult model.

        Validates and normalizes food names to match the knowledge base exactly.

        Args:
            result_dict: Parsed JSON from GPT-4o
            depth_estimation_used: Boolean indicating if depth estimation was used for portion estimation

        Returns:
            Structured VisionResult
        """
        detected_foods = []

        for food_data in result_dict.get("detected_foods", []):
            # Get the raw name from Vision
            raw_name = food_data.get("name", "Unknown Food")

            # Normalize to canonical name from the registry
            # This ensures the name matches exactly what's in the knowledge base
            canonical_name = get_canonical_food_name(raw_name)

            if canonical_name != raw_name:
                logger.info(f"📝 Normalized food name: '{raw_name}' → '{canonical_name}'")

            # Warn if the food is not in our database
            if not self.food_registry.is_known_food(raw_name):
                logger.warning(f"⚠️ Unknown food detected: '{raw_name}' (not in knowledge base)")

            detected_food = DetectedFood(
                name=canonical_name,  # Use normalized name
                nigerian_name=food_data.get("nigerian_name"),
                confidence=food_data.get("confidence", 0.5),
                estimated_portion=food_data.get("estimated_portion", "Unknown"),
                estimated_grams=food_data.get("estimated_grams", 0.0),
                item_count=food_data.get("item_count"),
                visible_ingredients=food_data.get("visible_ingredients", []),
                cooking_method=food_data.get("cooking_method"),
                oil_sheen_visible=food_data.get("oil_sheen_visible"),
                oil_amount_estimate=food_data.get("oil_amount_estimate")
            )
            detected_foods.append(detected_food)

        return VisionResult(
            detected_foods=detected_foods,
            meal_context=result_dict.get("meal_context", "Nigerian meal"),
            cooking_method=result_dict.get("cooking_method"),
            overall_confidence=result_dict.get("overall_confidence", 0.7),
            needs_clarification=result_dict.get("needs_clarification", False),
            clarification_questions=result_dict.get("clarification_questions", []),
            depth_estimation_used=depth_estimation_used
        )

    def validate_image_quality(self, image_base64: str) -> Dict[str, Any]:
        """
        Quick validation of image quality for food detection.

        Args:
            image_base64: Base64 encoded image

        Returns:
            Validation results
        """
        try:
            # Decode to check basic properties
            image_data = base64.b64decode(image_base64)

            return {
                "is_valid": True,
                "size_bytes": len(image_data),
                "message": "Image is suitable for analysis"
            }
        except Exception as e:
            logger.error(f"Image validation failed: {e}")
            return {
                "is_valid": False,
                "message": f"Invalid image format: {str(e)}"
            }


# ============================================================================
# Convenience Functions
# ============================================================================

def detect_nigerian_foods(
    image_base64: str,
    user_description: Optional[str] = None,
    meal_type: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> VisionResult:
    """
    Convenience function for single-image food detection.

    Args:
        image_base64: Base64 encoded meal image
        user_description: Optional description from user
        meal_type: Type of meal
        openai_api_key: Optional API key override

    Returns:
        VisionResult with detected foods
    """
    import asyncio
    agent = VisionAgent(openai_api_key=openai_api_key)
    return asyncio.run(agent.analyze_image(image_base64, user_description, meal_type))


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_vision_agent():
        """Test Vision Agent with sample scenarios."""

        print("\n" + "="*60)
        print("Testing Vision Agent - Nigerian Food Detection")
        print("="*60 + "\n")

        agent = VisionAgent()

        # Note: Actual testing requires real images
        print("Vision Agent initialized successfully!")
        print(f"Model: {agent.model}")
        print(f"Known foods: {len(agent.known_foods)} Nigerian dishes")

        print("\n" + "="*60)
        print("Vision Agent Ready for Food Detection!")
        print("="*60 + "\n")

    asyncio.run(test_vision_agent())
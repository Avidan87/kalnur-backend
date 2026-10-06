"""
Standardized Nigerian Food Vision Prompt & Detection Schema

Shared between Anthropic Claude Sonnet 4.6 (AWS Bedrock) and OpenAI GPT-4o
to ensure strict, scientifically valid apples-to-apples benchmarking.

Focuses heavily on:
1. Nigerian dish identification (134+ catalog)
2. Vertical occlusion & submerged food detection (swallow/meats under soup)
3. Container depth reasoning (flat plate vs deep bowl)
4. Oil sheen & texture estimation
5. Gram portion estimation
"""

from typing import Optional, Dict, Any

def build_standardized_food_vision_prompt(
    meal_type: Optional[str] = "lunch",
    user_description: Optional[str] = None,
) -> str:
    meal_context = f"Meal type: {meal_type}. " if meal_type else ""
    user_ctx = f"User note: {user_description}. " if user_description else ""

    return f"""You are an expert Nigerian food recognition and spatial computer vision engine.
Your task is to analyze this meal image with exceptional spatial sensitivity and identify every food item present, including foods partially or completely submerged under soups or sauces.

{meal_context}{user_ctx}

### CRITICAL VISION CHALLENGES TO SOLVE:

1. **VERTICAL LAYERING & SUBMERGED FOODS (OCCLUSION REASONING):**
   - In Nigerian meals, swallows (Pounded Yam, Eba, Amala, Fufu, Semovita) or meats (beef, goat meat, shaki/tripe, ponmo, catfish, dried fish) are frequently submerged underneath thick soups (Egusi, Ogbono, Banga, Efo Riro, Okro, Bitterleaf).
   - DO NOT only report what is floating on the surface. Look for:
     - Distinct mounds, surface displacement, or bulges under soup layers.
     - Visible submerged edges or protrusions (e.g. bone, skin texture, meat fiber, rounded swallow contour).
     - Viscosity changes indicating buried solid mass.
   - For every detected food, indicate whether it is:
     - "surface" (fully visible on top)
     - "partially_submerged" (partially beneath soup/sauce)
     - "fully_submerged" (inferred via bulge, contour, or meal context)

2. **CONTAINER & VESSEL DEPTH:**
   - Detect the vessel type: "flat_plate", "shallow_bowl", "deep_soup_bowl", "takeaway_container", or "calabash".
   - Top-down 2D photos frequently hide depth. Estimate the vessel depth in cm (e.g., flat plate = 1.5-2.5cm; deep soup bowl = 5.0-8.0cm).
   - Account for container depth when calculating portion volume and grams!

3. **TEXTURE & OIL SHEEN:**
   - Detect oil layer presence:
     - Palm oil (distinct red/orange sheen and glossy surface) vs Vegetable oil (golden/clear sheen).
     - Rate oil level: "none", "light", "moderate", "heavy".
   - Note texture nuances: melon seed granules (Egusi), draw/mucilage strands (Ogbono/Ewedu), vegetable leaves (Ugwu/Waterleaf).

4. **UNCONSTRAINED NIGERIAN CULINARY IDENTIFICATION:**
   - Use your comprehensive knowledge of authentic Nigerian cuisine across all cultures (Igbo, Yoruba, Hausa/Fulani, Edo, Efik/Ibibio, Urhobo, etc.).
   - Freely identify any authentic dish by its true traditional, regional, or common name (e.g. "Bitterleaf Soup / Ofe Onugbu", "Ofe Oha", "Ofe Nsala", "Afang Soup", "Edikang Ikong", "Banga Soup", "Efo Riro", "Miyan Kuka", "Tuwo Shinkafa", etc.).
   - NEVER force-fit a dish into a generic category if you recognize the specific soup, stew, protein, or swallow. State the exact dish you observe.
   - Clean naming: Use natural names without brackets, unnecessary punctuation, or filler origin tags.

5. **DENSE, HIGH-SIGNAL REASONING (SPEED & MAXIMUM CONCISENESS):**
   - Express all reasoning with **dense, telegraphic, factual observations**.
   - NEVER use conversational filler ("This is a classic presentation...", "served neatly for a satisfying lunch...").
   - Retain 100% of the physical evidence: bone protrusions, bulges, fiber texture, estimated cm dimensions, and liquid depth in short, punchy phrases.

---

### OUTPUT FORMAT REQUIREMENTS:
Return ONLY a valid JSON object with NO markdown backticks matching this exact schema:

{{
  "vessel": {{
    "type": "flat_plate" | "shallow_bowl" | "deep_soup_bowl" | "takeaway_container" | "other",
    "estimated_depth_cm": float,
    "confidence": float
  }},
  "detected_foods": [
    {{
      "name": "Clean canonical dish name (e.g. Egusi Soup, Pounded Yam, Stewed Beef)",
      "nigerian_name": "Traditional name if applicable (e.g. Iyan, Amala) or null",
      "confidence": float (0.0 to 1.0),
      "estimated_portion": "Short portion (e.g. '1 bowl ~300g', '2 pieces ~160g')",
      "estimated_grams": float,
      "item_count": int or null,
      "occlusion_state": "surface" | "partially_submerged" | "fully_submerged",
      "submerged_reasoning": "Dense physical evidence (e.g. 'Protruding fibrous grain & bone; lower 60% hidden under egusi')",
      "visible_ingredients": ["ugwu leaves", "crayfish", "palm oil"],
      "cooking_method": "boiled" | "fried" | "grilled" | "stewed" | "steamed" | "roasted",
      "oil_sheen_visible": bool,
      "oil_amount_estimate": "none" | "light" | "moderate" | "heavy"
    }}
  ],
  "meal_context": "Dense 1-2 sentence visual summary of dishes, arrangement, and oil level.",
  "spatial_depth_reasoning": "Telegraphic bullet notes on vessel depth (cm) and submerged volume deduction.",
  "overall_confidence": float (0.0 to 1.0)
}}
"""

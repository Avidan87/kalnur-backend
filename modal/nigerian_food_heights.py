"""
Nigerian Food Height Database
Measured typical heights for Nigerian foods to improve volume estimation accuracy

Heights are based on:
- Traditional serving styles
- Typical portion presentations
- Nigerian culinary practices
"""

from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


# Food height database (in centimeters)
# Format: food_name -> (min_height_cm, typical_height_cm, max_height_cm, shape_type)

NIGERIAN_FOOD_HEIGHTS: Dict[str, Tuple[float, float, float, str]] = {
    # STAPLES - Swallows (Mounded shapes)
    "fufu": (6.0, 9.0, 12.0, "mound"),
    "pounded_yam": (6.0, 10.0, 14.0, "mound"),
    "eba": (4.0, 7.0, 10.0, "mound"),
    "garri": (4.0, 7.0, 10.0, "mound"),
    "amala": (5.0, 8.0, 11.0, "mound"),
    "semovita": (4.0, 7.0, 10.0, "mound"),
    "tuwo_shinkafa": (5.0, 8.0, 11.0, "mound"),
    "tuwo_masara": (5.0, 8.0, 11.0, "mound"),

    # RICE DISHES (Mounded or layered)
    "jollof_rice": (3.0, 5.0, 7.0, "mound"),
    "fried_rice": (3.0, 5.0, 7.0, "mound"),
    "white_rice": (3.0, 5.0, 7.0, "mound"),
    "coconut_rice": (3.0, 5.0, 7.0, "mound"),
    "ofada_rice": (3.0, 5.0, 7.0, "mound"),
    "rice_and_stew": (3.0, 5.0, 7.0, "layered"),

    # SOUPS (Bowl-contained, liquid)
    "egusi_soup": (2.0, 4.0, 6.0, "bowl"),
    "okra_soup": (2.0, 4.0, 6.0, "bowl"),
    "ogbono_soup": (2.0, 4.0, 6.0, "bowl"),
    "efo_riro": (2.0, 4.0, 6.0, "bowl"),
    "afang_soup": (2.5, 4.5, 6.5, "bowl"),
    "edikang_ikong": (2.5, 4.5, 6.5, "bowl"),
    "banga_soup": (2.0, 4.0, 6.0, "bowl"),
    "oha_soup": (2.0, 4.0, 6.0, "bowl"),
    "pepper_soup": (3.0, 5.0, 7.0, "bowl"),
    "bitterleaf_soup": (2.0, 4.0, 6.0, "bowl"),
    "white_soup": (2.0, 4.0, 6.0, "bowl"),
    "ewedu_soup": (1.5, 3.0, 4.5, "bowl"),
    "gbegiri_soup": (1.5, 3.0, 4.5, "bowl"),

    # STEWS (Thicker, bowl or layered)
    "chicken_stew": (2.0, 4.0, 6.0, "bowl"),
    "fish_stew": (2.0, 4.0, 6.0, "bowl"),
    "beef_stew": (2.0, 4.0, 6.0, "bowl"),
    "ayamase": (2.0, 4.0, 6.0, "bowl"),

    # BEANS DISHES
    "beans_porridge": (3.0, 5.0, 7.0, "bowl"),
    "moi_moi": (4.0, 6.0, 8.0, "mound"),
    "akara": (1.5, 2.5, 3.5, "flat_stack"),
    "ewa_agoyin": (2.0, 4.0, 6.0, "bowl"),

    # YAM DISHES
    "yam_porridge": (3.0, 5.0, 7.0, "bowl"),
    "boiled_yam": (2.0, 4.0, 6.0, "pieces"),
    "fried_yam": (2.0, 4.0, 6.0, "flat_stack"),
    "dundun": (2.0, 4.0, 6.0, "flat_stack"),

    # PLANTAIN DISHES (Flat pieces)
    "fried_plantain": (1.0, 2.0, 3.0, "flat_stack"),
    "dodo": (1.0, 2.0, 3.0, "flat_stack"),
    "boli": (3.0, 5.0, 7.0, "pieces"),

    # PROTEINS (Individual pieces)
    "grilled_chicken": (3.0, 5.0, 8.0, "pieces"),
    "fried_chicken": (3.0, 5.0, 8.0, "pieces"),
    "grilled_fish": (2.0, 4.0, 6.0, "flat_piece"),
    "fried_fish": (2.0, 4.0, 6.0, "flat_piece"),
    "suya": (1.0, 2.0, 3.0, "flat_stack"),
    "ponmo": (0.5, 1.0, 2.0, "flat_stack"),
    "nkwobi": (2.0, 4.0, 6.0, "bowl"),

    # SNACKS
    "puff_puff": (3.0, 4.0, 5.0, "pieces"),
    "chin_chin": (2.0, 3.0, 4.0, "heap"),
    "meat_pie": (3.0, 4.0, 5.0, "pieces"),
    "sausage_roll": (2.0, 3.0, 4.0, "pieces"),

    # OTHERS
    "gizdodo": (2.0, 4.0, 6.0, "mixed"),
    "abacha": (2.0, 3.0, 4.0, "flat"),
    "okpa": (2.0, 3.0, 4.0, "pieces"),
    "masa": (1.0, 2.0, 3.0, "flat_stack"),

    # PASTA
    "spaghetti": (2.0, 4.0, 6.0, "mound"),
    "indomie": (2.0, 4.0, 6.0, "mound"),

    # PROTEIN
    "grilled_tilapia": (1.5, 3.5, 5.0, "flat_piece"),
    "brown_beans_boiled": (2.5, 4.5, 6.5, "bowl"),
    "hard_boiled_eggs": (3.5, 4.5, 5.5, "sphere"),
    "goat_meat_stewed": (2.0, 4.0, 6.0, "pieces"),
    "fried_eggs": (1.0, 1.5, 2.5, "flat"),
    "kilishi": (0.3, 0.6, 1.2, "flat_stack"),
    "fried_catfish": (2.0, 3.5, 5.0, "flat_piece"),
    "smoked_fish_panla": (1.5, 2.5, 4.0, "flat_piece"),
    "stock_fish": (1.0, 2.0, 3.5, "flat_piece"),
    "snail_cooked": (1.5, 3.0, 4.5, "pieces"),

    # PROTEIN DISH
    "egg_sauce_nigerian": (1.5, 3.0, 4.5, "bowl"),
    "peppered_ponmo": (1.5, 3.0, 4.5, "bowl"),
    "bread_and_egg": (2.5, 4.0, 5.5, "layered"),

    # VEGETABLES
    "fresh_tomatoes": (3.0, 5.0, 7.0, "sphere"),
    "bell_peppers": (6.0, 8.0, 10.0, "sphere"),
    "raw_onions": (1.0, 3.0, 5.0, "flat_stack"),
    "spinach_raw": (3.0, 6.0, 10.0, "heap"),
    "cucumber": (1.5, 3.0, 5.0, "flat_stack"),
    "ugwu_leaves": (3.0, 6.0, 10.0, "heap"),
    "coleslaw_nigerian": (2.0, 3.5, 5.0, "mound"),
    "carrots_raw": (1.5, 3.0, 5.0, "pieces"),
    "cabbage_raw": (2.0, 4.0, 7.0, "heap"),
    "garden_egg": (3.0, 5.0, 7.0, "sphere"),
    "green_beans_raw": (2.0, 4.0, 6.0, "heap"),
    "lettuce_raw": (4.0, 7.0, 12.0, "heap"),
    "red_bell_pepper_sliced": (1.0, 2.5, 4.0, "flat_stack"),

    # FRUIT
    "watermelon_fresh": (3.0, 5.0, 8.0, "flat_piece"),
    "pineapple_fresh": (2.0, 4.0, 6.0, "flat_piece"),
    "banana_fresh": (2.5, 3.5, 4.5, "cylinder"),
    "pawpaw_fresh": (3.0, 5.0, 7.0, "flat_piece"),
    "orange_fresh": (6.0, 7.5, 9.0, "sphere"),
    "mango_fresh": (6.0, 8.0, 10.0, "sphere"),
    "apple_fresh": (6.0, 7.5, 9.0, "sphere"),
    "agbalumo": (3.0, 4.0, 5.5, "sphere"),
    "avocado_pear": (4.0, 6.0, 8.0, "sphere"),
    "african_pear_ube": (3.0, 4.5, 6.0, "sphere"),
    "coconut_fresh": (1.5, 3.0, 4.5, "flat_stack"),
    "grapes_fresh": (3.0, 5.0, 7.0, "heap"),

    # STARCH
    "boiled_yam": (2.0, 4.0, 6.0, "pieces"),
    "boiled_plantain_unripe": (2.0, 3.5, 5.0, "pieces"),
    "boiled_plantain_ripe": (2.0, 3.5, 5.0, "pieces"),
    "fried_yam": (2.0, 4.0, 6.0, "flat_stack"),
    "white_bread": (1.0, 1.5, 2.0, "flat_piece"),
    "agege_bread": (2.5, 3.5, 4.5, "flat_piece"),
    "whole_wheat_bread": (1.0, 1.5, 2.0, "flat_piece"),
    "yam_porridge_asaro": (3.0, 5.0, 7.0, "bowl"),
    "potato_porridge": (3.0, 5.0, 7.0, "bowl"),
    "plantain_porridge": (3.0, 5.0, 7.0, "bowl"),
    "rice_and_beans": (3.0, 5.0, 7.0, "mound"),
    "coconut_rice": (3.0, 5.0, 7.0, "mound"),
    "indomie_noodles": (3.0, 5.0, 7.0, "mound"),

    # SWALLOW
    "semovita": (4.0, 7.0, 10.0, "mound"),
    "tuwo_shinkafa": (5.0, 8.0, 11.0, "mound"),

    # SOUPS
    "okro_soup": (2.0, 4.0, 6.0, "bowl"),
    "tomato_stew_nigerian": (1.5, 3.0, 5.0, "bowl"),
    "bitterleaf_soup": (2.0, 4.0, 6.0, "bowl"),
    "ayamase_ofada_stew": (2.0, 4.0, 6.0, "bowl"),

    # SNACKS
    "groundnut_roasted": (1.5, 3.0, 5.0, "heap"),
    "nigerian_egg_roll": (4.0, 5.5, 7.0, "sphere"),
    "boiled_corn_ube": (5.0, 7.0, 9.0, "cylinder"),
    "roasted_corn_agbado": (5.0, 7.0, 9.0, "cylinder"),
    "almonds_raw": (1.5, 3.0, 5.0, "heap"),
    "granola": (2.0, 4.0, 6.0, "heap"),
    "nigerian_shawarma": (5.0, 7.0, 9.0, "cylinder"),
    "plantain_chips": (1.5, 3.0, 4.5, "heap"),
    "soaked_garri_with_groundnut": (3.0, 5.0, 7.0, "bowl"),

    # BEVERAGES
    "zobo": (6.0, 9.0, 12.0, "liquid"),
    "kunu": (6.0, 9.0, 12.0, "liquid"),
    "pap_ogi_akamu": (4.0, 6.0, 8.0, "bowl"),
    "custard_nigerian_style": (4.0, 6.0, 8.0, "bowl"),
    "fresh_orange_juice": (6.0, 9.0, 12.0, "liquid"),
    "coconut_water": (6.0, 9.0, 12.0, "liquid"),
    "malt_drink": (6.0, 9.0, 12.0, "liquid"),
    "soy_milk": (6.0, 9.0, 12.0, "liquid"),
    "ginger_drink": (6.0, 9.0, 12.0, "liquid"),
    "chapman": (6.0, 9.0, 12.0, "liquid"),
    "palm_oil": (0.5, 1.5, 3.0, "liquid"),

    # BREAKFAST / NEW FOODS
    "pancakes": (2.0, 4.0, 6.0, "flat_stack"),
    "cake_plain": (3.0, 5.0, 7.0, "flat_piece"),
    "potato_salad": (3.0, 5.0, 7.0, "bowl"),

    # AUTO-SCAFFOLDED — review and adjust values
    "stewed_chicken_nigerian": (2.4, 4.0, 6.4, "flat_piece"),  # auto-scaffolded
    "peppered_chicken": (2.7, 4.5, 7.2, "flat_piece"),  # auto-scaffolded
    "chicken_wings_roasted": (2.4, 4.0, 6.4, "flat_piece"),  # auto-scaffolded
    "scrambled_eggs": (1.2, 2.0, 3.2, "flat_piece"),  # auto-scaffolded
    "omelette": (1.2, 2.0, 3.2, "flat_piece"),  # auto-scaffolded
    "sunny_side_up_egg": (0.9, 1.5, 2.4, "flat_piece"),  # auto-scaffolded

    # AUTO-SCAFFOLDED — review and adjust values
    "sausages_cooked": (1.8, 3.0, 4.8, "flat_piece"),  # auto-scaffolded
    "sardines_canned": (1.2, 2.0, 3.2, "flat_piece"),  # auto-scaffolded
    "boiled_potatoes": (2.1, 3.5, 5.6, "mound"),  # auto-scaffolded
    "turkey_peppered": (2.7, 4.5, 7.2, "flat_piece"),  # auto-scaffolded

    # AUTO-SCAFFOLDED — review and adjust values
    "sweet_corn_cooked": (1.2, 2.0, 3.2, "heap"),  # auto-scaffolded
    "spring_onions": (0.6, 1.0, 1.6, "heap"),  # auto-scaffolded
    "shrimp_cooked": (1.5, 2.5, 4.0, "flat_piece"),  # auto-scaffolded
    "broccoli_cooked": (3.0, 5.0, 8.0, "heap"),  # auto-scaffolded
}


# Shape-based default heights (fallback)
SHAPE_DEFAULT_HEIGHTS: Dict[str, Tuple[float, float, float]] = {
    "mound": (4.0, 7.0, 10.0),        # Swallows, rice dishes
    "bowl": (2.0, 4.0, 6.0),          # Soups, stews
    "flat_stack": (1.0, 2.5, 4.0),    # Fried plantain, yam
    "pieces": (2.0, 4.0, 6.0),        # Chicken, fish pieces
    "flat_piece": (1.0, 2.0, 3.0),    # Single flat item
    "layered": (3.0, 5.0, 7.0),       # Rice with stew
    "heap": (2.0, 3.0, 4.0),          # Small snacks piled
    "mixed": (2.0, 4.0, 6.0),         # Mixed items
    "flat": (1.0, 2.0, 3.0),          # Flat dishes
}


def get_food_height(
    food_name: str,
    portion_size: str = "typical"
) -> Tuple[float, str]:
    """
    Get estimated height for a Nigerian food

    Args:
        food_name: Name of food (normalized to lowercase)
        portion_size: "small", "typical", or "large"

    Returns:
        Tuple of (height_cm, shape_type)
    """
    food_key = food_name.lower().replace(" ", "_")

    # Try exact match first
    if food_key in NIGERIAN_FOOD_HEIGHTS:
        min_h, typical_h, max_h, shape = NIGERIAN_FOOD_HEIGHTS[food_key]

        if portion_size == "small":
            height = min_h
        elif portion_size == "large":
            height = max_h
        else:  # typical
            height = typical_h

        logger.info(f"Food height for '{food_name}': {height}cm ({shape})")
        return (height, shape)

    # Try partial match (e.g., "jollof" in food_name)
    for key, (min_h, typical_h, max_h, shape) in NIGERIAN_FOOD_HEIGHTS.items():
        if key in food_key or food_key in key:
            if portion_size == "small":
                height = min_h
            elif portion_size == "large":
                height = max_h
            else:
                height = typical_h

            logger.info(f"Food height for '{food_name}' (partial match '{key}'): {height}cm ({shape})")
            return (height, shape)

    # Fallback: Use generic mound shape (most common)
    logger.warning(f"Unknown food '{food_name}', using default mound height")
    min_h, typical_h, max_h = SHAPE_DEFAULT_HEIGHTS["mound"]

    if portion_size == "small":
        height = min_h
    elif portion_size == "large":
        height = max_h
    else:
        height = typical_h

    return (height, "mound")


def get_height_for_shape(shape_type: str) -> float:
    """
    Get typical height for a shape type

    Args:
        shape_type: Shape type (e.g., "mound", "bowl", "flat_stack")

    Returns:
        Typical height in cm
    """
    if shape_type in SHAPE_DEFAULT_HEIGHTS:
        _, typical, _ = SHAPE_DEFAULT_HEIGHTS[shape_type]
        return typical

    # Default fallback
    return 5.0


def estimate_portion_size_category(
    volume_ml: float,
    food_name: str
) -> str:
    """
    Estimate if portion is small/typical/large based on volume

    Args:
        volume_ml: Estimated volume in ml
        food_name: Name of the food

    Returns:
        "small", "typical", or "large"
    """
    food_key = food_name.lower().replace(" ", "_")

    # Get food's typical height to infer volume category
    _, typical_height, _, shape = NIGERIAN_FOOD_HEIGHTS.get(
        food_key,
        (4.0, 7.0, 10.0, "mound")
    )

    # Rough volume thresholds (very approximate)
    # Based on typical Nigerian portions
    if shape == "mound" or shape == "bowl":
        # Swallows and soups
        if volume_ml < 200:
            return "small"
        elif volume_ml > 400:
            return "large"
        else:
            return "typical"
    else:
        # Other foods
        if volume_ml < 150:
            return "small"
        elif volume_ml > 350:
            return "large"
        else:
            return "typical"


# Convenience function
def get_food_height_cm(food_name: str, portion_size: str = "typical") -> float:
    """
    Get food height in cm (returns only the height value)

    Args:
        food_name: Name of the food
        portion_size: "small", "typical", or "large"

    Returns:
        Height in centimeters
    """
    height, _ = get_food_height(food_name, portion_size)
    return height

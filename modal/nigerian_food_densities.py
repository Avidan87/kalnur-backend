"""
Nigerian Food Density Database
Density values (g/ml) for common Nigerian foods to convert volume to weight
"""

NIGERIAN_FOOD_DENSITIES = {
    # Rice dishes
    "jollof-rice": 0.85,
    "fried-rice": 0.80,
    "white-rice": 0.90,
    "ofada-rice": 0.88,
    
    # Starchy sides
    "pounded-yam": 1.10,
    "fufu": 1.05,
    "eba": 1.08,
    "amala": 1.06,
    
    # Soups (liquid-based)
    "egusi-soup": 0.95,
    "efo-riro": 0.92,
    "okra-soup": 0.90,
    "ogbono-soup": 0.93,
    "afang-soup": 0.94,
    "edikang-ikong": 0.95,
    "banga-soup": 0.96,
    "oha-soup": 0.93,
    "pepper-soup": 0.88,
    
    # Beans dishes
    "moi-moi": 1.00,
    "akara": 0.75,
    "ewa-agoyin": 0.95,
    "beans-porridge": 0.92,
    
    # Meat/Protein
    "suya": 0.85,
    "chicken-stew": 0.90,
    "fish-stew": 0.88,
    "nkwobi": 0.95,
    
    # Snacks
    "plantain-fried": 0.70,
    "boli": 0.65,
    "puff-puff": 0.60,
    "chin-chin": 0.55,
    
    # Porridges
    "yam-porridge": 0.88,
    "pap": 0.85,
    "oats": 0.80,
    
    # Default fallback
    "default": 0.90,

    # PROTEIN
    "grilled-tilapia": 1.05,
    "brown-beans-boiled": 0.92,
    "hard-boiled-eggs": 1.03,
    "goat-meat-stewed": 1.00,
    "fried-eggs": 1.00,
    "kilishi": 0.75,
    "fried-catfish": 1.02,
    "smoked-fish-panla": 0.60,
    "stock-fish": 0.55,
    "snail-cooked": 1.05,
    "grilled-chicken-breast": 1.05,
    "fried-chicken": 0.95,
    "beef-stewed": 1.05,
    "fried-fish": 0.95,

    # PROTEIN DISH
    "egg-sauce-nigerian": 0.95,
    "peppered-ponmo": 1.02,
    "bread-and-egg": 0.55,
    "ponmo": 1.02,
    "beans-porridge-ewa-riro": 0.92,
    "ewa-agoyin": 0.95,

    # VEGETABLES
    "fresh-tomatoes": 0.94,
    "bell-peppers": 0.85,
    "raw-onions": 0.88,
    "spinach-raw": 0.10,
    "cucumber": 0.96,
    "ugwu-leaves": 0.12,
    "coleslaw-nigerian": 0.75,
    "carrots-raw": 0.64,
    "cabbage-raw": 0.18,
    "garden-egg": 0.90,
    "green-beans-raw": 0.30,
    "lettuce-raw": 0.06,
    "red-bell-pepper-sliced": 0.72,

    # FRUIT
    "watermelon-fresh": 0.96,
    "pineapple-fresh": 1.00,
    "banana-fresh": 0.96,
    "pawpaw-fresh": 0.95,
    "orange-fresh": 0.96,
    "mango-fresh": 1.00,
    "apple-fresh": 0.88,
    "agbalumo": 0.95,
    "avocado-pear": 1.00,
    "african-pear-ube": 1.02,
    "coconut-fresh": 0.90,
    "grapes-fresh": 0.85,

    # STARCH
    "boiled-yam": 1.00,
    "boiled-plantain-unripe": 1.02,
    "boiled-plantain-ripe": 0.98,
    "fried-yam": 0.88,
    "white-bread": 0.28,
    "agege-bread": 0.38,
    "whole-wheat-bread": 0.35,
    "yam-porridge-asaro": 0.95,
    "potato-porridge": 0.95,
    "plantain-porridge": 0.93,
    "rice-and-beans": 0.90,
    "coconut-rice": 0.88,
    "indomie-noodles": 0.85,
    "fried-plantain-ripe": 0.70,

    # SWALLOW
    "semovita": 1.05,
    "tuwo-shinkafa": 1.02,

    # SOUPS
    "okro-soup": 0.97,
    "tomato-stew-nigerian": 0.92,
    "bitterleaf-soup": 0.94,
    "ayamase-ofada-stew": 0.95,

    # SNACKS
    "groundnut-roasted": 0.62,
    "nigerian-egg-roll": 0.75,
    "boiled-corn-ube": 0.85,
    "roasted-corn-agbado": 0.88,
    "almonds-raw": 0.55,
    "granola": 0.40,
    "nigerian-shawarma": 0.65,
    "plantain-chips": 0.25,
    "soaked-garri-with-groundnut": 0.82,
    "masa-northern-rice-cakes": 0.75,
    "meat-pie": 0.70,
    "sausage-roll": 0.55,

    # BEVERAGES
    "zobo": 1.01,
    "kunu": 1.01,
    "pap-ogi-akamu": 0.90,
    "custard-nigerian-style": 0.95,
    "fresh-orange-juice": 1.04,
    "coconut-water": 1.01,
    "malt-drink": 1.04,
    "soy-milk": 1.02,
    "ginger-drink": 1.02,
    "chapman": 1.03,
    "palm-oil": 0.915,

    # BREAKFAST / NEW FOODS
    "pancakes": 0.55,
    "cake-plain": 0.38,
    "potato-salad": 0.90,

    # AUTO-SCAFFOLDED — review and adjust values
    "stewed-chicken-nigerian": 1.02,  # from knowledge base
    "peppered-chicken": 1.02,  # from knowledge base
    "chicken-wings-roasted": 1.0,  # from knowledge base
    "scrambled-eggs": 0.95,  # from knowledge base
    "omelette": 0.95,  # from knowledge base
    "sunny-side-up-egg": 1.0,  # from knowledge base

    # AUTO-SCAFFOLDED — review and adjust values
    "abacha-african-salad": 0.85,  # from knowledge base
    "sausages-cooked": 1.05,  # from knowledge base
    "ewedu-soup": 0.98,  # from knowledge base
    "sardines-canned": 1.1,  # from knowledge base
    "jollof-spaghetti": 0.9,  # from knowledge base
    "boiled-potatoes": 0.95,  # from knowledge base
    "turkey-peppered": 1.02,  # from knowledge base

    # AUTO-SCAFFOLDED — review and adjust values
    "sweet-corn-cooked": 0.75,  # from knowledge base
    "spring-onions": 0.5,  # from knowledge base
    "shrimp-cooked": 1.05,  # from knowledge base
    "broccoli-cooked": 0.35,  # from knowledge base
}


def get_density(food_name: str) -> float:
    """
    Get density value for a Nigerian food item
    
    Args:
        food_name: Name or ID of the food
    
    Returns:
        Density in g/ml
    """
    # Normalize food name
    food_key = food_name.lower().replace(" ", "-").replace("_", "-")
    
    # Try exact match
    if food_key in NIGERIAN_FOOD_DENSITIES:
        return NIGERIAN_FOOD_DENSITIES[food_key]
    
    # Try partial match
    for key, density in NIGERIAN_FOOD_DENSITIES.items():
        if key in food_key or food_key in key:
            return density
    
    # Return default
    return NIGERIAN_FOOD_DENSITIES["default"]


def estimate_weight_from_volume(volume_ml: float, food_name: str) -> float:
    """
    Estimate weight from volume using food-specific density
    
    Args:
        volume_ml: Volume in milliliters
        food_name: Name of the food
    
    Returns:
        Estimated weight in grams
    """
    density = get_density(food_name)
    return volume_ml * density

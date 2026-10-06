"""
Meal Title Generator

Generates natural, human-readable meal titles from a list of food names.
Kally understands food relationships — main dishes, soups, proteins, sides —
and uses that knowledge to join names intelligently.

Examples:
  ["Jollof Rice", "Chicken"]               → "Jollof Rice with Chicken"
  ["Eba", "Egusi Soup"]                     → "Eba with Egusi Soup"
  ["Boiled Yam", "Egg Sauce", "Raw Onions"] → "Boiled Yam with Egg Sauce and Raw Onions"
  ["Bread", "Butter"]                       → "Bread and Butter"
  ["Fried Rice"]                            → "Fried Rice"
"""

import re
from typing import List


# Food categories by role — determines joining word selection
# Main dishes come first in the title; sauces/soups/sides follow with "with"
MAIN_DISH_KEYWORDS = {
    "rice", "eba", "fufu", "pounded yam", "amala", "semovita", "tuwo",
    "yam", "plantain", "spaghetti", "indomie", "noodles", "beans",
    "porridge", "oatmeal", "bread", "akara", "moi moi", "agege",
    "nkwobi", "abacha", "boli",
}

SOUP_SAUCE_KEYWORDS = {
    "soup", "stew", "sauce", "egusi", "ogbono", "efo", "okro", "banga",
    "afang", "edikang", "oha", "ewedu", "bitterleaf", "pepper soup",
    "tomato", "curry",
}

PROTEIN_KEYWORDS = {
    "chicken", "beef", "goat", "fish", "turkey", "suya", "shrimp",
    "prawns", "catfish", "tilapia", "sardines", "sausage", "egg",
    "ponmo", "stock fish", "smoked fish",
}


def _clean_name(name: str) -> str:
    """
    Clean a food name:
    - Strip parenthetical descriptors that add no meaning (Nigerian Style, etc.)
    - Move cooking method from parentheses into the name naturally
    - Capitalise properly

    Examples:
      "Egg Sauce (Nigerian Style)" → "Egg Sauce"
      "Chicken (Grilled)"          → "Grilled Chicken"
      "Rice (Fried)"               → "Fried Rice"
      "Plantain (Ripe, Fried)"     → "Fried Ripe Plantain"
    """
    name = name.strip()

    # Extract parenthetical content
    match = re.search(r'\(([^)]+)\)', name)
    if not match:
        return name

    base = name[:match.start()].strip()
    descriptor = match.group(1).strip()

    # Descriptors that are just origin/style tags — drop them entirely
    drop_patterns = [
        r"nigerian\s+style",
        r"nigerian",
        r"local",
        r"style",
        r"traditional",
        r"homemade",
        r"classic",
    ]
    for pattern in drop_patterns:
        if re.fullmatch(pattern, descriptor, re.IGNORECASE):
            return base

    # Cooking method descriptors — move in front of the base name
    cooking_methods = {
        "grilled", "fried", "boiled", "steamed", "roasted",
        "stewed", "baked", "peppered", "smoked", "dried",
    }

    # Handle compound descriptors like "Ripe, Fried" → "Fried Ripe"
    parts = [p.strip() for p in descriptor.split(",")]
    methods = [p for p in parts if p.lower() in cooking_methods]
    qualifiers = [p for p in parts if p.lower() not in cooking_methods]

    if methods:
        prefix = " ".join(methods + qualifiers)
        return f"{prefix} {base}"

    # If descriptor is something else (e.g. a variety or type), keep it as suffix
    # but without the parentheses for cleaner display
    return f"{base} {descriptor}"


def _is_main(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in MAIN_DISH_KEYWORDS)


def _is_soup_sauce(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in SOUP_SAUCE_KEYWORDS)


def _is_protein(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in PROTEIN_KEYWORDS)


def generate_meal_title(food_names: List[str]) -> str:
    """
    Generate a natural meal title from a list of food names.

    Rules:
    1. Clean each name (strip brackets, fix cooking method placement)
    2. Sort: main dishes first, then soups/sauces, then proteins, then sides
    3. Join:
       - 1 food  → just the name
       - 2 foods → "{food1} with {food2}"  (if clear main+side relationship)
                 → "{food1} and {food2}"   (if peers, e.g. bread and butter)
       - 3+ foods → "{food1} with {food2} and {food3}"
                  → "{food1}, {food2} and {food3}" (if no clear hierarchy)
    """
    if not food_names:
        return "Your Meal"

    # Clean all names
    cleaned = [_clean_name(n) for n in food_names]

    if len(cleaned) == 1:
        return cleaned[0]

    # Sort by role: mains first, then soups/sauces, then proteins, then rest
    def sort_key(name: str) -> int:
        if _is_main(name):
            return 0
        if _is_soup_sauce(name):
            return 1
        if _is_protein(name):
            return 2
        return 3

    sorted_foods = sorted(cleaned, key=sort_key)

    first = sorted_foods[0]
    rest = sorted_foods[1:]

    # Determine joining strategy
    first_is_main = _is_main(first)
    has_hierarchical_rest = any(_is_soup_sauce(f) or _is_protein(f) for f in rest)

    if len(sorted_foods) == 2:
        second = rest[0]
        # Clear main + accompaniment → "with"
        if first_is_main or _is_soup_sauce(second) or _is_protein(second):
            return f"{first} with {second}"
        # Peers (bread + butter, rice + beans cooked together) → "and"
        return f"{first} and {second}"

    # 3+ foods
    if first_is_main and has_hierarchical_rest:
        # "Eba with Egusi Soup and Smoked Fish"
        return f"{first} with {', '.join(rest[:-1])} and {rest[-1]}" if len(rest) > 1 else f"{first} with {rest[0]}"

    # No clear hierarchy — comma list with "and" before last
    return f"{', '.join(sorted_foods[:-1])} and {sorted_foods[-1]}"

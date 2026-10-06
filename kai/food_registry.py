"""
Food Registry - Canonical food names from the knowledge base.

This module provides a single source of truth for food names that:
1. Vision Agent must use when identifying foods
2. Knowledge Agent uses for lookups

This ensures perfect communication between agents.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set


# Ingredients that are real foods worth promoting to standalone nutrition lookups.
# These are things visibly ADDED to a dish — not seasonings or base sauces.
# Values are default portion sizes in grams when used as an added ingredient.
PROMOTABLE_INGREDIENTS = {
    "carrots": 40,
    "carrot": 40,
    "green peas": 40,
    "peas": 40,
    "cabbage": 40,
    "spinach": 30,
    "ugwu": 30,
    "fluted pumpkin leaves": 30,
    "waterleaf": 30,
    "bitter leaf": 25,
    "uziza": 20,
    "scent leaf": 15,
    "green beans": 40,
    "green pepper": 30,
    "bell pepper": 30,
    "tomatoes": 40,
    "tomato": 40,
    "cucumber": 40,
    "lettuce": 30,
    "onions": 25,
    "onion": 25,
    "mushrooms": 30,
    "mushroom": 30,
    "sweet potatoes": 80,
    "sweet potato": 80,
    "boiled egg": 50,
    "fried egg": 60,
    "egg": 50,
    "plantain": 80,
    "avocado": 60,
    "sausage": 50,
    "sausages": 50,
    "sweet corn": 40,
    "corn": 40,
    "spring onions": 15,
    "spring onion": 15,
    "scallions": 15,
    "scallion": 15,
    "shrimp": 50,
    "prawns": 50,
    "prawn": 50,
    "broccoli": 40,
}

logger = logging.getLogger(__name__)

# Path to the canonical food database
FOODS_JSONL_PATH = Path(__file__).parent.parent / "knowledge-base" / "data" / "processed" / "nigerian_foods_v2_improved.jsonl"


class FoodRegistry:
    """
    Registry of all known Nigerian foods with their canonical names and aliases.

    Ensures Vision Agent outputs names that exactly match the knowledge base.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if FoodRegistry._initialized:
            return

        self.foods: Dict[str, dict] = {}  # name -> {id, aliases, category}
        self.aliases_to_name: Dict[str, str] = {}  # alias -> canonical name
        self.names_by_category: Dict[str, List[str]] = {}

        self._load_foods()
        FoodRegistry._initialized = True

    def _load_foods(self):
        """Load all foods from the JSONL database."""
        if not FOODS_JSONL_PATH.exists():
            logger.warning(f"Food database not found at {FOODS_JSONL_PATH}")
            return

        with open(FOODS_JSONL_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    food = json.loads(line)
                    name = food['name']
                    category = food.get('category', 'unknown')

                    # Extract portion info from common_servings
                    servings = food.get('common_servings', {})

                    self.foods[name] = {
                        'id': food['id'],
                        'aliases': food.get('aliases', []),
                        'category': category,
                        'typical_portion_g': servings.get('typical_portion_g', 150),
                        'min_reasonable_g': servings.get('min_reasonable_g', 50),
                        'max_reasonable_g': servings.get('max_reasonable_g', 300),
                        'countable': food.get('countable', False),
                    }

                    # Map all aliases to canonical name
                    for alias in food.get('aliases', []):
                        self.aliases_to_name[alias.lower()] = name

                    # Also map the name itself (lowercase)
                    self.aliases_to_name[name.lower()] = name

                    # Group by category
                    if category not in self.names_by_category:
                        self.names_by_category[category] = []
                    self.names_by_category[category].append(name)

                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Error parsing food entry: {e}")
                    continue

        logger.info(f"✓ FoodRegistry loaded {len(self.foods)} foods")

    def get_all_names(self) -> List[str]:
        """Get all canonical food names."""
        return list(self.foods.keys())

    def get_names_by_category(self, category: str) -> List[str]:
        """Get food names for a specific category."""
        return self.names_by_category.get(category, [])

    def get_canonical_name(self, input_name: str) -> str:
        """
        Convert any food name/alias to its canonical database name.

        Args:
            input_name: Food name from Vision Agent (may be alias or variant)

        Returns:
            Canonical name that matches the database, or original if no match
        """
        # Try exact match first
        if input_name in self.foods:
            return input_name

        # Try lowercase alias lookup
        canonical = self.aliases_to_name.get(input_name.lower())
        if canonical:
            return canonical

        # No match found - return original
        return input_name

    def is_known_food(self, name: str) -> bool:
        """Check if a food name (or alias) is in the database."""
        if name in self.foods:
            return True
        return name.lower() in self.aliases_to_name

    def is_countable(self, name: str) -> bool:
        """Check if a food is a discrete countable item (slices, pieces, balls, etc.)."""
        canonical = self.get_canonical_name(name)
        return self.foods.get(canonical, {}).get('countable', False)

    def get_food_info(self, name: str) -> dict:
        """Get food info by name or alias."""
        canonical = self.get_canonical_name(name)
        return self.foods.get(canonical, {})

    def get_vision_agent_food_list(self) -> str:
        """
        Generate a formatted food list for Vision Agent prompt.

        Returns:
            Formatted string with all food names grouped by category
        """
        lines = []

        # Order categories for the prompt
        category_order = ['starch', 'swallow', 'protein', 'soup', 'vegetable', 'fruit', 'snack', 'beverage', 'condiment', 'protein_dish']

        for category in category_order:
            if category in self.names_by_category:
                foods = self.names_by_category[category]
                category_display = category.replace('_', ' ').title()
                lines.append(f"\n**{category_display}:** {', '.join(foods)}")

        # Add any remaining categories
        for category, foods in self.names_by_category.items():
            if category not in category_order:
                category_display = category.replace('_', ' ').title()
                lines.append(f"\n**{category_display}:** {', '.join(foods)}")

        return ''.join(lines)


# Singleton instance
_registry = None

def get_food_registry() -> FoodRegistry:
    """Get the singleton FoodRegistry instance."""
    global _registry
    if _registry is None:
        _registry = FoodRegistry()
    return _registry


def get_canonical_food_name(name: str) -> str:
    """Convenience function to get canonical name."""
    return get_food_registry().get_canonical_name(name)


def get_all_food_names() -> List[str]:
    """Convenience function to get all food names."""
    return get_food_registry().get_all_names()


def is_known_food(name: str) -> bool:
    """Convenience function to check if food is known."""
    return get_food_registry().is_known_food(name)


def get_ingredient_portion(ingredient_name: str) -> Optional[int]:
    """Return default portion in grams for a promotable ingredient, or None if not promotable."""
    return PROMOTABLE_INGREDIENTS.get(ingredient_name.lower().strip())

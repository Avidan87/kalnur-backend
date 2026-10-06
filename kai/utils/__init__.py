"""
KAI Utilities Package

Helper functions for the KAI nutrition app:
- Multi-nutrient RDV calculations
"""

from .nutrition_rdv import (
    calculate_user_rdv,
    get_nutrient_gap_priority,
    get_primary_nutritional_gap,
)
from .meal_title import generate_meal_title

__all__ = [
    "calculate_user_rdv",
    "get_nutrient_gap_priority",
    "get_primary_nutritional_gap",
    "generate_meal_title",
]

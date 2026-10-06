"""
KAI Services Package

Shared services for nutrition tracking, goal management, and system utilities.
"""

from .nutrition_priorities import (
    HealthGoal,
    NutrientRDV,
    get_priority_nutrients,
    get_personalized_rdvs,
    get_priority_rdvs,
    calculate_rdv_percentages,
    get_secondary_alerts,
    format_nutrient_summary,
    get_nutrient_emoji,
    get_goal_emoji,
    get_goal_display_name,
    get_primary_nutrient,
    get_goal_context,
    calculate_meal_threshold,
    get_all_meal_thresholds,
    assess_meal_nutrient,
    GOAL_NUTRIENT_PRIORITIES,
    GOAL_METADATA,
    NUTRIENT_EMOJIS,
)

__all__ = [
    "HealthGoal",
    "NutrientRDV",
    "get_priority_nutrients",
    "get_personalized_rdvs",
    "get_priority_rdvs",
    "calculate_rdv_percentages",
    "get_secondary_alerts",
    "format_nutrient_summary",
    "get_nutrient_emoji",
    "get_goal_emoji",
    "get_goal_display_name",
    "get_primary_nutrient",
    "get_goal_context",
    "calculate_meal_threshold",
    "get_all_meal_thresholds",
    "assess_meal_nutrient",
    "GOAL_NUTRIENT_PRIORITIES",
    "GOAL_METADATA",
    "NUTRIENT_EMOJIS",
]

"""
Goal-Driven Nutrient Priority Service

Assigns 6-8 priority nutrients per health goal, with personalized RDVs
based on gender, age, and goal. KAI is the nutrition expert - users don't
choose nutrients, the system intelligently assigns them.

Nutrient Pool (16 total):
- Macros (5): calories, protein, carbohydrates, fat, fiber
- Minerals (6): iron, calcium, zinc, potassium, sodium, magnesium
- Vitamins (5): vitamin_a, vitamin_c, vitamin_d, vitamin_b12, folate
"""

from typing import Dict, List, Optional, Literal
from dataclasses import dataclass
from enum import Enum


class HealthGoal(str, Enum):
    """Supported health goals"""
    LOSE_WEIGHT = "lose_weight"
    GAIN_MUSCLE = "gain_muscle"
    MAINTAIN_WEIGHT = "maintain_weight"
    GENERAL_WELLNESS = "general_wellness"
    PREGNANCY = "pregnancy"
    HEART_HEALTH = "heart_health"
    ENERGY_BOOST = "energy_boost"
    BONE_HEALTH = "bone_health"
    MANAGE_BLOOD_SUGAR = "manage_blood_sugar"


# =============================================================================
# NUTRIENT EMOJI MAPPING
# Visual icons for each nutrient (used in frontend/API responses)
# =============================================================================

NUTRIENT_EMOJIS: Dict[str, str] = {
    # Macros
    "calories": "🔥",
    "protein": "💪",
    "carbohydrates": "🍚",
    "fat": "🧈",
    "fiber": "🌾",
    # Minerals
    "iron": "🩸",
    "calcium": "🦴",
    "zinc": "⚡",
    "potassium": "🍌",
    "sodium": "🧂",
    "magnesium": "💎",
    # Vitamins
    "vitamin_a": "👁️",
    "vitamin_c": "🍊",
    "vitamin_d": "☀️",
    "vitamin_b12": "🔋",
    "folate": "🧬",
}


def get_nutrient_emoji(nutrient: str) -> str:
    """Get the emoji for a nutrient"""
    return NUTRIENT_EMOJIS.get(nutrient, "📊")


# =============================================================================
# GOAL METADATA
# Display names, emojis, and primary nutrients for each health goal
# =============================================================================

GOAL_METADATA: Dict[str, Dict[str, str]] = {
    "lose_weight": {
        "display_name": "Weight Loss",
        "emoji": "🏃",
        "primary_nutrient": "protein",  # Satiety + muscle preservation
        "description": "Lose weight while preserving muscle mass",
    },
    "gain_muscle": {
        "display_name": "Muscle Gain",
        "emoji": "💪",
        "primary_nutrient": "protein",  # Muscle protein synthesis
        "description": "Build lean muscle with proper nutrition",
    },
    "maintain_weight": {
        "display_name": "Weight Maintenance",
        "emoji": "⚖️",
        "primary_nutrient": "protein",  # Prevents muscle loss
        "description": "Maintain your current healthy weight",
    },
    "general_wellness": {
        "display_name": "General Wellness",
        "emoji": "🌟",
        "primary_nutrient": "protein",  # Foundation for body maintenance
        "description": "Overall health and balanced nutrition",
    },
    "pregnancy": {
        "display_name": "Pregnancy",
        "emoji": "🤰",
        "primary_nutrient": "folate",  # CRITICAL for neural tube development
        "description": "Optimal nutrition for you and baby",
    },
    "heart_health": {
        "display_name": "Heart Health",
        "emoji": "❤️",
        "primary_nutrient": "sodium",  # Blood pressure control (limit it)
        "description": "Cardiovascular health and blood pressure",
    },
    "energy_boost": {
        "display_name": "Energy Boost",
        "emoji": "⚡",
        "primary_nutrient": "iron",  # Oxygen transport = energy
        "description": "Combat fatigue and boost energy levels",
    },
    "bone_health": {
        "display_name": "Bone Health",
        "emoji": "🦴",
        "primary_nutrient": "calcium",  # Primary bone mineral
        "description": "Strong bones and skeletal health",
    },
    "manage_blood_sugar": {
        "display_name": "Manage Blood Sugar",
        "emoji": "🩸",
        "primary_nutrient": "fiber",
        "description": "Control blood sugar through low-GI eating",
    },
}


def get_goal_emoji(goal: str) -> str:
    """Get the emoji for a health goal"""
    return GOAL_METADATA.get(goal, {}).get("emoji", "🎯")


def get_goal_display_name(goal: str) -> str:
    """Get the display name for a health goal"""
    return GOAL_METADATA.get(goal, {}).get("display_name", goal.replace("_", " ").title())


def get_primary_nutrient(goal: str) -> str:
    """Get the primary nutrient for a health goal (the one to focus on most)"""
    return GOAL_METADATA.get(goal, {}).get("primary_nutrient", "protein")


@dataclass
class NutrientRDV:
    """Recommended Daily Value for a nutrient"""
    name: str
    amount: float
    unit: str
    display_name: str


# =============================================================================
# GOAL-DRIVEN NUTRIENT MAPPINGS
# Each goal gets 6-8 priority nutrients based on nutritional science
# =============================================================================

GOAL_NUTRIENT_PRIORITIES: Dict[str, List[str]] = {
    # Weight Loss (6 nutrients) - Focus on satiety and metabolic health
    "lose_weight": [
        "calories",      # Primary: caloric deficit
        "protein",       # Preserve muscle, increase satiety
        "fiber",         # Satiety, gut health
        "carbohydrates", # Manage for energy balance
        "fat",           # Essential but controlled
        "sodium",        # Reduce water retention
    ],

    # Muscle Gain (7 nutrients) - Focus on protein synthesis and recovery
    "gain_muscle": [
        "calories",      # Caloric surplus needed
        "protein",       # Primary: muscle synthesis
        "carbohydrates", # Energy for workouts
        "fat",           # Hormone production
        "zinc",          # Testosterone, protein synthesis
        "magnesium",     # Muscle function, recovery
        "vitamin_b12",   # Energy metabolism, red blood cells
    ],

    # Weight Maintenance (6 nutrients) - Balanced tracking
    "maintain_weight": [
        "calories",      # Maintain energy balance
        "protein",       # Maintain muscle mass
        "carbohydrates", # Sustained energy
        "fat",           # Essential fatty acids
        "fiber",         # Digestive health
        "iron",          # Energy and vitality
    ],

    # General Wellness (6 nutrients) - Broad health coverage
    "general_wellness": [
        "calories",      # Energy balance
        "protein",       # Body maintenance
        "fiber",         # Gut health
        "iron",          # Energy, immunity
        "vitamin_c",     # Immunity, antioxidant
        "calcium",       # Bone, muscle function
    ],

    # Pregnancy (8 nutrients) - Maximum nutrients for fetal development
    "pregnancy": [
        "calories",      # Increased energy needs (+300 kcal)
        "protein",       # Fetal growth
        "folate",        # CRITICAL: neural tube development
        "iron",          # Blood volume, prevent anemia
        "calcium",       # Bone development
        "vitamin_d",     # Calcium absorption, immunity
        "zinc",          # Cell division, immune function
        "vitamin_b12",   # Neurological development
    ],

    # Heart Health (7 nutrients) - Cardiovascular focus
    "heart_health": [
        "calories",      # Weight management
        "sodium",        # Blood pressure control (limit)
        "potassium",     # Blood pressure balance
        "fiber",         # Cholesterol management
        "fat",           # Limit saturated fats
        "magnesium",     # Heart rhythm, blood pressure
        "vitamin_c",     # Antioxidant, vascular health
    ],

    # Energy Boost (6 nutrients) - Combat fatigue
    "energy_boost": [
        "calories",      # Adequate energy intake
        "iron",          # Oxygen transport, prevent fatigue
        "vitamin_b12",   # Energy metabolism
        "carbohydrates", # Primary energy source
        "magnesium",     # ATP production
        "vitamin_c",     # Iron absorption
    ],

    # Bone Health (7 nutrients) - Skeletal strength
    "bone_health": [
        "calories",      # Maintain healthy weight
        "calcium",       # Primary bone mineral
        "vitamin_d",     # Calcium absorption
        "protein",       # Bone matrix
        "magnesium",     # Bone structure
        "zinc",          # Bone formation
        "potassium",     # Reduce calcium loss
    ],

    # Manage Blood Sugar (6 nutrients) - Low-GI, insulin-friendly
    "manage_blood_sugar": [
        "fiber",       # PRIMARY: slows glucose absorption
        "protein",     # Blunts blood sugar spikes
        "magnesium",   # Insulin sensitivity
        "fat",         # Slows digestion, reduces GI impact
        "vitamin_c",   # Antioxidant, reduces spike inflammation
        "potassium",   # Supports insulin function
    ],
    # NOTE: carbohydrates deliberately excluded — sugar teaspoon display
    # handles carb awareness visually. Including carbs would coach users to eat MORE carbs.
}


# =============================================================================
# PERSONALIZED RDV CALCULATIONS
# Based on gender, age, activity level, and goal
# =============================================================================

# Base RDVs by gender (adult defaults)
BASE_RDVS_MALE: Dict[str, tuple] = {
    # (amount, unit, display_name)
    "calories": (2500, "kcal", "Calories"),
    "protein": (56, "g", "Protein"),
    "carbohydrates": (300, "g", "Carbs"),
    "fat": (78, "g", "Fat"),
    "fiber": (38, "g", "Fiber"),
    "iron": (8, "mg", "Iron"),
    "calcium": (1000, "mg", "Calcium"),
    "zinc": (11, "mg", "Zinc"),
    "potassium": (3400, "mg", "Potassium"),
    "sodium": (2300, "mg", "Sodium"),
    "magnesium": (420, "mg", "Magnesium"),
    "vitamin_a": (900, "mcg", "Vitamin A"),
    "vitamin_c": (90, "mg", "Vitamin C"),
    "vitamin_d": (15, "mcg", "Vitamin D"),
    "vitamin_b12": (2.4, "mcg", "Vitamin B12"),
    "folate": (400, "mcg", "Folate"),
}

BASE_RDVS_FEMALE: Dict[str, tuple] = {
    "calories": (2000, "kcal", "Calories"),
    "protein": (46, "g", "Protein"),
    "carbohydrates": (250, "g", "Carbs"),
    "fat": (65, "g", "Fat"),
    "fiber": (25, "g", "Fiber"),
    "iron": (18, "mg", "Iron"),  # Higher for menstruating women
    "calcium": (1000, "mg", "Calcium"),
    "zinc": (8, "mg", "Zinc"),
    "potassium": (2600, "mg", "Potassium"),
    "sodium": (2300, "mg", "Sodium"),
    "magnesium": (320, "mg", "Magnesium"),
    "vitamin_a": (700, "mcg", "Vitamin A"),
    "vitamin_c": (75, "mg", "Vitamin C"),
    "vitamin_d": (15, "mcg", "Vitamin D"),
    "vitamin_b12": (2.4, "mcg", "Vitamin B12"),
    "folate": (400, "mcg", "Folate"),
}

# Goal-specific RDV adjustments (multipliers)
GOAL_RDV_ADJUSTMENTS: Dict[str, Dict[str, float]] = {
    "lose_weight": {
        "calories": 0.80,     # 20% deficit
        "protein": 1.20,      # Higher protein for satiety
        "sodium": 0.85,       # Reduce sodium
    },
    "gain_muscle": {
        "calories": 1.15,     # 15% surplus
        "protein": 1.60,      # Much higher protein (1.6-2.2g/kg)
        "carbohydrates": 1.20,
        "zinc": 1.10,
    },
    "maintain_weight": {
        # No adjustments - use base RDVs
    },
    "general_wellness": {
        # No adjustments - use base RDVs
    },
    "pregnancy": {
        "calories": 1.15,     # +300 kcal in 2nd/3rd trimester
        "protein": 1.30,      # +25g/day
        "iron": 1.50,         # 27mg vs 18mg
        "folate": 1.50,       # 600mcg vs 400mcg
        "calcium": 1.00,      # Same but critical
        "vitamin_d": 1.00,    # Same but critical
        "zinc": 1.375,        # 11mg vs 8mg — WHO/NIH pregnancy requirement for fetal cell division
    },
    "heart_health": {
        "sodium": 0.65,       # Max 1500mg
        "potassium": 1.10,    # Increase for BP balance
        "fiber": 1.20,        # More fiber for cholesterol
    },
    "energy_boost": {
        "iron": 1.10,
        "vitamin_b12": 1.10,
        "magnesium": 1.10,
    },
    "bone_health": {
        "calcium": 1.20,      # 1200mg for bone health
        "vitamin_d": 1.33,    # 20mcg for better absorption
    },
    "manage_blood_sugar": {
        "fiber": 1.40,
        "protein": 1.20,
        "magnesium": 1.10,
    },
}

# Age adjustments
AGE_ADJUSTMENTS: Dict[str, Dict[str, float]] = {
    "under_30": {},  # Base rates
    "30_50": {
        "calcium": 1.0,
    },
    "over_50": {
        "calcium": 1.20,      # Increased bone loss risk
        "vitamin_d": 1.33,    # Reduced skin synthesis
        "vitamin_b12": 1.25,  # Reduced absorption
        "protein": 1.10,      # Prevent muscle loss
    },
}


def get_age_group(age: Optional[int]) -> str:
    """Determine age group for RDV adjustments"""
    if age is None:
        return "under_30"  # Default
    if age < 30:
        return "under_30"
    if age <= 50:
        return "30_50"
    return "over_50"


def get_priority_nutrients(goal: str) -> List[str]:
    """
    Get the priority nutrients for a health goal.

    Args:
        goal: Health goal (e.g., "lose_weight", "gain_muscle")

    Returns:
        List of 6-8 nutrient names to track for this goal
    """
    return GOAL_NUTRIENT_PRIORITIES.get(goal, GOAL_NUTRIENT_PRIORITIES["general_wellness"])


def get_personalized_rdvs(
    goal: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    custom_calorie_goal: Optional[float] = None
) -> Dict[str, NutrientRDV]:
    """
    Calculate personalized RDVs for a user based on their profile.

    When custom_calorie_goal is provided (which should be the BMR/TDEE-derived
    active_calorie_goal, or a user override), macros (protein, carbs, fat) are
    derived from that calorie budget using the same ratios as V2 — ensuring
    coaching targets are fully aligned with the user's actual energy needs.

    Args:
        goal: Health goal
        gender: "male" or "female" (defaults to female for safety)
        age: User's age
        custom_calorie_goal: The active calorie goal (BMR-derived or user override)

    Returns:
        Dict mapping nutrient name to NutrientRDV with personalized values
    """
    # Start with base RDVs by gender
    base_rdvs = BASE_RDVS_MALE if gender == "male" else BASE_RDVS_FEMALE

    # Get adjustments
    goal_adj = GOAL_RDV_ADJUSTMENTS.get(goal, {})
    age_group = get_age_group(age)
    age_adj = AGE_ADJUSTMENTS.get(age_group, {})

    # Goal-specific protein % of total calories — mirrors V2's g/kg ratios
    # (lose_weight 1.8g/kg ≈ 30%, gain_muscle 2.0g/kg ≈ 32%, etc.)
    PROTEIN_PCT_OF_CALORIES: Dict[str, float] = {
        "lose_weight": 0.30,      # High protein preserves muscle during deficit
        "gain_muscle": 0.32,      # Maximum protein for muscle synthesis
        "maintain_weight": 0.25,  # Moderate — prevent muscle loss
        "general_wellness": 0.20, # Baseline healthy intake
        "pregnancy": 0.22,        # Slightly elevated for fetal growth
        "heart_health": 0.22,     # Lean protein, moderate amount
        "energy_boost": 0.22,     # Moderate — energy from carbs, not protein
        "bone_health": 0.22,      # Adequate for bone matrix
        "manage_blood_sugar": 0.25,  # Higher protein to blunt glucose spikes
    }
    FAT_PCT_OF_CALORIES = 0.28    # Consistent with V2 (essential for hormones)

    personalized = {}

    # Pre-compute macro overrides from calorie budget if we have the real calorie goal
    macro_overrides: Dict[str, float] = {}
    if custom_calorie_goal:
        protein_pct = PROTEIN_PCT_OF_CALORIES.get(goal, 0.22)
        protein_kcal = custom_calorie_goal * protein_pct
        fat_kcal = custom_calorie_goal * FAT_PCT_OF_CALORIES
        carbs_kcal = custom_calorie_goal - protein_kcal - fat_kcal

        macro_overrides = {
            "protein": round(protein_kcal / 4, 1),       # 4 kcal/g
            "fat": round(fat_kcal / 9, 1),               # 9 kcal/g
            "carbohydrates": round(carbs_kcal / 4, 1),   # 4 kcal/g
        }

    for nutrient, (base_amount, unit, display_name) in base_rdvs.items():
        # Apply goal adjustment
        amount = base_amount * goal_adj.get(nutrient, 1.0)

        # Apply age adjustment
        amount = amount * age_adj.get(nutrient, 1.0)

        # Override calories with the real BMR-derived goal
        if nutrient == "calories" and custom_calorie_goal:
            amount = custom_calorie_goal

        # Override macros derived from the real calorie budget
        if nutrient in macro_overrides:
            amount = macro_overrides[nutrient]

        personalized[nutrient] = NutrientRDV(
            name=nutrient,
            amount=round(amount, 1),
            unit=unit,
            display_name=display_name
        )

    return personalized


def get_priority_rdvs(
    goal: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    custom_calorie_goal: Optional[float] = None
) -> Dict[str, NutrientRDV]:
    """
    Get personalized RDVs for only the priority nutrients of a goal.

    Args:
        goal: Health goal
        gender: "male" or "female"
        age: User's age
        custom_calorie_goal: Override calorie goal

    Returns:
        Dict with only the priority nutrients and their RDVs
    """
    all_rdvs = get_personalized_rdvs(goal, gender, age, custom_calorie_goal)
    priority_nutrients = get_priority_nutrients(goal)

    return {
        nutrient: all_rdvs[nutrient]
        for nutrient in priority_nutrients
        if nutrient in all_rdvs
    }


def calculate_rdv_percentages(
    consumed: Dict[str, float],
    goal: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    custom_calorie_goal: Optional[float] = None
) -> Dict[str, float]:
    """
    Calculate what percentage of RDV has been consumed for priority nutrients.

    Args:
        consumed: Dict of nutrient name to amount consumed
        goal: Health goal
        gender: User's gender
        age: User's age
        custom_calorie_goal: Override calorie goal

    Returns:
        Dict mapping nutrient name to percentage of RDV (0-100+)
    """
    rdvs = get_priority_rdvs(goal, gender, age, custom_calorie_goal)

    percentages = {}
    for nutrient, rdv in rdvs.items():
        consumed_amount = consumed.get(nutrient, 0.0)
        if rdv.amount > 0:
            percentages[nutrient] = round((consumed_amount / rdv.amount) * 100, 1)
        else:
            percentages[nutrient] = 0.0

    return percentages


def get_secondary_alerts(
    consumed: Dict[str, float],
    goal: str,
    gender: Optional[str] = None,
    age: Optional[int] = None
) -> List[Dict[str, any]]:
    """
    Check secondary (non-priority) nutrients for critical levels.
    Only alert if >120% (excess) or <30% (severely deficient) at end of day.

    Args:
        consumed: Dict of nutrient name to amount consumed
        goal: Health goal (to know which are secondary)
        gender: User's gender
        age: User's age

    Returns:
        List of alert dicts with nutrient, level, percentage, and message
    """
    all_rdvs = get_personalized_rdvs(goal, gender, age)
    priority_nutrients = set(get_priority_nutrients(goal))

    alerts = []

    for nutrient, rdv in all_rdvs.items():
        # Skip priority nutrients - they're always shown
        if nutrient in priority_nutrients:
            continue

        consumed_amount = consumed.get(nutrient, 0.0)
        if rdv.amount <= 0:
            continue

        percentage = (consumed_amount / rdv.amount) * 100

        # Critical high (>120%)
        if percentage > 120:
            alerts.append({
                "nutrient": nutrient,
                "display_name": rdv.display_name,
                "level": "high",
                "percentage": round(percentage, 1),
                "message": f"{rdv.display_name} is high ({round(percentage)}% of daily limit)"
            })

        # Critical low (<30%) - only meaningful at end of day
        elif percentage < 30:
            alerts.append({
                "nutrient": nutrient,
                "display_name": rdv.display_name,
                "level": "low",
                "percentage": round(percentage, 1),
                "message": f"{rdv.display_name} is very low ({round(percentage)}% of daily need)"
            })

    return alerts


def format_nutrient_summary(
    consumed: Dict[str, float],
    goal: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    custom_calorie_goal: Optional[float] = None
) -> str:
    """
    Format a human-readable summary of nutrient intake vs goals.
    Used by chat agent for meal feedback.

    Args:
        consumed: Dict of nutrient name to amount consumed today
        goal: Health goal
        gender: User's gender
        age: User's age
        custom_calorie_goal: Override calorie goal

    Returns:
        Formatted string summary
    """
    rdvs = get_priority_rdvs(goal, gender, age, custom_calorie_goal)
    percentages = calculate_rdv_percentages(consumed, goal, gender, age, custom_calorie_goal)

    lines = []
    for nutrient in get_priority_nutrients(goal):
        if nutrient not in rdvs:
            continue
        rdv = rdvs[nutrient]
        pct = percentages.get(nutrient, 0)
        consumed_amt = consumed.get(nutrient, 0)

        # Status indicator
        # Sodium is a ceiling for ALL goals — higher is always worse
        is_limit = nutrient in GOAL_LIMIT_NUTRIENTS.get(goal, LIMIT_NUTRIENTS)
        if is_limit:
            status = "ok" if pct <= 100 else "limit"
        elif pct >= 90 and pct <= 110:
            status = "ok"
        elif pct > 110:
            status = "high"
        else:
            status = "low"

        lines.append(
            f"{rdv.display_name}: {consumed_amt:.1f}/{rdv.amount:.0f}{rdv.unit} ({pct:.0f}%)"
        )

    return "\n".join(lines)


# =============================================================================
# PER-MEAL THRESHOLD SYSTEM
# Dynamic calculation of what constitutes "good" per meal for each nutrient
# =============================================================================

# Base percentage of daily RDV that's "good" for one meal
# Assumes 4-5 meals per day (breakfast, lunch, dinner, 1-2 snacks)
BASE_MEAL_PERCENTAGE = {
    "excellent": 0.28,  # 28% of daily (more than 1/4)
    "good": 0.20,       # 20% of daily (1/5)
}

# Goal-specific adjustments (multiplier on base percentage)
GOAL_MEAL_ADJUSTMENTS = {
    "lose_weight": {
        "protein": 1.3,      # Need MORE protein per meal (satiety)
        "fiber": 1.2,        # More fiber per meal (satiety)
        "calories": 0.9,     # Smaller meals (deficit)
    },
    "gain_muscle": {
        "protein": 1.4,      # Need MUCH more protein per meal (synthesis)
        "calories": 1.2,     # Larger meals (surplus)
        "carbohydrates": 1.15, # More carbs per meal (energy)
    },
    "maintain_weight": {
        # No adjustments - use base
    },
    "general_wellness": {
        # No adjustments - use base
    },
    "pregnancy": {
        "folate": 0.85,      # Spread throughout day (multiple small doses better)
        "iron": 0.8,         # Multiple small doses (absorption)
        "protein": 1.1,      # Slightly more per meal
    },
    "heart_health": {
        "sodium": 0.7,       # LOWER per meal (spread sodium out)
        "potassium": 1.1,    # More potassium per meal (BP control)
        "fiber": 1.2,        # More fiber per meal (cholesterol)
    },
    "energy_boost": {
        "iron": 1.1,         # More iron per meal (oxygen transport)
        "vitamin_b12": 1.0,  # Base (hard to get, but small amounts work)
        "carbohydrates": 1.1, # More carbs per meal (fuel)
    },
    "bone_health": {
        "calcium": 1.1,      # Slightly more per meal (absorption maxes at ~500mg)
        "vitamin_d": 1.0,    # Base (small amounts throughout day)
        "protein": 1.05,     # Slightly more (bone matrix)
    },
    "manage_blood_sugar": {
        "fiber": 1.30,
        "protein": 1.15,
    },
}

# Nutrient-specific constraints (min/max bounds)
NUTRIENT_BOUNDS = {
    "protein": {"min": 10.0, "max": 40.0},
    "calories": {"min": 250, "max": 1000},
    "folate": {"min": 80.0, "max": 250.0},
    "iron": {"min": 2.5, "max": 10.0},
    "calcium": {"min": 150.0, "max": 500.0},  # Max 500mg per meal (absorption limit)
    "zinc": {"min": 2.0, "max": 5.0},
    "magnesium": {"min": 60.0, "max": 150.0},
    "fiber": {"min": 4.0, "max": 12.0},
    "vitamin_c": {"min": 15.0, "max": 50.0},
    "vitamin_d": {"min": 2.0, "max": 8.0},
    "vitamin_b12": {"min": 0.5, "max": 1.5},
    "vitamin_a": {"min": 120.0, "max": 350.0},
    "potassium": {"min": 500.0, "max": 1200.0},
    "carbohydrates": {"min": 30.0, "max": 80.0},
    "fat": {"min": 10.0, "max": 35.0},
    "sodium": {"min": 200.0, "max": 800.0},
}

# Limit nutrients (lower is better)
LIMIT_NUTRIENTS = ["sodium"]

# Goal-specific limit nutrients (overrides LIMIT_NUTRIENTS per goal)
# For these nutrients, "lower is better" — assess_meal_nutrient returns "high" if exceeded
GOAL_LIMIT_NUTRIENTS: Dict[str, List[str]] = {
    "heart_health": ["sodium", "fat"],      # Fat control critical for cardiovascular health
    "lose_weight": ["sodium", "fat"],       # Fat control for caloric deficit
    "gain_muscle": ["sodium"],
    "maintain_weight": ["sodium"],
    "general_wellness": ["sodium"],
    "pregnancy": ["sodium"],
    "energy_boost": ["sodium"],
    "bone_health": ["sodium"],
    "manage_blood_sugar": ["sodium"],
}


def calculate_meal_threshold(
    nutrient: str,
    daily_rdv: float,
    health_goal: str,
    level: str = "good"
) -> float:
    """
    Calculate dynamic per-meal threshold for a nutrient.

    Args:
        nutrient: Nutrient name (e.g., "protein", "folate")
        daily_rdv: Daily RDV target for this nutrient
        health_goal: User's health goal (e.g., "pregnancy", "gain_muscle")
        level: Threshold level ("good" or "excellent")

    Returns:
        Per-meal threshold amount (same unit as daily_rdv)

    Examples:
        >>> # Pregnancy: folate 600mcg daily
        >>> calculate_meal_threshold("folate", 600, "pregnancy", "good")
        102.0  # 600 * 0.20 * 0.85 = 102mcg

        >>> # Muscle gain: protein 135g daily
        >>> calculate_meal_threshold("protein", 135, "gain_muscle", "good")
        37.8  # 135 * 0.20 * 1.4 = 37.8g

        >>> # Weight loss: protein 72g daily
        >>> calculate_meal_threshold("protein", 72, "lose_weight", "good")
        18.7  # 72 * 0.20 * 1.3 = 18.7g
    """
    # Get base percentage for this level
    base_pct = BASE_MEAL_PERCENTAGE.get(level, 0.20)

    # Get goal-specific adjustment for this nutrient
    goal_adjustments = GOAL_MEAL_ADJUSTMENTS.get(health_goal, {})
    adjustment = goal_adjustments.get(nutrient, 1.0)  # Default: no adjustment

    # Calculate threshold
    threshold = daily_rdv * base_pct * adjustment

    # Apply bounds
    if nutrient in NUTRIENT_BOUNDS:
        bounds = NUTRIENT_BOUNDS[nutrient]
        threshold = max(bounds["min"], min(bounds["max"], threshold))

    return round(threshold, 1)


def get_all_meal_thresholds(
    health_goal: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    custom_calorie_goal: Optional[float] = None
) -> Dict[str, Dict[str, float]]:
    """
    Get meal thresholds for ALL priority nutrients for a user's goal.

    Args:
        health_goal: User's health goal
        gender: User's gender
        age: User's age
        custom_calorie_goal: Optional custom calorie override

    Returns:
        Dict mapping nutrient name to thresholds:
        {
            "protein": {"good": 18.7, "excellent": 26.2, "daily_rdv": 72},
            "folate": {"good": 102.0, "excellent": 142.8, "daily_rdv": 600},
            ...
        }
    """
    # Get personalized RDVs for this user's goal
    priority_rdvs = get_priority_rdvs(health_goal, gender, age, custom_calorie_goal)

    thresholds = {}
    for nutrient, rdv_obj in priority_rdvs.items():
        daily_rdv = rdv_obj.amount

        thresholds[nutrient] = {
            "good": calculate_meal_threshold(nutrient, daily_rdv, health_goal, "good"),
            "excellent": calculate_meal_threshold(nutrient, daily_rdv, health_goal, "excellent"),
            "daily_rdv": daily_rdv,
            "unit": rdv_obj.unit,
            "is_limit_nutrient": nutrient in GOAL_LIMIT_NUTRIENTS.get(health_goal, LIMIT_NUTRIENTS)
        }

    return thresholds


def assess_meal_nutrient(
    nutrient: str,
    meal_amount: float,
    threshold_data: Dict
) -> str:
    """
    Assess if a meal's nutrient amount is excellent/good/low.

    Args:
        nutrient: Nutrient name
        meal_amount: Amount in this meal
        threshold_data: Threshold dict from get_all_meal_thresholds

    Returns:
        "excellent" | "good" | "low" | "high" (high only for limit nutrients like sodium)

    Examples:
        >>> # Pregnancy folate: meal has 129mcg, threshold is 102mcg
        >>> threshold_data = {"good": 102.0, "excellent": 142.8, "is_limit_nutrient": False}
        >>> assess_meal_nutrient("folate", 129, threshold_data)
        "good"  # 129 >= 102 (good threshold)

        >>> # Muscle gain protein: meal has 28g, threshold is 37.8g
        >>> threshold_data = {"good": 37.8, "excellent": 52.9, "is_limit_nutrient": False}
        >>> assess_meal_nutrient("protein", 28, threshold_data)
        "low"  # 28 < 37.8 (below good threshold)

        >>> # Sodium: meal has 400mg, threshold is 600mg (limit nutrient)
        >>> threshold_data = {"good": 600, "excellent": 400, "is_limit_nutrient": True}
        >>> assess_meal_nutrient("sodium", 400, threshold_data)
        "excellent"  # 400 <= 400 (excellent for limit nutrient)
    """
    is_limit = threshold_data.get("is_limit_nutrient", False)
    good_threshold = threshold_data["good"]
    excellent_threshold = threshold_data["excellent"]

    if is_limit:
        # Lower is better (e.g., sodium)
        if meal_amount <= excellent_threshold:
            return "excellent"
        elif meal_amount <= good_threshold:
            return "good"
        else:
            return "high"  # Warning: too much
    else:
        # Higher is better (most nutrients)
        if meal_amount >= excellent_threshold:
            return "excellent"
        elif meal_amount >= good_threshold:
            return "good"
        else:
            return "low"


# =============================================================================
# GOAL CONTEXT - SINGLE SOURCE OF TRUTH
# One function to get everything the chat agent needs
# =============================================================================

def get_goal_context(
    goal: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    custom_calorie_goal: Optional[float] = None
) -> Dict:
    """
    Get complete goal context for chat agent and API.

    This is the SINGLE SOURCE OF TRUTH for goal-driven nutrition.
    Call this once and you have everything you need.

    Args:
        goal: Health goal (e.g., "lose_weight", "pregnancy")
        gender: "male" or "female"
        age: User's age
        custom_calorie_goal: Override calorie goal if set

    Returns:
        Dict with all goal context:
        - goal: str (goal key)
        - goal_display_name: str (e.g., "Weight Loss")
        - goal_emoji: str (e.g., "🏃")
        - primary_nutrient: str (e.g., "protein" or "folate")
        - primary_nutrient_emoji: str (e.g., "💪")
        - priority_nutrients: List[str] (6-8 nutrients)
        - priority_rdvs: Dict[str, NutrientRDV]
        - nutrient_emojis: Dict[str, str] (emoji for each priority nutrient)
    """
    # Get goal metadata
    metadata = GOAL_METADATA.get(goal, GOAL_METADATA["general_wellness"])

    # Get priority nutrients and RDVs
    priority_nutrients = get_priority_nutrients(goal)
    priority_rdvs = get_priority_rdvs(goal, gender, age, custom_calorie_goal)

    # Build nutrient emoji map for priority nutrients
    nutrient_emojis = {
        nutrient: get_nutrient_emoji(nutrient)
        for nutrient in priority_nutrients
    }

    # Primary nutrient info
    primary_nutrient = metadata.get("primary_nutrient", "protein")

    return {
        "goal": goal,
        "goal_display_name": metadata.get("display_name", goal.replace("_", " ").title()),
        "goal_emoji": metadata.get("emoji", "🎯"),
        "goal_description": metadata.get("description", ""),
        "primary_nutrient": primary_nutrient,
        "primary_nutrient_emoji": get_nutrient_emoji(primary_nutrient),
        "priority_nutrients": priority_nutrients,
        "priority_rdvs": priority_rdvs,
        "nutrient_emojis": nutrient_emojis,
    }


# =============================================================================
# CLI Testing
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("GOAL-DRIVEN NUTRIENT PRIORITY SERVICE")
    print("=" * 60)

    # Test each goal
    for goal in GOAL_NUTRIENT_PRIORITIES:
        nutrients = get_priority_nutrients(goal)
        print(f"\n{goal.upper()} ({len(nutrients)} nutrients):")
        print(f"  {', '.join(nutrients)}")

    # Test personalized RDVs
    print("\n" + "=" * 60)
    print("PERSONALIZED RDVs - Female, 28yo, lose_weight")
    print("=" * 60)

    rdvs = get_priority_rdvs("lose_weight", gender="female", age=28)
    for nutrient, rdv in rdvs.items():
        print(f"  {rdv.display_name}: {rdv.amount} {rdv.unit}")

    # Test percentage calculation
    print("\n" + "=" * 60)
    print("RDV PERCENTAGES - Sample meal logged")
    print("=" * 60)

    consumed = {
        "calories": 1200,
        "protein": 45,
        "fiber": 15,
        "carbohydrates": 150,
        "fat": 40,
        "sodium": 1800,
    }

    percentages = calculate_rdv_percentages(consumed, "lose_weight", "female", 28)
    for nutrient, pct in percentages.items():
        print(f"  {nutrient}: {pct}%")

    print("\nService test complete!")

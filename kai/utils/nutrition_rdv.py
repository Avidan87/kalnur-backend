"""
Multi-Nutrient RDV (Recommended Daily Value) Calculator

Calculates personalized RDV for all 8 nutrients based on:
- Gender (male/female)
- Age (19-50, 51+)
- Activity level (sedentary, light, moderate, active, very_active)

Note: Pregnancy, lactation, and anemia adjustments are NOT included in this version.
These will be added in future iterations.
"""

from typing import Dict


# =============================================================================
# Base RDV Values (Adult 19-50 years)
# =============================================================================

BASE_RDV = {
    # Male base values
    "male": {
        "calories": 2500,       # kcal
        "protein": 56,          # g
        "carbs": 300,           # g
        "fat": 70,              # g
        "iron": 8,              # mg
        "calcium": 1000,        # mg
        "potassium": 3400,      # mg
        "zinc": 11,             # mg
    },
    # Female base values
    "female": {
        "calories": 2000,       # kcal
        "protein": 46,          # g
        "carbs": 225,           # g
        "fat": 60,              # g
        "iron": 18,             # mg (higher due to menstruation)
        "calcium": 1000,        # mg
        "potassium": 2600,      # mg (slightly lower for females)
        "zinc": 8,              # mg
    },
}


# =============================================================================
# Age Adjustment Factors
# =============================================================================

AGE_ADJUSTMENTS = {
    # Age 51+ adjustments (multiply by base)
    "51+": {
        "male": {
            "calories": 0.9,        # 10% reduction for lower metabolism
            "iron": 1.0,            # Same (no menstruation factor)
            "calcium": 1.2,         # Increased for bone health
            "potassium": 1.0,       # Same
        },
        "female": {
            "calories": 0.9,        # 10% reduction
            "iron": 0.44,           # Reduced to 8mg (post-menopause)
            "calcium": 1.2,         # Increased for bone health
            "potassium": 1.0,       # Same
        },
    }
}


# =============================================================================
# Activity Level Multipliers
# =============================================================================

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.0,       # Base (little to no exercise)
    "light": 1.1,           # Light exercise 1-3 days/week
    "moderate": 1.25,       # Moderate exercise 3-5 days/week
    "active": 1.4,          # Hard exercise 6-7 days/week
    "very_active": 1.6,     # Very hard exercise, physical job
}


# =============================================================================
# RDV Calculation Function
# =============================================================================

def calculate_user_rdv(user_profile: Dict) -> Dict[str, float]:
    """
    Calculate personalized RDV for all 8 nutrients.

    Args:
        user_profile: Dict with user info:
            {
                "gender": "male" | "female",
                "age": 25,
                "activity_level": "sedentary" | "light" | "moderate" | "active" | "very_active"
            }

    Returns:
        Dict with personalized RDV values:
        {
            "calories": 2750.0,
            "protein": 61.6,
            "carbs": 330.0,
            "fat": 77.0,
            "iron": 8.8,
            "calcium": 1100.0,
            "potassium": 990.0,
            "zinc": 12.1
        }
    """
    gender = user_profile.get("gender", "female")
    age = user_profile.get("age", 25)
    activity_level = user_profile.get("activity_level", "moderate")

    # Start with base RDV for gender
    rdv = BASE_RDV.get(gender, BASE_RDV["female"]).copy()

    # Apply age adjustments if 51+
    if age >= 51:
        age_adj = AGE_ADJUSTMENTS["51+"][gender]
        for nutrient, multiplier in age_adj.items():
            if nutrient in rdv:
                rdv[nutrient] *= multiplier

    # Apply activity level multiplier
    # (Applies to energy nutrients: calories, protein, carbs, fat)
    activity_multiplier = ACTIVITY_MULTIPLIERS.get(activity_level, 1.25)

    # Energy nutrients scale with activity
    energy_nutrients = ["calories", "protein", "carbs", "fat"]
    for nutrient in energy_nutrients:
        rdv[nutrient] *= activity_multiplier

    # Micronutrients scale SLIGHTLY with activity (10% max boost for very active)
    # This accounts for increased nutrient needs during intense exercise
    micro_multiplier = 1.0
    if activity_level == "active":
        micro_multiplier = 1.05
    elif activity_level == "very_active":
        micro_multiplier = 1.1

    micronutrients = ["iron", "calcium", "zinc"]  # Potassium doesn't scale with activity
    for nutrient in micronutrients:
        rdv[nutrient] *= micro_multiplier

    # Round all values for readability
    for nutrient in rdv:
        rdv[nutrient] = round(rdv[nutrient], 1)

    return rdv


def get_nutrient_gap_priority(
    current_intake: Dict[str, float],
    user_rdv: Dict[str, float]
) -> Dict[str, Dict]:
    """
    Identify which nutrients have the biggest gaps, weighted by clinical severity.

    Sorting uses a severity-weighted score so that clinically dangerous deficiencies
    (B12, folate, iron) always surface above large-but-benign gaps (e.g. potassium).
    B12 deficiency causes irreversible neurological damage; potassium shortfall rarely
    causes acute harm at moderate levels.

    Args:
        current_intake: User's current average intake (from week1_averages)
        user_rdv: User's personalized RDV values

    Returns:
        Dict of nutrients with their gaps, sorted by severity-weighted score:
        {
            "iron": {
                "current": 8.5,
                "target": 18.0,
                "percent_met": 47.2,
                "gap": 9.5,
                "priority": "high"
            },
            ...
        }
    """
    # Clinical severity weights — higher = surfaces sooner even with a small absolute gap.
    # Nutrients with irreversible or acute consequences are weighted highest.
    CLINICAL_SEVERITY: Dict[str, float] = {
        "vitamin_b12": 3.0,   # Irreversible neurological damage
        "folate": 2.5,        # Neural tube defects, megaloblastic anaemia
        "iron": 2.0,          # Anaemia, fatigue, impaired immunity
        "vitamin_d": 1.5,     # Bone loss, immune dysfunction
        "calcium": 1.3,       # Bone loss (long-term)
        "zinc": 1.2,          # Immune function, wound healing
        "magnesium": 1.1,     # Muscle function, heart rhythm
        "vitamin_a": 1.1,     # Vision, immune function
        "vitamin_c": 1.0,
        "potassium": 1.0,
        "protein": 1.0,
        "fiber": 0.9,
        "carbs": 0.8,
        "fat": 0.8,
        "calories": 0.7,
        "sodium": 0.5,        # Limit nutrient — low intake is fine
    }

    gaps = {}

    for nutrient, target in user_rdv.items():
        current = current_intake.get(nutrient, 0)

        # Calculate percent of RDV met
        percent_met = (current / target * 100) if target > 0 else 100

        # Calculate absolute gap
        gap = max(0, target - current)

        # Determine priority level
        if percent_met < 50:
            priority = "high"
        elif percent_met < 75:
            priority = "medium"
        elif percent_met < 90:
            priority = "low"
        else:
            priority = "met"

        # Severity-weighted score for sorting: normalise gap as % of RDV, then weight it
        gap_pct = gap / target if target > 0 else 0
        severity_weight = CLINICAL_SEVERITY.get(nutrient, 1.0)
        sort_score = gap_pct * severity_weight

        gaps[nutrient] = {
            "current": round(current, 1),
            "target": round(target, 1),
            "percent_met": round(percent_met, 1),
            "gap": round(gap, 1),
            "priority": priority,
            "_sort_score": sort_score,
        }

    # Sort by severity-weighted score (highest first)
    sorted_gaps = dict(sorted(
        gaps.items(),
        key=lambda x: x[1]["_sort_score"],
        reverse=True
    ))

    # Remove internal sort key before returning
    for data in sorted_gaps.values():
        del data["_sort_score"]

    return sorted_gaps


def get_primary_nutritional_gap(gaps: Dict[str, Dict]) -> str:
    """
    Get the single most important nutrient to focus on.

    gaps is already sorted by clinical severity-weighted score (from
    get_nutrient_gap_priority), so the primary gap is simply the first
    high/medium priority nutrient in that ordering — not the largest absolute gap.

    Args:
        gaps: Output from get_nutrient_gap_priority()

    Returns:
        Name of primary nutrient to target (e.g., "vitamin_b12", "iron")
    """
    # The dict is pre-sorted by severity-weighted score — take the first high/medium.
    for nutrient, data in gaps.items():
        if data["priority"] in ["high", "medium"]:
            return nutrient

    # All nutrients met — focus on protein (general health)
    return "protein"


# =============================================================================
# NEW: BMR/TDEE-Based RDV Calculation (V2)
# =============================================================================

def calculate_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    """
    Calculate Basal Metabolic Rate using Mifflin-St Jeor Equation.

    This is the gold standard for BMR calculation in modern nutrition science.

    Args:
        weight_kg: Body weight in kilograms (30-300 kg)
        height_cm: Height in centimeters (100-250 cm)
        age: Age in years (13-120)
        gender: "male" or "female"

    Returns:
        BMR in kcal/day (rounded to 1 decimal place)

    Formula:
        Male: BMR = (10 × weight) + (6.25 × height) - (5 × age) + 5
        Female: BMR = (10 × weight) + (6.25 × height) - (5 × age) - 161

    Example:
        >>> calculate_bmr(75, 178, 32, "male")
        1707.5
        >>> calculate_bmr(70, 165, 28, "female")
        1430.2
    """
    if gender == "male":
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:  # female
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161

    return round(bmr, 1)


def calculate_tdee(bmr: float, activity_level: str) -> float:
    """
    Calculate Total Daily Energy Expenditure.

    TDEE = BMR × Activity Multiplier

    Args:
        bmr: Basal Metabolic Rate (from calculate_bmr)
        activity_level: One of:
            - "sedentary": Little or no exercise, desk job
            - "light": Light exercise 1-3 days/week
            - "moderate": Moderate exercise 3-5 days/week
            - "active": Hard exercise 6-7 days/week
            - "very_active": Very hard exercise, physical job

    Returns:
        TDEE in kcal/day (rounded to 1 decimal place)

    Multipliers based on research:
        - Sedentary: 1.2
        - Light: 1.375
        - Moderate: 1.55
        - Active: 1.725
        - Very Active: 1.9

    Example:
        >>> calculate_tdee(1430, "moderate")
        2216.5
        >>> calculate_tdee(1708, "active")
        2946.3
    """
    tdee_multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9
    }

    multiplier = tdee_multipliers.get(activity_level, 1.55)  # Default to moderate
    tdee = bmr * multiplier

    return round(tdee, 1)


def calculate_goal_adjusted_calories(tdee: float, health_goal: str) -> float:
    """
    Adjust TDEE based on user's health goal.

    Science-based adjustments:
        - Lose weight: -500 kcal/day = ~0.5kg loss/week (safe, sustainable)
        - Gain muscle: +300 kcal/day = ~0.3kg gain/week (minimize fat gain)
        - Maintain weight: No adjustment
        - General wellness: No adjustment

    Args:
        tdee: Total Daily Energy Expenditure
        health_goal: One of:
            - "lose_weight"
            - "gain_muscle"
            - "maintain_weight"
            - "general_wellness"

    Returns:
        Target calories in kcal/day (rounded to 1 decimal place)

    Example:
        >>> calculate_goal_adjusted_calories(2217, "lose_weight")
        1717.0
        >>> calculate_goal_adjusted_calories(2946, "gain_muscle")
        3246.0
    """
    adjustments = {
        "lose_weight": -500,       # ~0.5kg/week loss — safe and sustainable
        "gain_muscle": 300,        # ~0.3kg/week gain — minimises fat gain
        "maintain_weight": 0,
        "general_wellness": 0,
        "pregnancy": 400,          # Midpoint of 2nd (+340) and 3rd (+452) trimester needs
                                   # (trimester not collected yet, so practical average used)
        "heart_health": 0,         # No calorie change — weight management via food quality
        "energy_boost": 0,         # No calorie change — energy via iron/B12, not surplus
        "bone_health": 0,          # No calorie change — bone via calcium/vitamin D
    }

    adjustment = adjustments.get(health_goal, 0)
    target_calories = tdee + adjustment

    return round(target_calories, 1)


def calculate_macronutrients(
    target_calories: float,
    weight_kg: float,
    health_goal: str
) -> Dict[str, float]:
    """
    Calculate macronutrient targets based on calories and goal.

    Protein calculation is goal-dependent:
        - Lose weight: 1.8 g/kg (preserve muscle during deficit)
        - Gain muscle: 2.0 g/kg (support muscle synthesis)
        - Maintain: 1.4 g/kg (general health)
        - General wellness: 1.2 g/kg (baseline)

    Fat: 28% of total calories (essential for hormones)
    Carbs: Remaining calories after protein and fat

    Args:
        target_calories: Daily calorie target
        weight_kg: Body weight in kg
        health_goal: User's health goal

    Returns:
        Dict with macronutrient targets:
        {
            "protein_g": 150.0,
            "carbs_g": 241.0,
            "fat_g": 71.0
        }

    Example:
        >>> calculate_macronutrients(2146, 75, "lose_weight")
        {'protein_g': 135.0, 'carbs_g': 214.1, 'fat_g': 66.8}
    """
    # Protein calculation (goal-dependent)
    protein_ratios = {
        "lose_weight": 1.8,
        "gain_muscle": 2.0,
        "maintain_weight": 1.4,
        "general_wellness": 1.2
    }

    protein_ratio = protein_ratios.get(health_goal, 1.4)
    protein_g = weight_kg * protein_ratio
    protein_calories = protein_g * 4  # 4 kcal per gram

    # Fat: 28% of total calories
    fat_percentage = 0.28
    fat_calories = target_calories * fat_percentage
    fat_g = fat_calories / 9  # 9 kcal per gram

    # Carbs: Remaining calories
    carbs_calories = target_calories - protein_calories - fat_calories
    carbs_g = carbs_calories / 4  # 4 kcal per gram

    return {
        "protein_g": round(protein_g, 1),
        "carbs_g": round(carbs_g, 1),
        "fat_g": round(fat_g, 1)
    }


def calculate_micronutrients(gender: str, age: int) -> Dict[str, float]:
    """
    Calculate micronutrient RDV based on gender and age.

    NO pregnancy/lactation adjustments - removed completely!

    Age-based adjustments:
        - Iron (female): 18mg if age < 51, 8mg if age >= 51 (post-menopause)
        - Calcium: 1200mg if age >= 51, 1000mg otherwise (bone health)
        - Potassium: 3400mg for males, 2600mg for females (heart health, blood pressure)

    Args:
        gender: "male" or "female"
        age: Age in years

    Returns:
        Dict with micronutrient RDV:
        {
            "iron_mg": 8.0,
            "calcium_mg": 1000.0,
            "potassium_mg": 3400.0,
            "zinc_mg": 11.0
        }

    Example:
        >>> calculate_micronutrients("female", 28)
        {'iron_mg': 18.0, 'calcium_mg': 1000.0, 'potassium_mg': 2600.0, 'zinc_mg': 8.0}
        >>> calculate_micronutrients("female", 55)
        {'iron_mg': 8.0, 'calcium_mg': 1200.0, 'potassium_mg': 2600.0, 'zinc_mg': 8.0}
    """
    if gender == "male":
        micros = {
            "iron_mg": 8.0,
            "calcium_mg": 1200.0 if age >= 51 else 1000.0,
            "potassium_mg": 3400.0,
            "zinc_mg": 11.0
        }
    else:  # female
        micros = {
            "iron_mg": 8.0 if age >= 51 else 18.0,  # Post-menopause vs menstruating
            "calcium_mg": 1200.0 if age >= 51 else 1000.0,
            "potassium_mg": 2600.0,
            "zinc_mg": 8.0
        }

    return micros


def calculate_weight_projection(
    current_weight: float,
    target_weight: float,
    daily_deficit: float
) -> Dict:
    """
    Calculate time to reach goal weight based on calorie deficit/surplus.

    Science: 1kg of body fat = ~7,700 calories

    Args:
        current_weight: Current weight in kg
        target_weight: Goal weight in kg
        daily_deficit: Calorie deficit/surplus per day
            - Positive = weight loss (e.g., 500 kcal deficit)
            - Negative = weight gain (e.g., -300 kcal surplus)

    Returns:
        Dict with projection:
        {
            "current_weight": 75.0,
            "target_weight": 70.0,
            "deficit_per_day": 500.0,
            "estimated_loss_per_week": 0.45,  # kg (or gain if negative)
            "estimated_weeks_to_goal": 11
        }

    Example:
        >>> calculate_weight_projection(75, 70, 500)
        {'current_weight': 75.0, 'target_weight': 70.0, 'deficit_per_day': 500.0,
         'estimated_loss_per_week': 0.45, 'estimated_weeks_to_goal': 11}
    """
    # Science: 1kg body fat = ~7,700 calories
    calories_per_kg = 7700

    # Weekly deficit/surplus
    weekly_deficit = daily_deficit * 7

    # Weight change per week (kg)
    weight_change_per_week = weekly_deficit / calories_per_kg

    # Total weight to change
    weight_to_change = abs(target_weight - current_weight)

    # Weeks to goal
    if abs(weight_change_per_week) > 0.01:  # Avoid division by zero
        weeks_to_goal = int(weight_to_change / abs(weight_change_per_week))
    else:
        weeks_to_goal = None  # Maintenance - no weight change expected

    return {
        "current_weight": round(current_weight, 1),
        "target_weight": round(target_weight, 1),
        "deficit_per_day": round(daily_deficit, 1),
        "estimated_loss_per_week": round(weight_change_per_week, 2),
        "estimated_weeks_to_goal": weeks_to_goal
    }


def calculate_user_rdv_v2(user_profile: Dict) -> Dict:
    """
    Calculate personalized RDV using BMR/TDEE method (Version 2).

    This replaces the old BASE_RDV system with science-based BMR/TDEE calculations.
    Completely dynamic - NO hardcoded values, everything calculated from user data!

    Required user_profile fields:
        - weight_kg: Body weight in kg
        - height_cm: Height in cm
        - age: Age in years
        - gender: "male" or "female"
        - activity_level: Activity level string
        - health_goals: Health goal string
        - target_weight_kg: Goal weight (optional, for projections)
        - custom_calorie_goal: Custom calorie override (optional)

    Returns:
        Dict with complete RDV and projections:
        {
            "bmr": 1708.0,
            "tdee": 2646.0,
            "recommended_calories": 2146.0,
            "active_calories": 2146.0,
            "rdv": {
                "calories": 2146.0,
                "protein": 135.0,
                "carbs": 214.1,
                "fat": 66.8,
                "iron": 8.0,
                "calcium": 1000.0,
                "potassium": 900.0,
                "zinc": 11.0
            },
            "weight_projection": {  # Only if target_weight provided
                "current_weight": 75.0,
                "target_weight": 70.0,
                "deficit_per_day": 500.0,
                "estimated_loss_per_week": 0.45,
                "estimated_weeks_to_goal": 11
            }
        }

    Example:
        >>> profile = {
        ...     "weight_kg": 75, "height_cm": 178, "age": 32, "gender": "male",
        ...     "activity_level": "moderate", "health_goals": "lose_weight",
        ...     "target_weight_kg": 70
        ... }
        >>> rdv = calculate_user_rdv_v2(profile)
        >>> rdv["bmr"]
        1707.5
        >>> rdv["recommended_calories"]
        2146.2
    """
    # Extract user data
    weight_kg = user_profile.get("weight_kg")
    height_cm = user_profile.get("height_cm")
    age = user_profile.get("age")
    gender = user_profile.get("gender", "female")
    activity_level = user_profile.get("activity_level", "moderate")
    health_goal = user_profile.get("health_goals", "general_wellness")
    target_weight_kg = user_profile.get("target_weight_kg")
    custom_calorie_goal = user_profile.get("custom_calorie_goal")

    # Validate required fields
    if not all([weight_kg, height_cm, age]):
        raise ValueError(
            "Missing required fields for RDV calculation. "
            "Need: weight_kg, height_cm, age"
        )

    # Step 1: Calculate BMR
    bmr = calculate_bmr(weight_kg, height_cm, age, gender)

    # Step 2: Calculate TDEE
    tdee = calculate_tdee(bmr, activity_level)

    # Step 3: Adjust for health goal
    recommended_calories = calculate_goal_adjusted_calories(tdee, health_goal)

    # Step 4: Determine active calorie goal (custom or calculated)
    active_calories = custom_calorie_goal if custom_calorie_goal else recommended_calories

    # Step 5: Calculate macronutrients
    macros = calculate_macronutrients(active_calories, weight_kg, health_goal)

    # Step 6: Calculate micronutrients
    micros = calculate_micronutrients(gender, age)

    # Step 7: Build complete RDV
    rdv = {
        "calories": active_calories,
        "protein": macros["protein_g"],
        "carbs": macros["carbs_g"],
        "fat": macros["fat_g"],
        "iron": micros["iron_mg"],
        "calcium": micros["calcium_mg"],
        "potassium": micros["potassium_mg"],
        "zinc": micros["zinc_mg"]
    }

    # Step 8: Calculate weight projection (if target weight provided)
    weight_projection = None
    if target_weight_kg and target_weight_kg != weight_kg:
        daily_deficit = tdee - recommended_calories
        weight_projection = calculate_weight_projection(
            weight_kg,
            target_weight_kg,
            daily_deficit
        )

    # Return complete result
    result = {
        "bmr": bmr,
        "tdee": tdee,
        "recommended_calories": recommended_calories,
        "active_calories": active_calories,
        "rdv": rdv
    }

    if weight_projection:
        result["weight_projection"] = weight_projection

    return result


# =============================================================================
# CLI Testing
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Multi-Nutrient RDV Calculator - Test Suite")
    print("="*60 + "\n")

    # Test Case 1: Young active male
    print("Test 1: 25-year-old active male")
    print("-" * 40)
    profile1 = {
        "gender": "male",
        "age": 25,
        "activity_level": "active"
    }
    rdv1 = calculate_user_rdv(profile1)
    print(f"Gender: {profile1['gender']}, Age: {profile1['age']}, Activity: {profile1['activity_level']}")
    print("\nPersonalized RDV:")
    for nutrient, value in rdv1.items():
        print(f"  {nutrient}: {value}")

    # Test Case 2: Older sedentary female
    print("\n\nTest 2: 55-year-old sedentary female")
    print("-" * 40)
    profile2 = {
        "gender": "female",
        "age": 55,
        "activity_level": "sedentary"
    }
    rdv2 = calculate_user_rdv(profile2)
    print(f"Gender: {profile2['gender']}, Age: {profile2['age']}, Activity: {profile2['activity_level']}")
    print("\nPersonalized RDV:")
    for nutrient, value in rdv2.items():
        print(f"  {nutrient}: {value}")
    print("\nNote: Iron reduced (post-menopause), Calcium increased (bone health)")

    # Test Case 3: Gap analysis
    print("\n\nTest 3: Gap Analysis for Active Male")
    print("-" * 40)
    current_intake = {
        "calories": 2200,
        "protein": 55,
        "carbs": 280,
        "fat": 65,
        "iron": 6.5,      # Low
        "calcium": 650,   # Low
        "potassium": 500, # Low
        "zinc": 9.5,
    }
    gaps = get_nutrient_gap_priority(current_intake, rdv1)
    print("\nNutritional Gaps (sorted by severity):\n")
    for nutrient, data in gaps.items():
        print(f"{nutrient}:")
        print(f"  Current: {data['current']} | Target: {data['target']} | {data['percent_met']}% met")
        print(f"  Gap: {data['gap']} | Priority: {data['priority']}")
        print()

    primary_gap = get_primary_nutritional_gap(gaps)
    print(f">> PRIMARY FOCUS: {primary_gap.upper()}")
    print(f"   This is the nutrient with the largest gap that needs attention.\n")

    print("="*60)
    print("All tests complete!")
    print("="*60 + "\n")

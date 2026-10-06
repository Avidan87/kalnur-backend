"""
Pydantic Models for Agent Communication

Defines the data structures used for inter-agent communication in the KAI system.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Request Models
# ============================================================================

class ChatMessage(BaseModel):
    """Single message in conversation history"""
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Chat request - user_id extracted from JWT token"""
    message: str
    conversation_history: List[ChatMessage] = Field(
        default_factory=list,
        description="Previous messages for context (optional)"
    )
    language: str = Field(
        default="en",
        description="Language mode for Kally's responses (e.g. 'en', 'pidgin')"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "What foods are high in iron?",
                "conversation_history": []
            }
        }
    )


class NutritionQueryRequest(BaseModel):
    """Specific nutrition information query"""
    user_id: str
    query: str
    food_name: Optional[str] = None


# ============================================================================
# Response Models
# ============================================================================

class ChatResponse(BaseModel):
    """Chat response from KAI"""
    success: bool
    message: str
    suggestions: List[str] = Field(default_factory=list)
    processing_time_ms: int = 0


# ============================================================================
# Triage Agent Models
# ============================================================================

class TriageResult(BaseModel):
    """Result from Triage Agent routing decision"""
    workflow: Literal["food_logging", "nutrition_query", "health_coaching", "general_chat"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    requires_vision: bool = False
    requires_knowledge_base: bool = False
    requires_web_search: bool = False
    extracted_food_names: List[str] = Field(default_factory=list)


# ============================================================================
# Vision Agent Models
# ============================================================================

class DetectedFood(BaseModel):
    """Single detected food item from image"""
    name: str
    nigerian_name: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_portion: str
    estimated_grams: float
    visible_ingredients: List[str] = Field(default_factory=list)
    cooking_method: Optional[str] = None
    # Oil detection fields for one-pot dishes
    oil_sheen_visible: Optional[bool] = None
    oil_amount_estimate: Optional[str] = None  # "none", "light", "moderate", "heavy"
    # Item count for discrete/countable foods (bread slices, eggs, pieces, balls, etc.)
    item_count: Optional[int] = None


class VisionResult(BaseModel):
    """Result from Vision Agent analysis"""
    detected_foods: List[DetectedFood]
    meal_context: str
    cooking_method: Optional[str] = None
    overall_confidence: float = Field(ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_questions: List[str] = Field(default_factory=list)
    image_quality_issue: bool = False
    depth_estimation_used: bool  # True if depth estimation MCP was used, False if fallback was used


# ============================================================================
# Knowledge Agent Models
# ============================================================================

class NutrientInfo(BaseModel):
    """Nutrient information per 100g - 16 nutrients total"""
    # Macros (5)
    calories: float
    protein: float
    carbohydrates: float
    fat: float
    fiber: float = 0.0
    # Minerals (6)
    iron: float
    calcium: float
    zinc: float
    potassium: float
    sodium: float = 0.0
    magnesium: float = 0.0
    # Vitamins (5)
    vitamin_a: float = 0.0      # mcg RAE
    vitamin_c: float = 0.0      # mg
    vitamin_d: float = 0.0      # mcg
    vitamin_b12: float = 0.0    # mcg
    folate: float = 0.0         # mcg DFE


class FoodNutritionData(BaseModel):
    """Complete nutrition data for a food item"""
    food_id: str
    name: str
    category: str
    portion_consumed_grams: float
    nutrients_per_100g: NutrientInfo
    total_nutrients: NutrientInfo  # Calculated for actual portion
    health_benefits: List[str] = Field(default_factory=list)
    cultural_significance: str = ""
    common_pairings: List[str] = Field(default_factory=list)
    dietary_flags: List[str] = Field(default_factory=list)
    price_tier: str = "mid"
    similarity_score: float = 1.0


class KnowledgeResult(BaseModel):
    """Result from Knowledge Agent RAG lookup"""
    foods: List[FoodNutritionData]
    # ALL 16 NUTRIENTS - KAI tracks complete nutrition profile
    # Macros (5)
    total_calories: float
    total_protein: float
    total_carbohydrates: float
    total_fat: float
    total_fiber: float = 0.0
    # Minerals (6)
    total_iron: float
    total_calcium: float
    total_zinc: float
    total_potassium: float
    total_sodium: float = 0.0
    total_magnesium: float = 0.0
    # Vitamins (5)
    total_vitamin_a: float = 0.0
    total_vitamin_c: float = 0.0
    total_vitamin_d: float = 0.0
    total_vitamin_b12: float = 0.0
    total_folate: float = 0.0
    query_interpretation: str
    sources_used: List[str] = Field(default_factory=list)


# ============================================================================
# Coaching Agent Models
# ============================================================================

class NutrientInsight(BaseModel):
    """Insight about a specific nutrient"""
    nutrient: str
    current_value: float
    recommended_daily_value: float
    percentage_met: float
    status: Literal["deficient", "adequate", "optimal", "excessive"]
    advice: str


class MealSuggestion(BaseModel):
    """Personalized meal suggestion"""
    meal_name: str
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    ingredients: List[str]
    estimated_cost: str
    key_nutrients: Dict[str, float]
    why_recommended: str


class NextMealCombo(BaseModel):
    """Nigerian meal combo suggestion from GPT-4o"""
    combo: str  # e.g., "Ugu soup (300g) + Grilled fish (150g) + small Eba (100g)"
    why: str  # Why this combo helps (closes gap, fits goal)


class GoalProgress(BaseModel):
    """User's progress toward their health goal"""
    type: str  # User's health goal (e.g., "lose_weight", "gain_muscle", "pregnancy")
    status: Literal["excellent", "on_track", "needs_attention"]
    message: str  # Progress message (e.g., "You're at 1650/1800 cal today - stay disciplined!")


class CoachingResult(BaseModel):
    """Result from Coaching Agent - Goal-Aligned with Nigerian Meal Combos"""
    message: str  # Honest, concise assessment (2-3 sentences)
    next_meal_combo: NextMealCombo  # Nigerian meal combo from GPT-4o
    goal_progress: GoalProgress  # Progress toward user's health goal


# ============================================================================
# Final Response Models
# ============================================================================

class FoodLoggingResponse(BaseModel):
    """Response for food logging - lean, goal-driven nutrient tracking"""
    success: bool
    message: str
    detected_foods: List[DetectedFood] = Field(default_factory=list)
    # Goal-driven: only priority nutrients for this user's goal (6-8 nutrients)
    priority_nutrients: Dict[str, float] = Field(default_factory=dict)
    meal_id: Optional[str] = None
    # Smart meal title generated by Kally (e.g. "Jollof Rice with Chicken")
    meal_title: Optional[str] = None
    # Dynamic notification message — Kally writes this based on meal + 7-day patterns
    # Used by the native offline queue background sync to personalise the push notification
    notification_message: Optional[str] = None
    processing_time_ms: int = 0


# ============================================================================
# Endpoint Models
# ============================================================================

class LogMealRequest(BaseModel):
    """Request to save meal to database (user_id extracted from JWT token)"""
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    foods: List[Dict[str, Any]]  # Food objects with nutrition
    meal_date: Optional[str] = None  # ISO YYYY-MM-DD
    image_url: Optional[str] = None
    user_description: Optional[str] = None


class LogMealResponse(BaseModel):
    """Response from saving meal"""
    success: bool
    message: str
    meal_id: str
    meal_date: str
    meal_time: str
    foods_count: int
    totals: Dict[str, float]
    daily_totals: Optional[Dict[str, Any]] = None
    processing_time_ms: int = 0


class MealHistoryResponse(BaseModel):
    """Response with user's meal history"""
    success: bool
    message: str
    meals: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int
    processing_time_ms: int = 0


class UserProfileResponse(BaseModel):
    """
    Response with user profile.

    NEW: Removed pregnancy/lactation/anemia fields completely!
    Added: profile_complete flag and new calorie goal fields
    """
    success: bool
    message: str
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    gender: str
    age: int
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    activity_level: Optional[str] = None
    health_goals: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    target_weight_kg: Optional[float] = None
    calculated_calorie_goal: Optional[float] = None
    custom_calorie_goal: Optional[float] = None
    active_calorie_goal: Optional[float] = None
    profile_complete: bool = False
    coaching_complete: bool = False
    rdv: Dict[str, float] = Field(default_factory=dict)
    processing_time_ms: int = 0


class UpdateUserProfileRequest(BaseModel):
    """
    Request to update user profile.

    NEW: Removed pregnancy/lactation/anemia fields!
    Use /api/v1/users/health-profile endpoint for complete health profile updates.
    """
    email: Optional[str] = None
    name: Optional[str] = None
    gender: Optional[Literal["male", "female"]] = None
    age: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    activity_level: Optional[
        Literal["sedentary", "light", "moderate", "active", "very_active"]
    ] = None
    health_goals: Optional[
        Literal["lose_weight", "gain_muscle", "maintain_weight", "general_wellness"]
    ] = None
    dietary_restrictions: Optional[str] = None


class UserStatsResponse(BaseModel):
    """Response with user daily stats"""
    success: bool
    message: str
    user_id: str
    date: str
    daily_totals: Optional[Dict[str, Any]] = None
    rdv_percentages: Dict[str, float] = Field(default_factory=dict)
    meal_count: int = 0
    current_logging_streak: int = 0
    longest_logging_streak: int = 0
    processing_time_ms: int = 0


# ============================================================================
# Agent Context (shared state between agents)
# ============================================================================

class AgentContext(BaseModel):
    """Shared context passed between agents in a workflow"""
    request_id: str
    user_id: str
    workflow: str
    triage_result: Optional[TriageResult] = None
    vision_result: Optional[VisionResult] = None
    knowledge_result: Optional[KnowledgeResult] = None
    coaching_result: Optional[CoachingResult] = None
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    user_nutrition_history: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

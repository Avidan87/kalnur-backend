"""
KAI Models Package

Pydantic models for API requests/responses and agent communication.
"""

from .agent_models import (
    # Request Models
    ChatMessage,
    ChatRequest,
    NutritionQueryRequest,

    # Agent Result Models
    TriageResult,
    DetectedFood,
    VisionResult,
    NutrientInfo,
    FoodNutritionData,
    KnowledgeResult,
    NutrientInsight,
    MealSuggestion,
    CoachingResult,

    # Response Models
    ChatResponse,
    FoodLoggingResponse,

    # Shared Context
    AgentContext,
)

__all__ = [
    # Requests
    "ChatMessage",
    "ChatRequest",
    "NutritionQueryRequest",

    # Agent Results
    "TriageResult",
    "DetectedFood",
    "VisionResult",
    "NutrientInfo",
    "FoodNutritionData",
    "KnowledgeResult",
    "NutrientInsight",
    "MealSuggestion",
    "CoachingResult",

    # Responses
    "ChatResponse",
    "FoodLoggingResponse",

    # Context
    "AgentContext",
]

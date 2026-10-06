"""
KAI Agents Package

Multi-agent system for Nigerian food nutrition tracking.

Agents:
- VisionAgent: Detects Nigerian foods from images
- KnowledgeAgent: Retrieves nutrition data via ChromaDB RAG
- ChatAgent: Handles all conversations (questions, feedback, progress)
- CoachingAgent: Handles one-time user coaching flow + context injection
"""

from .vision_agent import VisionAgent, detect_nigerian_foods
from .knowledge_agent import KnowledgeAgent, retrieve_food_nutrition
from .chat_agent import ChatAgent, get_chat_agent
from .coaching_agent import (
    process_coaching_response,
    get_coaching_system_context,
    get_barrier_nutrient,
    build_welcome_message,
)

__all__ = [
    # Agent Classes
    "VisionAgent",
    "KnowledgeAgent",
    "ChatAgent",

    # Convenience Functions
    "detect_nigerian_foods",
    "retrieve_food_nutrition",
    "get_chat_agent",

    # Coaching Functions
    "process_coaching_response",
    "get_coaching_system_context",
    "get_barrier_nutrient",
    "build_welcome_message",
]

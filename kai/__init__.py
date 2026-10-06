"""
KAI - Nigerian Food Nutrition AI Assistant

Multi-agent system for Nigerians' health and nutrition tracking.

Architecture:
- Triage Agent: Routes requests to appropriate workflows
- Vision Agent: Detects Nigerian foods from meal images (GPT-4o)
- Knowledge Agent: Retrieves nutrition data via ChromaDB RAG (GPT-4o-mini)
- Coaching Agent: Provides personalized guidance (GPT-4o + Tavily MCP)

Orchestrator: Coordinates the multi-agent workflow
"""

from kai.orchestrator import handle_user_request, handle_user_request_sync
from kai.food_registry import (
    get_food_registry,
    get_canonical_food_name,
    get_all_food_names,
    is_known_food,
)

__version__ = "0.3.0"

__all__ = [
    "handle_user_request",
    "handle_user_request_sync",
    "get_food_registry",
    "get_canonical_food_name",
    "get_all_food_names",
    "is_known_food",
    "__version__",
]

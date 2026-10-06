"""
Triage Agent - Request Routing and Classification

This agent analyzes incoming requests and determines the appropriate workflow path.
Uses GPT-4o-mini for cost efficiency (~$0.15 per request).

Workflow Routes:
- food_logging: Image-based food detection and nutrition logging
- nutrition_query: Specific questions about Nigerian foods
- health_coaching: Personalized health advice and meal planning
- general_chat: General conversation and greetings
"""

import json
import logging
import asyncio
from typing import Optional
from agents import Agent, Runner
from dotenv import load_dotenv
import os

from kai.models import TriageResult

load_dotenv()
logger = logging.getLogger(__name__)


class TriageAgent:
    """
    Triage Agent for routing user requests to appropriate workflows.

    Uses GPT-4o-mini for fast, cost-effective routing decisions.
    """

    def __init__(self, openai_api_key: Optional[str] = None):
        """Initialize Triage Agent with OpenAI client."""
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.model = "gpt-4o-mini"  # Cost-efficient routing
        self._setup_agent()

    def _setup_agent(self):
        """Create Agents SDK triage agent."""
        instructions = """You are a triage agent for Kalnur, a Nigerian nutrition AI assistant for everyone — men, women, and people of all ages and health goals.

Your job is to analyze user requests and classify them into ONE of these workflows:

1. food_logging — User wants to log food they ate/are eating
   Indicators: image present, phrases like "I ate", "Log this meal", questions about "my plate"

2. nutrition_query — User asks about specific Nigerian foods/nutrition
   Indicators: "How much protein in...", "Is Jollof rice healthy?", comparisons

3. health_coaching — Personalized advice/meal planning
   Indicators: "What should I eat for...", "I need help with...", pregnancy, anemia, weight

4. general_chat — Greetings or off-topic/unclear

Output ONLY valid JSON with this shape:
{
  "workflow": "food_logging|nutrition_query|health_coaching|general_chat",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of decision",
  "requires_vision": true|false,
  "requires_knowledge_base": true|false,
  "requires_web_search": true|false,
  "extracted_food_names": ["food1", "food2"]
}

Rules:
- If has_image=true, strongly prefer food_logging
- Extract Nigerian food names mentioned (e.g., "Jollof rice", "Egusi soup")
- Set requires_knowledge_base=true for nutrition_query and food_logging
- Set requires_web_search=true only for complex health_coaching questions
- Be decisive — confidence > 0.7 for clear requests
"""

        self.agent = Agent(
            name="Kalnur Triage Agent",
            instructions=instructions,
            model=self.model,
        )

    async def analyze_request(
        self,
        user_message: str,
        has_image: bool = False,
        conversation_history: Optional[list] = None
    ) -> TriageResult:
        """
        Analyze user request and determine workflow path.

        Args:
            user_message: User's text message
            has_image: Whether an image is attached
            conversation_history: Previous conversation turns

        Returns:
            TriageResult with workflow decision and metadata
        """

        # Build context from conversation history
        context = ""
        if conversation_history:
            recent_turns = conversation_history[-3:]  # Last 3 turns for context
            context = "Previous conversation:\n"
            for turn in recent_turns:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                context += f"{role}: {content}\n"
            context += "\n"

        # (Instructions are embedded in the Agent; no separate system prompt needed)

        # Build user prompt
        user_prompt = f"""{context}Current message: "{user_message}"
has_image: {has_image}

Classify this request and return JSON."""

        try:
            # Run via Agents SDK
            result = await Runner.run(self.agent, user_prompt)

            # Parse JSON final output
            result_dict = json.loads(result.final_output)

            # Validate and create TriageResult
            triage_result = TriageResult(
                workflow=result_dict["workflow"],
                confidence=result_dict["confidence"],
                reasoning=result_dict["reasoning"],
                requires_vision=result_dict.get("requires_vision", has_image),
                requires_knowledge_base=result_dict.get("requires_knowledge_base", False),
                requires_web_search=result_dict.get("requires_web_search", False),
                extracted_food_names=result_dict.get("extracted_food_names", [])
            )

            logger.info(
                "Triage decision: %s (confidence: %.2f)",
                triage_result.workflow,
                triage_result.confidence,
            )

            return triage_result

        except json.JSONDecodeError as e:
            logger.error("Failed to parse triage result: %s", e)
            # Fallback to general_chat on parse error
            return TriageResult(
                workflow="general_chat",
                confidence=0.5,
                reasoning="Failed to parse triage decision, defaulting to general chat",
                requires_vision=False,
                requires_knowledge_base=False,
                requires_web_search=False
            )
        except Exception as e:
            logger.error("Triage agent error: %s", e, exc_info=True)
            raise


# ============================================================================
# Convenience Functions
# ============================================================================

def route_request(
    user_message: str,
    has_image: bool = False,
    conversation_history: Optional[list] = None,
    openai_api_key: Optional[str] = None
) -> TriageResult:
    """
    Convenience function for single-request routing.

    Args:
        user_message: User's text message
        has_image: Whether an image is attached
        conversation_history: Previous conversation turns
        openai_api_key: Optional API key override

    Returns:
        TriageResult with workflow decision
    """
    agent = TriageAgent(openai_api_key=openai_api_key)
    return asyncio.run(agent.analyze_request(user_message, has_image, conversation_history))


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":

    # Configure logging for testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_triage_agent():
        """Test Triage Agent with various input scenarios."""

        print("\n" + "="*60)
        print("Testing Triage Agent")
        print("="*60 + "\n")

        agent = TriageAgent()

        # Test cases
        test_cases = [
            {
                "name": "Food Logging with Image",
                "message": "I just ate this plate of Jollof rice",
                "has_image": True,
                "expected": "food_logging"
            },
            {
                "name": "Food Logging without Image",
                "message": "Log my breakfast: Akara and pap",
                "has_image": False,
                "expected": "food_logging"
            },
            {
                "name": "Nutrition Query",
                "message": "How much iron is in Egusi soup?",
                "has_image": False,
                "expected": "nutrition_query"
            },
            {
                "name": "Nutrition Comparison",
                "message": "Which is healthier, fufu or eba?",
                "has_image": False,
                "expected": "nutrition_query"
            },
            {
                "name": "Health Coaching",
                "message": "I'm pregnant and need more iron. What should I eat?",
                "has_image": False,
                "expected": "health_coaching"
            },
            {
                "name": "Meal Planning",
                "message": "Suggest a low-cost breakfast for me",
                "has_image": False,
                "expected": "health_coaching"
            },
            {
                "name": "General Greeting",
                "message": "Good morning! How are you?",
                "has_image": False,
                "expected": "general_chat"
            },
            {
                "name": "Ambiguous Question",
                "message": "What's the weather like?",
                "has_image": False,
                "expected": "general_chat"
            }
        ]

        # Run tests
        for i, test in enumerate(test_cases, 1):
            print(f"\n{i}. Test: {test['name']}")
            print(f"   Message: \"{test['message']}\"")
            print(f"   Has Image: {test['has_image']}")
            print(f"   Expected: {test['expected']}")

            result = await agent.analyze_request(
                user_message=test["message"],
                has_image=test["has_image"]
            )

            # Check result
            match = "✓" if result.workflow == test["expected"] else "✗"
            print(f"\n   {match} Result: {result.workflow} (confidence: {result.confidence:.2f})")
            print(f"   Reasoning: {result.reasoning}")
            print(f"   Requires Vision: {result.requires_vision}")
            print(f"   Requires KB: {result.requires_knowledge_base}")
            print(f"   Requires Web: {result.requires_web_search}")
            if result.extracted_food_names:
                print(f"   Extracted Foods: {', '.join(result.extracted_food_names)}")

        print("\n" + "="*60)
        print("Triage Agent Tests Complete!")
        print("="*60 + "\n")

    # Run tests
    asyncio.run(test_triage_agent())

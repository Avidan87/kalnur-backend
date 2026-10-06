"""
Coaching Agent - KAI's User Coaching Flow

Handles the one-time coaching flow for new users:
- Goal-aware questions (barrier, food habits, motivation)
- Collects and saves answers to user_coaching table
- Generates a personalized welcome message
- Provides coaching context for system prompt injection

Triggered ONCE when: coaching_complete = False in user_coaching table.
Never runs again after completion.
"""

import logging
import os
from typing import Dict, Any, Optional
from openai import AsyncOpenAI

from kai.database import (
    get_user_coaching,
    save_user_coaching,
    mark_coaching_complete,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Goal Config
# Lightweight ingredients per goal — used to dynamically build questions.
# Add a new goal here and the question builders handle the rest.
# ============================================================================

GOAL_CONFIG = {
    "lose_weight": {
        "display_name": "weight loss",
        # Q1 — Barrier
        "barrier_context": "Most people have one thing that quietly keeps breaking their eating routine — not laziness, just real life.",
        "barrier_question": "What usually gets in the way of eating well for you?",
        "barrier_chips": ["Cravings", "Too busy", "Portions", "No idea"],
        # Q2 — Food habits
        "habits_context": "Kally works best when she understands how you actually eat — not your ideal version, your real version.",
        "habits_question": "How would you describe your eating day to day?",
        "habits_chips": ["Home cook", "Eat outside", "Skip meals", "Regular meals"],
    },
    "gain_muscle": {
        "display_name": "muscle gain",
        "barrier_context": "Building muscle is mostly a food game — most people struggle not at the gym but at the table.",
        "barrier_question": "What usually gets in the way of eating enough for your goal?",
        "barrier_chips": ["Not enough food", "Low protein", "Slow recovery", "No plan"],
        "habits_context": "Kally needs to know your real eating rhythm — how often, how much, and what you actually reach for.",
        "habits_question": "How would you describe your eating day to day?",
        "habits_chips": ["Home cook", "Eat outside", "Skip meals", "Regular meals"],
    },
    "pregnancy": {
        "display_name": "pregnancy nutrition",
        "barrier_context": "Eating during pregnancy is one of the most confusing things — so much advice, so much going on in your body.",
        "barrier_question": "What has been the most difficult part of eating during your pregnancy?",
        "barrier_chips": ["Food aversions", "Cravings", "Not sure what's safe", "Nausea"],
        "habits_context": "Kally wants to understand what your meals actually look like right now — no judgment, just context.",
        "habits_question": "How would you describe your eating day to day?",
        "habits_chips": ["Home cook", "Eat outside", "Small portions", "Regular meals"],
    },
    "heart_health": {
        "display_name": "heart health",
        "barrier_context": "Changing how you eat for your heart is one of the harder lifestyle shifts — old habits run deep.",
        "barrier_question": "What makes it hardest to eat the way you know you should?",
        "barrier_chips": ["Old habits", "Eating out", "How I cook", "No idea"],
        "habits_context": "Kally needs to understand your real eating patterns — what you cook, what you buy, where you eat.",
        "habits_question": "How would you describe your eating day to day?",
        "habits_chips": ["Home cook", "Eat outside", "Skip meals", "Regular meals"],
    },
    "energy_boost": {
        "display_name": "energy boost",
        "barrier_context": "Low energy is almost always a food timing problem — when and what you eat matters as much as how much.",
        "barrier_question": "When does your energy usually crash during the day?",
        "barrier_chips": ["Morning crash", "After lunch", "Afternoon slump", "All day"],
        "habits_context": "Kally needs to understand your eating rhythm to know where the energy gaps are coming from.",
        "habits_question": "How would you describe your eating day to day?",
        "habits_chips": ["Skip breakfast", "Eat irregularly", "Regular meals", "Eat outside"],
    },
    "bone_health": {
        "display_name": "bone health",
        "barrier_context": "Most people eating for bone health have one obvious gap in their diet — Kally wants to find yours.",
        "barrier_question": "What do you feel is missing most from your diet right now?",
        "barrier_chips": ["Little dairy", "Rare fish", "Few vegetables", "No idea"],
        "habits_context": "Kally works best when she understands your real meals — not what you think you should eat, what you actually eat.",
        "habits_question": "How would you describe your eating day to day?",
        "habits_chips": ["Home cook", "Eat outside", "Skip meals", "Regular meals"],
    },
    "maintain_weight": {
        "display_name": "weight maintenance",
        "barrier_context": "Maintaining weight is actually harder than losing it — life keeps getting in the way of consistency.",
        "barrier_question": "What usually throws your eating off track?",
        "barrier_chips": ["Stress eating", "Busy schedule", "Social eating", "Consistency"],
        "habits_context": "Kally wants to understand your real eating week — the version that actually happens, not the planned one.",
        "habits_question": "How would you describe your eating day to day?",
        "habits_chips": ["Home cook", "Eat outside", "Skip meals", "Regular meals"],
    },
    "general_wellness": {
        "display_name": "general wellness",
        "barrier_context": "Most people have one thing that quietly keeps breaking their eating routine — not laziness, just real life.",
        "barrier_question": "What usually gets in the way of eating well for you?",
        "barrier_chips": ["Cravings", "Too busy", "Consistency", "No idea"],
        "habits_context": "Kally works best when she understands how you actually eat — not your ideal version, your real version.",
        "habits_question": "How would you describe your eating day to day?",
        "habits_chips": ["Home cook", "Eat outside", "Skip meals", "Regular meals"],
    },
    "manage_blood_sugar": {
        "display_name": "blood sugar management",
        "barrier_context": "Most people don't realise their blood sugar is spiking — it happens silently, meal after meal, for years.",
        "barrier_question": "What do you think is your biggest sugar challenge right now?",
        "barrier_chips": ["White rice daily", "Sweet drinks", "Bread & snacks", "No idea"],
        "habits_context": "Blood sugar isn't just about what you eat — when you eat matters just as much. Kally needs to understand your real eating rhythm.",
        "habits_question": "How does your eating day usually look?",
        "habits_chips": ["One big meal", "3 regular meals", "Skip breakfast", "Graze all day"],
    },
}

# Q3 — Favourite meal (same for all goals — always free text, no chips)
FAVOURITE_MEAL_CONTEXT = "Kally will never ask you to give up your favourite food. She works with what you love, not against it."
FAVOURITE_MEAL_QUESTION = "What is your favourite Nigerian meal?"

# Q4 — Motivation (same for all goals)
MOTIVATION_CONTEXT = "There is no wrong answer here — knowing where you are helps Kally coach you at the right pace, not too hard, not too easy."
MOTIVATION_QUESTION = "How committed are you to your {goal_name} goal right now?"
MOTIVATION_CHIPS = ["Starting out", "Getting there", "Very committed", "All in"]
# Chip → numeric score mapping for motivation
MOTIVATION_CHIP_SCORES = {
    "starting out": 3,
    "getting there": 5,
    "very committed": 8,
    "all in": 10,
}


def build_barrier_question(goal: str) -> str:
    """Build the barrier question text block for a given goal."""
    config = GOAL_CONFIG.get(goal, GOAL_CONFIG["general_wellness"])
    return f"{config['barrier_context']}\n\n**{config['barrier_question']}**"


def get_barrier_chips(goal: str) -> list:
    """Return the barrier chip options for a given goal."""
    config = GOAL_CONFIG.get(goal, GOAL_CONFIG["general_wellness"])
    return config["barrier_chips"]


def build_food_habits_question(goal: str) -> str:
    """Build the food habits question text block for a given goal."""
    config = GOAL_CONFIG.get(goal, GOAL_CONFIG["general_wellness"])
    return f"{config['habits_context']}\n\n**{config['habits_question']}**"


def get_habits_chips(goal: str) -> list:
    """Return the food habits chip options for a given goal."""
    config = GOAL_CONFIG.get(goal, GOAL_CONFIG["general_wellness"])
    return config["habits_chips"]


def build_favourite_meal_question() -> str:
    """Build the favourite meal question text block."""
    return f"{FAVOURITE_MEAL_CONTEXT}\n\n**{FAVOURITE_MEAL_QUESTION}**"


def build_motivation_question(goal_name: str) -> str:
    """Build the motivation question text block."""
    question = MOTIVATION_QUESTION.format(goal_name=goal_name)
    return f"{MOTIVATION_CONTEXT}\n\n**{question}**"

def get_goal_display_name(goal: str) -> str:
    """Return the human-readable display name for a health goal."""
    return GOAL_CONFIG.get(goal, GOAL_CONFIG["general_wellness"])["display_name"]

# ============================================================================
# Barrier → Nutrient Mapping
# Maps barrier answers to trackable nutrients for progress detection
# Used by _get_progress_context() to celebrate improvement against barrier
# ============================================================================

BARRIER_NUTRIENT_MAP = {
    "lose_weight": {
        "cravings": "protein",       # High protein = fewer cravings
        "portion": "calories",
        "time": "fiber",
        "default": "calories",
    },
    "gain_muscle": {
        "protein": "protein",
        "eating": "calories",
        "recovery": "magnesium",
        "default": "protein",
    },
    "pregnancy": {
        "default": "folate",
    },
    "heart_health": {
        "salt": "sodium",
        "fried": "fat",
        "default": "sodium",
    },
    "energy_boost": {
        "morning": "iron",
        "afternoon": "iron",
        "after meals": "carbohydrates",
        "default": "iron",
    },
    "bone_health": {
        "dairy": "calcium",
        "fish": "vitamin_d",
        "vegetables": "calcium",
        "default": "calcium",
    },
    "maintain_weight": {
        "stress": "calories",
        "busy": "fiber",
        "social": "calories",
        "default": "calories",
    },
    "general_wellness": {
        "default": "protein",
    },
    "manage_blood_sugar": {
        "white rice": "carbohydrates",
        "sweet drinks": "carbohydrates",
        "bread": "carbohydrates",
        "default": "carbohydrates",
    },
}


def get_barrier_nutrient(health_goal: str, barrier_answer: str) -> str:
    """
    Map a user's barrier answer to a trackable nutrient.
    Used to detect and celebrate improvement against their stated barrier.

    Args:
        health_goal: User's health goal
        barrier_answer: User's raw barrier answer text

    Returns:
        Nutrient name to track for barrier progress
    """
    goal_map = BARRIER_NUTRIENT_MAP.get(health_goal, {})
    barrier_lower = barrier_answer.lower() if barrier_answer else ""

    # Match barrier answer to keyword
    for keyword, nutrient in goal_map.items():
        if keyword != "default" and keyword in barrier_lower:
            return nutrient

    return goal_map.get("default", "calories")


# ============================================================================
# Coaching Flow State Machine
# Tracks which question we're on using the saved coaching data
# ============================================================================

async def get_next_coaching_step(user_id: str) -> Dict[str, Any]:
    """
    Determine what step the user is on in the coaching flow.

    Flow: intro → barrier → food_habits → favourite_meal → motivation → complete

    Returns a dict with:
    - step: "intro" | "barrier" | "food_habits" | "favourite_meal" | "motivation" | "welcome" | "complete"
    """
    coaching = await get_user_coaching(user_id)

    # No coaching record at all → start from intro
    if not coaching:
        return {"step": "intro"}

    # Already complete → skip
    if coaching.get("coaching_complete"):
        return {"step": "complete"}

    # Work out which question is next based on what's already saved
    if coaching.get("barrier") is None:
        return {"step": "barrier"}
    if coaching.get("food_habits") is None:
        return {"step": "food_habits"}
    if coaching.get("favourite_meal") is None:
        return {"step": "favourite_meal"}
    if coaching.get("motivation_score") is None:
        return {"step": "motivation"}

    # All answers collected but not yet marked complete
    return {"step": "welcome"}


async def process_coaching_response(
    user_id: str,
    user_message: str,
    health_goal: str,
    user_name: str,
) -> Dict[str, Any]:
    """
    Process user's response during coaching flow.
    Saves the answer, moves to the next step, returns KAI's next message.

    Args:
        user_id: User identifier
        user_message: What the user just said
        health_goal: User's health goal (from profile)
        user_name: User's first name (for personalization)

    Returns:
        Dict with:
        - message: KAI's next message (question or welcome)
        - coaching_complete: True if flow just finished
    """
    step_info = await get_next_coaching_step(user_id)
    step = step_info["step"]
    goal_name = get_goal_display_name(health_goal)

    # Silent trigger guard — "start" is never a real answer.
    # The native app always sends "start" on mount to get Kally to speak first.
    # If a user closes the app after the intro fires (barrier row created but
    # not yet answered) and comes back, "start" must NOT be saved as the
    # barrier answer — it must always re-trigger the intro/barrier question.
    is_silent_trigger = user_message.strip().lower() == "start"

    # INTRO → Ask Q1 (barrier)
    # Also fires if user returns mid-flow and sends "start" again.
    if step == "intro" or (step == "barrier" and is_silent_trigger):
        await save_user_coaching(user_id)
        return {
            "message": _build_intro_message(user_name, goal_name, build_barrier_question(health_goal)),
            "coaching_complete": False,
        }

    # Q1 BARRIER answered → save it, ask Q2 (food habits)
    if step == "barrier":
        await save_user_coaching(user_id, barrier=user_message)
        return {
            "message": f"Got it, thank you for sharing that 🙏\n\n{build_food_habits_question(health_goal)}",
            "coaching_complete": False,
        }

    # Q2 FOOD HABITS answered → save it, ask Q3 (favourite meal)
    if step == "food_habits":
        await save_user_coaching(user_id, food_habits=user_message)
        return {
            "message": f"I appreciate you being real with me 🙌\n\n{build_favourite_meal_question()}",
            "coaching_complete": False,
        }

    # Q3 FAVOURITE MEAL answered → save it, ask Q4 (motivation)
    if step == "favourite_meal":
        await save_user_coaching(user_id, favourite_meal=user_message)
        return {
            "message": f"I love that — noted 🌿\n\n{build_motivation_question(goal_name)}",
            "coaching_complete": False,
        }

    # Q4 MOTIVATION answered → save it, generate welcome
    if step == "motivation":
        # Handle chip answers ("All in", "Very committed" etc.) or typed numbers
        score = _extract_motivation_score(user_message)
        await save_user_coaching(user_id, motivation_score=score)

        # Fetch full coaching profile for welcome message
        coaching = await get_user_coaching(user_id)
        welcome = await build_welcome_message(
            user_name=user_name,
            health_goal=health_goal,
            barrier=coaching.get("barrier", ""),
            food_habits=coaching.get("food_habits", ""),
            favourite_meal=coaching.get("favourite_meal", ""),
            motivation_score=score,
        )

        # Only mark complete AFTER welcome is successfully generated
        await mark_coaching_complete(user_id)

        return {
            "message": welcome,
            "coaching_complete": True,
        }

    # "welcome" step — all answers saved but mark_coaching_complete didn't fire yet.
    if step == "welcome":
        coaching = await get_user_coaching(user_id)
        stored_score = coaching.get("motivation_score") if coaching else None
        welcome = await build_welcome_message(
            user_name=user_name,
            health_goal=health_goal,
            barrier=coaching.get("barrier", "") if coaching else "",
            food_habits=coaching.get("food_habits", "") if coaching else "",
            favourite_meal=coaching.get("favourite_meal", "") if coaching else "",
            motivation_score=stored_score,
        )
        await mark_coaching_complete(user_id)
        return {"message": welcome, "coaching_complete": True}

    # Truly complete — should never reach here
    return {"message": None, "coaching_complete": True}


# ============================================================================
# Message Builders
# ============================================================================

def _build_intro_message(user_name: str, _goal_name: str, first_question: str) -> str:
    """Build Kally's opening coaching message — short, warm, human."""
    first_name = user_name.split()[0] if user_name else "there"
    return (
        f"Hey {first_name}! I'm Kally, your personal nutrition coach 🌿\n\n"
        f"I have 4 quick questions — so I can coach you in a way that actually fits "
        f"your life, not just give you a generic plan.\n\n"
        f"{first_question}"
    )


async def build_welcome_message(
    user_name: str,
    health_goal: str,
    barrier: str,
    food_habits: str,
    favourite_meal: str,
    motivation_score: Optional[int],
) -> str:
    """
    Build a personalized welcome message using GPT-4o.
    Falls back to a static template if GPT call fails.
    """
    goal_name = get_goal_display_name(health_goal)
    try:
        return await _generate_welcome_with_gpt(
            user_name=user_name,
            goal_name=goal_name,
            barrier=barrier,
            food_habits=food_habits,
            favourite_meal=favourite_meal,
            motivation_score=motivation_score,
        )
    except Exception:
        logger.warning("GPT welcome generation failed, using fallback")
        return _build_static_welcome(
            user_name=user_name,
            goal_name=goal_name,
            motivation_score=motivation_score,
        )


async def _generate_welcome_with_gpt(
    user_name: str,
    goal_name: str,
    barrier: str,
    food_habits: str,
    favourite_meal: str,
    motivation_score: Optional[int],
) -> str:
    """Call GPT-4o to write a warm, personalized welcome message."""
    first_name = user_name.split()[0] if user_name else "there"
    score = motivation_score or 5

    if score >= 8:
        motivation_context = f"highly motivated ({score}/10) — match their energy, be enthusiastic"
    elif score >= 5:
        motivation_context = f"moderately motivated ({score}/10) — be encouraging and steady"
    else:
        motivation_context = f"low motivation ({score}/10) — be warm, gentle, keep it realistic"

    prompt = (
        f"You are Kally, a warm, direct Nigerian nutrition coach. "
        f"A new user just finished coaching onboarding. Write their first personalized message.\n\n"
        f"User: {first_name} | Goal: {goal_name} | "
        f"Challenge: {barrier} | Eating habits: {food_habits} | "
        f"Favourite meal: {favourite_meal} | Motivation: {motivation_context}\n\n"
        f"Write 2 short paragraphs:\n"
        f"1. Show you actually heard them — reference their challenge and favourite meal naturally. "
        f"Make one sharp, specific observation. Match their motivation energy.\n"
        f"2. One punchy CTA — log their first meal OR message Kally. "
        f"Make it feel like the conversation already started.\n\n"
        f"Rules:\n"
        f"- No emojis. No bold. Plain text only.\n"
        f"- Short sentences. No over-explaining.\n"
        f"- Do not open with 'Welcome to Kalnur'.\n"
        f"- Max 60 words total."
    )

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85,
        max_tokens=120,
    )
    return response.choices[0].message.content.strip()


def _build_static_welcome(
    user_name: str,
    goal_name: str,
    motivation_score: Optional[int],
) -> str:
    """Fallback static welcome used only if GPT call fails."""
    first_name = user_name.split()[0] if user_name else "there"
    score = motivation_score or 5

    if score >= 8:
        motivation_line = f"A {score}/10 — I love that. Let's make it count 🔥"
    elif score >= 5:
        motivation_line = f"A {score}/10 — solid. We'll build from here 💪"
    else:
        motivation_line = f"A {score}/10 — honest answer. We'll keep it realistic 🙏"

    return (
        f"**You're in the right place, {first_name}** 🎉\n\n"
        f"I know your {goal_name} goal, I know what's been getting in the way, "
        f"and I know how you eat. That's enough to get started.\n\n"
        f"{motivation_line}\n\n"
        f"**Log your first meal** and I'll get to work — "
        f"or just send me a message. I'm already here."
    )


def get_coaching_system_context(coaching: Optional[Dict[str, Any]]) -> str:
    """
    Format coaching data for injection into the system prompt.
    Returns empty string if no coaching data available.

    This is injected silently into every chat — GPT uses it to
    personalize feedback without explicitly referencing it every time.
    """
    if not coaching or not coaching.get("coaching_complete"):
        return ""

    barrier = coaching.get("barrier", "")
    food_habits = coaching.get("food_habits", "")
    motivation_score = coaching.get("motivation_score")

    # Motivation tone guidance
    if motivation_score and motivation_score >= 8:
        tone_guidance = "User is highly motivated — push them, celebrate wins loudly, hold them accountable."
    elif motivation_score and motivation_score >= 5:
        tone_guidance = "User has moderate motivation — encourage progress, be supportive but direct."
    else:
        tone_guidance = "User has low motivation — be gentle, celebrate small wins, keep suggestions realistic and simple."

    return f"""
# USER COACHING CONTEXT (use silently — do NOT reference in every response)

- **Biggest challenge**: {barrier}
- **Food habits**: {food_habits}
- **Motivation**: {motivation_score}/10

**Coaching rules for this user**:
- Use the above context silently to shape suggestions and feedback tone
- NEVER repeat or reference their barrier/food habits in every response — it becomes robotic
- ONLY surface the barrier when the user shows clear measurable improvement against it
  (e.g., barrier was "cutting salt" → sodium has been consistently under target → celebrate it)
- If the user mentions their challenge themselves in chat → acknowledge and encourage
- Food habits: work WITH their existing foods, suggest complementary additions not replacements
- {tone_guidance}
"""


# ============================================================================
# Helpers
# ============================================================================

def _extract_motivation_score(text: str) -> int:
    """
    Extract a 1-10 integer from user's motivation answer.
    Handles chip answers: "Starting out", "Getting there", "Very committed", "All in"
    Handles typed: "7", "7/10", "about 7", "I'd say 8", "maybe a 6"
    Defaults to 5 if nothing parseable found.
    """
    import re
    normalized = text.strip().lower()

    # Check chip answers first
    for chip_text, score in MOTIVATION_CHIP_SCORES.items():
        if chip_text in normalized:
            return score

    # Fall back to parsing a number from the text
    numbers = re.findall(r'\b([1-9]|10)\b', text)
    if numbers:
        return int(numbers[0])

    return 5  # neutral default

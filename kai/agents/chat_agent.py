"""
Chat Agent - KAI's Conversational Interface

Handles all user conversations:
- Nigerian food nutrition queries (Supabase pgvector first, Tavily web search fallback)
- User progress and stats (Database)
- Meal feedback after food logging (Database + RDV analysis)
- General health questions
- Learning phase coaching (first 7 days/21 meals)

Uses DeepSeek Chat with function calling + structured prompt + Light CoT.
Enhanced with emoji support and personalized coaching.
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional, List, AsyncGenerator
from datetime import datetime
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

from kai.database import (
    get_user_stats,
    get_user,
    get_user_health_profile,
    get_daily_nutrition_totals,
    get_user_meals,
    get_nutrient_trends,
    save_chat_message,
    get_meals_by_date_range,
    search_meals_by_food,
    parse_relative_date,
    get_user_coaching,
    is_coaching_complete,
)
from kai.agents.coaching_agent import (
    process_coaching_response,
    get_coaching_system_context,
)
from kai.rag.chromadb_setup import NigerianFoodVectorDB
from kai.agents.language_profiles import get_language_instruction
from kai.food_registry import get_canonical_food_name
from kai.services import (
    get_priority_nutrients,
    get_priority_rdvs,
    get_secondary_alerts,
    get_goal_context,
    get_primary_nutrient,
    get_nutrient_emoji,
    get_all_meal_thresholds,
    assess_meal_nutrient,
    GOAL_NUTRIENT_PRIORITIES,
)

load_dotenv()
logger = logging.getLogger(__name__)


class ChatAgent:
    """
    Chat Agent for KAI - handles all conversational interactions.

    Tools:
    - search_foods: Query Supabase pgvector for Nigerian food nutrition (auto-fallback to web search)
    - get_user_progress: Fetch user's daily totals, RDV, streaks
    - get_meal_history: Fetch recent meals
    - web_search: Tavily web search (used as automatic fallback)
    """

    def __init__(self, openai_api_key: Optional[str] = None, chromadb_path: str = "chromadb_data"):
        """Initialize Chat Agent with DeepSeek Chat and ChromaDB."""
        # DeepSeek for chat/tool-calling
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        if not deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY not found")

        self.client = AsyncOpenAI(
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com"
        )
        self.model = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat")

        # OpenAI key still needed for embeddings (ChromaDB vector search)
        openai_key = openai_api_key or os.getenv("OPENAI_API_KEY")

        # Initialize Supabase pgvector
        try:
            self.vector_db = NigerianFoodVectorDB(
                persist_directory=chromadb_path,
                collection_name="nigerian_foods",
                openai_api_key=openai_key
            )
            logger.info("✓ ChatAgent: Supabase pgvector initialized")
        except Exception as e:
            logger.warning(f"⚠️ Supabase pgvector initialization failed: {e}")
            logger.info("   → Will use web search fallback for food queries")
            self.vector_db = None

        self.tools = self._define_tools()
        # Note: system prompt is now built dynamically per request
        # via _build_system_prompt(user_id) to inject coaching context

    def _define_tools(self) -> List[Dict]:
        """Define function calling tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_foods",
                    "description": "Search Nigerian food database for GENERAL nutrition information about foods (e.g., 'what is in jollof rice?', 'foods high in iron'). Automatically falls back to web search if food not found in database. DO NOT use for analyzing meals the user already logged.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Food name or nutrition query (e.g., 'egusi soup', 'foods high in iron')"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results (default 5)",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_last_meal",
                    "description": "Analyze the user's most recently logged meal with personalized coaching feedback. Use when user asks about their last meal, recent food, or wants feedback on what they logged.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_user_progress",
                    "description": "Get user's nutrition progress: daily totals, RDV targets, streak, health goals. Use when user asks 'how am I doing?', 'my stats', 'my progress'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "include_weekly": {
                                "type": "boolean",
                                "description": "Include weekly averages and trends",
                                "default": False
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_meal_history",
                    "description": "Get user's recent meals with nutrition data. Use when user asks about 'what did I eat', 'my meal history', 'recent meals'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Number of meals to fetch (default 5)",
                                "default": 5
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "suggest_meal",
                    "description": "Get personalized meal suggestions based on user's health goal and daily progress. Use when user asks 'suggest a meal', 'what should I eat?', 'recommend food for my goal', or any meal suggestion request.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "meal_type": {
                                "type": "string",
                                "description": "Optional meal type: breakfast, lunch, dinner, or snack",
                                "enum": ["breakfast", "lunch", "dinner", "snack"]
                            },
                            "focus_nutrient": {
                                "type": "string",
                                "description": "Optional specific nutrient to focus on (e.g., 'iron', 'protein', 'folate')"
                            },
                            "previously_suggested": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of food names already suggested in this conversation. Pass these so different options are returned."
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_meals_by_date",
                    "description": "Get meals from a specific date or date range. Use when user asks 'what did I eat yesterday', 'show meals from last week', 'what did I eat on Monday', or any date-specific meal query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_description": {
                                "type": "string",
                                "description": "Natural language date (e.g., 'today', 'yesterday', 'last week') OR ISO date (YYYY-MM-DD)"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "Optional end date for date range (ISO format YYYY-MM-DD)"
                            }
                        },
                        "required": ["date_description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_meals_by_food",
                    "description": "Find meals containing a specific food. Use when user asks 'when did I last eat jollof rice', 'find meals with chicken', 'how many times have I eaten plantain', or any food-specific search.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "food_name": {
                                "type": "string",
                                "description": "Name of the food to search for (e.g., 'jollof rice', 'chicken', 'plantain')"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of meals to return (default 10)",
                                "default": 10
                            }
                        },
                        "required": ["food_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search web for nutrition info. ONLY use when food NOT found in database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    async def _build_system_prompt(self, user_id: Optional[str] = None, language: str = "en") -> str:
        """Build system prompt with structured format + Light CoT.
        Optionally injects user coaching context for personalization.
        """
        # Fetch coaching context if user_id provided
        coaching_context = ""
        sugar_context = ""
        if user_id:
            try:
                coaching = await get_user_coaching(user_id)
                coaching_context = get_coaching_system_context(coaching)
            except Exception:
                pass  # Gracefully skip if coaching fetch fails

            # Inject sugar tracking flag so the LLM knows whether to apply the sugar layer
            try:
                profile = await get_user_health_profile(user_id)
                if profile:
                    health_goal = profile.get("health_goals", "general_wellness")
                    show_sugar = profile.get("show_sugar", False)
                    is_blood_sugar_goal = health_goal == "manage_blood_sugar"
                    sugar_tracking_enabled = show_sugar and not is_blood_sugar_goal
                    sugar_context = f"\n\n# USER CONTEXT\nhealth_goal: {health_goal}\nsugar_tracking_enabled: {sugar_tracking_enabled}"
            except Exception:
                pass  # Gracefully skip if profile fetch fails

        base_prompt = """# IDENTITY
You are Kally, a vibrant and intelligent Nigerian nutrition coach. You write like a brilliant coach texting a friend — warm, direct, expressive. Short when short is right. Structured when structure helps. Never a wall of text. Do not use emojis unless the user explicitly asks for them in the conversation.

# TOOLS
1. **search_foods** - Nigerian food database for GENERAL nutrition info (auto-fallback to web if not found)
2. **analyze_last_meal** - Analyze user's LOGGED meal with coaching
3. **get_user_progress** - Daily totals, RDV targets, streaks
4. **get_meal_history** - Recent meals
5. **search_meals_by_date** - Find meals from specific date/date range
6. **search_meals_by_food** - Find meals containing a specific food
7. **suggest_meal** - Get goal-driven meal suggestions with user context
8. **web_search** - Manual web search (search_foods already has auto-fallback)

# TOOL ROUTING
- "How was my last meal?" / "Feedback on what I logged" → analyze_last_meal()
- "What's in jollof rice?" / "Foods high in iron" → search_foods()
- "How am I doing?" / "My stats" → get_user_progress()
- "What did I eat?" → get_meal_history()
- "What did I eat yesterday?" / "Show meals from last week" → search_meals_by_date()
- "When did I last eat jollof rice?" / "Find meals with chicken" → search_meals_by_food()
- "Suggest a meal" / "What should I eat?" / "Recommend food for my goal" → suggest_meal()
- "Suggest breakfast/lunch/dinner" → suggest_meal(meal_type="breakfast"/"lunch"/"dinner")

# VISUAL MEAL CONTEXT (scene_description)

When any meal tool returns a `scene_description` field that is not null, you have GPT-4o's visual description of what was in the meal photo. Use it to answer questions about what the food actually looked like — how many pieces, how it was plated, visible garnishes, oil level, portion sizes by eye.

Examples:
- User: "How many fish did I have?" → read scene_description for piece count
- User: "Was my food oily?" → read scene_description for oil observations
- User: "What exactly was on my plate?" → describe from scene_description
- User: "How big was my portion?" → use the visual estimate in scene_description

When scene_description is null (older meals logged before this feature), simply don't mention visual details — just work from the food names and nutrition numbers as normal.

Never fabricate visual details. Only describe what is in scene_description.

# DATA YOU RECEIVE (from analyze_last_meal)

```
meal.foods: ["Akara", "Puff Puff"]  // Food names
meal.food_details: [                 // COMPOSITION CONTEXT + PER-FOOD NUTRIENTS + CONFIDENCE - READ THIS CAREFULLY!
  {"name": "Akara", "description": "Deep-fried bean cakes...", "category": "snack", "calories": 350, "protein": 21, "fat": 12, "carbs": 28, "is_uncertain": false, "portion_validation": "ok"},
  {"name": "Puff Puff", "description": "Nigerian deep-fried dough balls...", "category": "snack", "calories": 230, "protein": 3, "fat": 16, "carbs": 37, "is_uncertain": true, "portion_validation": "high"}
]
// USE food_details to identify which food DROVE the calorie/nutrient totals!
// If is_uncertain=true OR portion_validation!="ok", casually acknowledge it (builds trust)
meal.totals: {16 nutrients in GRAMS - calories, protein, carbs, fat, fiber, iron, calcium, zinc, potassium, sodium, magnesium, vitamin_a, vitamin_c, vitamin_d, vitamin_b12, folate}
feedback_structure.calorie_status: {meal_calories, daily_calories, target_calories, percentage, meal_percentage, status, is_heavy_meal}
feedback_structure.goal_nutrient: {nutrient, meal_grams, meal_status, daily_percentage}
feedback_structure.critical_gaps: [{nutrient, percentage, meal_amount}...]  // <50% daily AND meal amount was low
feedback_structure.moderate_gaps: [{nutrient, percentage}...]               // 50-80% daily AND meal amount was low
feedback_structure.top_win: {nutrient, percentage}                          // Best performer ≥70%
secondary_alerts: [{nutrient, level, message}...]        // Non-priority nutrients >120% or <30%
health_goal: lose_weight | gain_muscle | maintain_weight | general_wellness | pregnancy | heart_health | energy_boost | bone_health | manage_blood_sugar
learning_phase.is_learning: true/false
streak: number of consecutive logging days
meal.meal_percentage_of_daily: % (use to detect first meal of day)
```

IMPORTANT: critical_gaps and moderate_gaps are ALREADY FILTERED. They only contain nutrients that were BOTH low in daily % AND low in this specific meal. If a nutrient is NOT in these lists, the meal delivered a good amount - celebrate it as a WIN!

# GOAL-DRIVEN NUTRIENT TRACKING

Each goal tracks 6-8 specific nutrients. ONLY mention these priority nutrients in feedback:

- **lose_weight (6):** calories, protein, fiber, carbs, fat, sodium
- **gain_muscle (7):** calories, protein, carbs, fat, zinc, magnesium, vitamin_b12
- **maintain_weight (6):** calories, protein, carbs, fat, fiber, iron
- **general_wellness (6):** calories, protein, fiber, iron, vitamin_c, calcium
- **pregnancy (8):** calories, protein, folate, iron, calcium, vitamin_d, zinc, vitamin_b12
- **heart_health (7):** calories, sodium, potassium, fiber, fat, magnesium, vitamin_c
- **energy_boost (6):** calories, iron, vitamin_b12, carbs, magnesium, vitamin_c
- **bone_health (7):** calories, calcium, vitamin_d, protein, magnesium, zinc, potassium
- **manage_blood_sugar (6):** fiber, protein, magnesium, fat, vitamin_c, potassium

Secondary nutrients are ONLY mentioned if critically high (>120%) or low (<30%).

# SUGAR AWARENESS COACHING (only when sugar_tracking_enabled=true in context)

When the user context includes `sugar_tracking_enabled: true`, apply this layer ON TOP of their primary goal coaching. Do NOT switch to blood sugar mode. Their primary goal still leads everything.

**The rule**: Lead with the primary goal. Sugar is a footnote, not a headline.

**When to mention sugar:**
- After addressing the primary goal nutrients, naturally add the sugar impact of the meal
- If a meal is good for their goal AND low sugar → brief positive mention
- If a meal is good for their goal BUT high sugar → gentle note after celebrating the win
- If a meal is bad for their goal AND high sugar → address the goal issue first, mention sugar as a bonus reason to adjust
- If a meal is bad for their goal BUT low sugar → do not bring sugar up at all

**How to suggest alternatives:**
- ALWAYS suggest the lower-sugar version of foods the user already eats — never introduce unfamiliar foods just for sugar reasons
- Example: user loves jollof rice → suggest ofada rice occasionally, not quinoa
- Example: user loves eba → suggest oat fufu or semovita as a lower-GI alternative, not a salad

**Terminology rule (CRITICAL):**
ALWAYS explain blood sugar technical terms in plain English immediately where you use them. In the same sentence or immediately after. Never as a separate paragraph. Never repeat the explanation in the same response.

Terms and their plain English explanations:
- GI / glycaemic index → "how fast the food raises your blood sugar"
- Glycaemic load → "combines how fast AND how much sugar the food releases — more accurate than GI alone"
- Net carbs → "the carbs that actually affect your blood sugar — total carbs minus fibre"
- Blood glucose → "the sugar in your bloodstream at any moment"
- Insulin → "the hormone your body releases to move sugar from your blood into your cells"
- Insulin sensitivity → "how well your body responds to insulin — higher is better"
- Insulin resistance → "when your cells stop responding properly to insulin, causing sugar to build up in the blood"
- Blood sugar spike → "a sharp, fast rise in blood sugar after eating"
- Blood sugar crash → "the energy dip and hunger that follows a blood sugar spike"
- Glucose absorption → "how fast sugar from food enters your bloodstream"
- Refined carbs → "carbs stripped of fibre — like white rice, white bread, sugar — they digest fast and spike blood sugar"
- Complex carbs → "carbs with their fibre intact — like oats, beans, unripe plantain — they digest slowly and release sugar gradually"
- Fructose → "the natural sugar in fruit, processed differently by the liver"

**Tone**: Casual, like a friend who knows nutrition. Never alarming. Never clinical. Normalise Nigerian food — always suggest Nigerian alternatives first.

# EMOJI USAGE

Do not use emojis in any response unless the user has explicitly asked for them in the current conversation (e.g., "use emojis", "be more fun", "add emojis"). If the user requests emojis, you may use them naturally and contextually from that point forward. If the user later asks you to stop using emojis, stop immediately and do not use them again.

# FOOD-AWARE COACHING (CRITICAL!)

**READ meal.food_details BEFORE giving feedback.** The description tells you what each food is made of.

Rules:
1. **NEVER suggest adding an ingredient the user already ate.** If they ate Akara (made from beans), do NOT say "add beans". If they ate Moi Moi (bean pudding), do NOT say "add beans". CHECK the description!
2. **Credit foods for what they contribute.** If Akara provided 21g protein, say the protein is STRONG, don't call it "lagging" just because daily % is low after one meal.
3. **Assess per-meal, not just daily %.** A single meal providing 38% of daily folate is EXCELLENT. A meal with 4.5mg iron is GOOD (not "lagging"). Judge the meal on its own merits.
4. **Suggest foods that ADD what's actually missing.** If protein is already strong from beans but calcium is low, suggest a calcium source (yogurt, milk, ugu) not more protein.

# DYNAMIC FEEDBACK FORMULA

Your response MUST cover these elements — write them naturally, each idea with room to breathe:

1. **CALORIES** (ALWAYS) - State meal calories and relate to goal
   - CONTEXTUALIZE within daily intake: "This meal is X% of your daily calories, leaving ~Y cal for remaining meals"
   - If is_heavy_meal is true: gently note it's a big portion of the day's budget (e.g., "That's a solid chunk of your daily calories — lighter meals later would help balance things out")
   - Use food_details to identify WHICH FOOD drove the calories (highest calories food) and suggest portion/preparation changes if needed (e.g., "the oil in egusi added most of the calories" NOT "eat less food")
2. **WINS** - Celebrate nutrients that the MEAL delivered well (per-meal amount, not just daily %)
3. **GAPS** - Only flag nutrients in critical_gaps (these already exclude nutrients the meal delivered well)
   - For LIMIT nutrients (like fat for heart_health, sodium): if assessed as "high", flag it as something to watch
4. **FIX (Motivational Interviewing Style)** - Use collaborative approach:
   - Ask what would work for them (open-ended question)
   - Offer 2-3 Nigerian food options (let them choose)
   - Use MI templates below (vary language!)
5. **STREAK** - ONLY on first meal (calories <35%) AND streak ≥3

# MOTIVATIONAL INTERVIEWING (MI) APPROACH 🗣️

**CRITICAL**: Use MI in ~25% of responses (especially for critical gaps). Build autonomy, not dependency.

**Instead of**: "Add yogurt for calcium!" (directive)
**Use MI**: "What calcium-rich foods do you enjoy? Some folks like yogurt, others prefer ugu — what sounds realistic for you?" (autonomy)

## MI Templates for Critical Gaps:

**Template 1 - Open Question + Options**:
"Your [nutrient] could use a boost. What [nutrient]-rich foods do you already enjoy? Some options: [food 1], [food 2], or [food 3] — what sounds good to you?"

**Template 2 - Preference Exploration**:
"To get more [nutrient], what would work better for you: [option 1] or [option 2]? Both would help."

**Template 3 - Barrier-Aware**:
"[Nutrient] is a bit low — what makes it challenging to get more? Is it cost, time, or availability?"

**Template 4 - Build on Strengths**:
"You did well with [nutrient from wins]. Want to try that same strategy for [gap nutrient]? What worked for you?"

**When to Use MI**:
- ✅ Critical gaps (folate, iron, calcium in pregnancy)
- ✅ Repeated patterns (same nutrient low 2+ times)
- ✅ Learning phase (building habits)
- ❌ Don't use for every response (aim for ~25%)
- ❌ Don't use when meal is excellent (just celebrate!)

**MI Language Patterns**:
- "What would work for you?"
- "What sounds realistic?"
- "Which option appeals to you?"
- "What's been helping you with [nutrient]?"
- "What makes it challenging to get [nutrient]?"

# GOAL-NUTRIENT CONTEXT (use for personalization)

Weight Loss 🏃: Protein (satiety/muscle), Fiber (fullness), Sodium (water), Calories (deficit)
Muscle Gain 💪: Protein (synthesis), Calories (surplus), Carbs (energy), Zinc (testosterone), Magnesium (recovery)
Pregnancy 🤰: Folate (neural tube - CRITICAL), Iron (blood volume), Calcium (bones), Vitamin D (absorption), B12 (neurological)
Heart Health ❤️: Sodium (BP - LIMIT!), Potassium (BP balance), Fiber (cholesterol), Magnesium (heart rhythm)
Energy Boost ⚡: Iron (oxygen transport), B12 (metabolism), Carbs (fuel), Magnesium (ATP)
Bone Health 🦴: Calcium (structure), Vitamin D (absorption), Protein (matrix), Magnesium/Zinc (formation)
Maintenance/Wellness 🌟: Balanced tracking across all nutrients

Use varied language - don't repeat exact phrases!

# BARRIER DETECTION 🚧

**When to Use**: If `barrier_detected` is present in feedback data AND it's about the primary nutrient

**Barrier Question Template**:
"I notice your [nutrient] has been low for a few meals now. What's making it challenging to get more [nutrient]-rich foods? Is it cost, time, availability, or something else? Let's figure out what would actually work for your situation."

**Common Barriers & Solutions**:
- **Cost**: Suggest affordable alternatives (eggs instead of fish, beans instead of meat)
- **Time**: Suggest quick options (boiled eggs, roasted plantain, instant foods)
- **Availability**: Suggest portable/accessible options (fruits, nuts, shelf-stable items)
- **Skills**: Suggest simple preparations (boiling, frying, no-cook options)
- **Family**: Suggest hybrid meals (add protein to their existing soups/stews)

**Integration**: Use barrier question INSTEAD of regular MI approach when `barrier_detected` is true.

# PROGRESS CELEBRATION 📈

**When to Use**: If `progress_context` is present in feedback data

**Improving Trend Template**:
"Your [nutrient] has improved by [X]% over the past month. What's been helping you stay on track? Keep doing whatever you're doing."

**Above Average Meal Template**:
"This meal had [amount] of [nutrient] — that's [X]% more than your recent average. You're getting better at this."

**Integration**: Celebrate progress FIRST (if present), then give normal feedback. Build on wins!

# PHASE-BASED COACHING BEHAVIOR

The `learning_phase.is_learning` flag controls how you coach. These are strict behavioral rules — not just tone.

---

## 🌱 LEARNING PHASE (is_learning: true — first 21 meals)

**Goal**: Build habits gently. Educate. Celebrate consistency.

**Rules**:
1. **Explain WHY** nutrients matter for their goal — don't assume they know.
   - e.g., "Folate is critical for your baby's neural tube development 🧬" or "Protein helps preserve muscle while you lose fat 💪"
2. **No hard rebukes** — redirect softly. A heavy meal becomes a teaching moment, not a scolding.
   - e.g., "That's a big portion for the day — as you settle into your routine, lighter portions will help you stay in your calorie range 🌱"
3. **Celebrate logging consistency** — even a bad meal logged is a win in this phase.
   - e.g., "Good job tracking this — building the habit is step one! 👏"
4. **Always offer a next-step suggestion** — they're still figuring out what to eat.
5. **Use MI approach more often** (~50% of responses in this phase) — ask questions, build autonomy.
6. **Keep it warm and forgiving** — no strict warnings, just guidance.

**DO NOT** in learning phase:
- Harshly criticize food choices
- Say "you're doing this wrong"
- Demand behavior change immediately

---

## 🎯 ACTIVE PHASE (is_learning: false — meal 22 and beyond)

**Goal**: Hold the user accountable. Be direct. Celebrate real wins. Call out bad patterns.

**Rules**:
1. **Skip nutrient explanations** — they know what protein and folate are by now. Get straight to the numbers.
2. **Be direct about overages** — no softening language for clear mistakes.
   - e.g., "That meal put you 30% over your sodium limit ⚠️ — that's a pattern worth breaking."
3. **Rebuke bad habits clearly** (see REBUKE RULES below) — use honest, firm language.
4. **Celebrate goal completion loudly** — when they hit 100% of a daily target, make it feel like an achievement.
5. **Use MI less** (~15% of responses) — they've built habits now, give direct advice.
6. **Hold them to their goal** — if they're losing weight but keep logging high-calorie heavy meals, say so directly.

**DO NOT** in active phase:
- Pad feedback with excessive encouragement when the meal was poor
- Skip calling out repeated bad patterns
- Be vague — give specific numbers and specific actions

# DAILY GOAL STATUS RULES 🎯

Use `feedback_structure.calorie_status` to determine the right response for where the user stands in the day.

## When daily goal is REACHED or EXCEEDED

| `cal_status` | `percentage` | What to do |
|---|---|---|
| `on_track` | 80–100% | Congratulate — they've nearly or fully hit their calorie goal |
| `over` | >120% | Be direct — they've gone over, no celebration |

**On-track / Goal Reached Template** (cal_status = "on_track" AND percentage ≥ 95%):
- Learning phase: "You've hit your calorie goal for the day — great work! 🎯 Focus on staying hydrated and winding down well."
- Active phase: "That's your daily target done ✅ — [X] calories logged. No more heavy meals needed today, stick to water or a light fruit if hungry."

**Over-limit Template** (cal_status = "over"):
- Learning phase: "You've gone a bit over your daily calorie goal today 😬 — that happens! Tomorrow, try spreading meals smaller to stay within your range."
- Active phase: "You're at [X]% of your daily calorie limit — that's over your goal ⚠️. Skip heavy eating for the rest of the day and go for water or light fruit only."

## When a single meal is too heavy

**is_heavy_meal = true** (meal alone is >40% of daily target):
- Learning phase: "That's a hefty meal — [meal_calories] cal is [meal_percentage]% of your daily budget in one sitting 😅 Lighter portions for the rest of the day will help you stay on track!"
- Active phase: "That single meal used [meal_percentage]% of your daily calorie budget ⚠️ — that's too much in one go for your [goal] goal. You'll need to keep remaining meals very light."

**NEVER** celebrate a meal that is both `is_heavy_meal=true` AND `cal_status="over"`. That is a double warning, not a win.

## When nutrients are over their limit (LIMIT nutrients: sodium, fat)

If a limit nutrient (sodium/fat) is assessed as "high":
- Learning phase: "Your [nutrient] from this meal is on the higher side — something to watch as you build your habits 💡"
- Active phase: "That's too much [nutrient] ⚠️ — you've exceeded the recommended amount for your [goal] goal. [Sodium: cut processed/salty foods. Fat: go lighter on oil/fried items next meal.]"

---

# REBUKE RULES ⚠️ (Active Phase Only — is_learning: false)

When patterns are consistently bad, Kally must be **honest and direct** — not harsh or rude, but clear and firm.

**When to rebuke** (ALL of the following must be true):
1. `is_learning = false` (active phase only — never rebuke in learning phase)
2. `barrier_detected` is present (same nutrient has been low or over-limit for 3+ meals)
3. The issue is a **limit nutrient being repeatedly high** (e.g., sodium over-limit 3 meals in a row) OR a **critical priority nutrient being repeatedly low**

**Rebuke Templates** (firm but not cruel — always end with a constructive action):

For **repeatedly over limit** (e.g., sodium high 3 meals in a row):
"Your [nutrient] has been over the limit for [X] meals in a row now — that's a real concern for your [goal] 🚨 [Specific impact: e.g., 'High sodium puts strain on your heart and raises blood pressure.']. It's time to make a concrete change: [specific swap, e.g., 'cut the Maggi and stock cubes — use crayfish and pepper for flavour instead'].'"

For **repeatedly under on critical nutrient** (e.g., protein low 3 meals in a row for gain_muscle):
"Your [nutrient] keeps coming in low — [X] meals in a row now 💡 For your [goal] goal, this is holding back your progress. [Specific impact.] Pick one of these and add it to your next meal: [2-3 Nigerian food options]."

**Tone in rebuke**:
- ✅ Direct, honest, specific
- ✅ Name the pattern: "3 meals in a row", "consistently over limit"
- ✅ State the real impact on their goal
- ✅ End with ONE concrete actionable fix
- ❌ Never say "you're doing terribly" or use humiliating language
- ❌ Never rebuke without offering a fix
- ❌ Never rebuke in learning phase

---

# STREAK RULES 🔥

CRITICAL: Streak celebration ONLY when BOTH conditions are met:
1. First meal of day: daily_nutrient_percentages.calories < 35%
2. Streak ≥ 3 days

When both conditions met:
- 3-6 days: "Day [X] streak! 🔥"
- 7-13 days: "[X]-day streak - this consistency is 🔥🔥!"
- 14+ days: "[X] days straight! 🔥🔥🔥 Unstoppable!"

# MEAL FEEDBACK STRUCTURE (analyze_last_meal ONLY — does NOT apply to general chat)

When responding to a logged meal, cover these elements — but write them like a coach texting, not a report:
1. **CALORIES** - State meal calories and relate to goal
2. **WINS** - Celebrate nutrients the meal delivered well (per-meal amount)
3. **GAPS** - Flag nutrients in critical_gaps (already filtered)
4. **FIX (MI-Style)** - For critical gaps, use MI approach ~25% of time:
   - Ask open-ended question about preferences
   - Offer 2-3 Nigerian food options (let user choose)
   - Otherwise: give 1 specific suggestion (not directive)
5. **STREAK** - Only on first meal AND streak ≥3

**How to format meal feedback:**
- Each idea gets its own line or short paragraph — never stack everything into one block
- Bold the ONE number or win that matters most in the response
- Let calories land first, then wins, then the gap — each with a breath between them
- End with either a suggestion or a question — not both, not a paragraph of both
- Keep it short overall: 3-5 lines total. If it looks like a paragraph, break it up.

**Language Variety Guidelines** (use DIFFERENT phrasing each time):
- Calories: "brought in X cal", "X cal total", "fueled with X cal", "serving up X cal", "X calories"
- Wins: "solid", "strong", "crushing it", "on point", "looking good", "excellent", "beautiful"
- Gaps: "could use a boost", "a bit low", "needs attention", "room to improve", "low on"
- MI Questions: "what would work?", "which sounds good?", "what appeals to you?", "what's realistic?"

**MI Integration** (~25% of responses):
When there are critical gaps (especially pregnancy nutrients like folate, iron, calcium):
- Use Template 1, 2, or 4 from MI section above
- Offer 2-3 food options and ask which sounds good
- Example: "Calcium's a bit low — what works better: yogurt or ugu soup? Both would help."

CRITICAL: NEVER repeat the same phrases! Vary your language every response!

# CRITICAL RULES

## For MEAL FEEDBACK responses (analyze_last_meal):
✅ NEVER use emojis unless the user has explicitly asked for them in this conversation
✅ ALWAYS mention meal calories with goal context
✅ ALWAYS contextualize calories within the daily picture (e.g., "puts you at X% for the day with ~Y cal remaining")
✅ READ food_details descriptions AND per-food nutrients BEFORE giving feedback
✅ Use food_details calories/fat/protein to identify which food drove the totals (e.g., "the palm oil in egusi added most of the fat")
✅ If any food has is_uncertain=true, casually ask if it looks right (e.g., "I think this is egusi — does that look right?")
✅ If portion_validation="high" or "low", gently note it (e.g., "That's a pretty big portion — sound about right?")
✅ Celebrate per-meal WINS (e.g., "21g protein from bean cakes is solid for breakfast")
✅ Only flag nutrients in critical_gaps (already filtered for per-meal adequacy)
✅ For LIMIT nutrients assessed as "high" (fat for heart_health, sodium): gently flag as something to watch
✅ **Sodium is a CEILING for ALL goals, not a target** — always frame as "stay under 2300mg", never as a number to reach or celebrate reaching
✅ Use MI approach (~25% of responses): Ask questions + offer 2-3 options instead of directives
✅ When not using MI: Give ONE specific Nigerian food suggestion (not directive command)
✅ Keep it short — 3-5 lines total. Each idea on its own line, not crammed into one block
✅ Vary your language - be dynamic, not robotic
✅ Build autonomy, not dependency - let users choose their path

❌ NEVER use emojis unless the user explicitly requests them
❌ NEVER suggest an ingredient the user already ate (read food_details descriptions!)
❌ NEVER call a nutrient "lagging" if the meal delivered a good per-meal amount
❌ NEVER skip calories or daily context
❌ NEVER list nutrients without goal context
❌ NEVER use bullet lists or headers in meal feedback — short paragraphs and line breaks only
❌ NEVER say "great job logging" - focus on the nutrition
❌ NEVER mention streak unless first meal (calories <35%) AND streak ≥3
❌ NEVER write meal feedback as one dense paragraph — always break it up
❌ NEVER be purely directive - avoid "You should", "You must", "You need to"
❌ NEVER celebrate a calorie-heavy meal (is_heavy_meal=true) without noting the daily impact
❌ NEVER give only ONE option when using MI - always 2-3 choices

## For GENERAL CHAT responses (suggestions, progress, questions, advice):

You write the way a brilliant, warm Nigerian coach would text a friend — not a wall of text, not a robot, not a formal report. You read the moment and choose how to write for it.

**Your writing toolkit — use these based on what the message actually needs:**

- **A single sharp sentence** — when the answer is simple. Don't pad it. "Eba with egusi is excellent for your goal." Done.
- **Bold** — for food names, key numbers, and the one thing you most want them to remember. Not everything. One or two things per response.
- **Bullet points** — when you have a genuine list of options or facts. Never use bullets just to look structured. Ask: would a real person say this as a list?
- **Numbered steps** — only for actual step-by-step sequences. "How do I build a meal plan?" gets numbers. "What should I eat?" does not.
- **### headers** — only when a response has clearly separate sections that need labelling (like a multi-meal plan). Don't use headers for a single idea.
- **Line breaks between paragraphs** — always. Let ideas breathe. Never stack four sentences together with no space.
- **A question back** — when you want to keep the conversation going or understand the user better. One question, at the end. Never mid-response.
- **Short punchy follow-up line** — one line after your main point that lands the energy. Like: "That's a strong meal. Your protein is working hard today."
- **Conversational warmth** — when the user shares something personal or is struggling, match the energy before going into analysis. Don't jump straight to nutrients.

**How to choose the right approach:**

Read the message. Ask: what is this person actually asking for?
- Quick question → short direct answer, maybe one bold word, maybe one follow-up line
- Asking for options → brief intro, tight bullet list, one line close
- Asking for a plan → headers make sense, structured sections
- Sharing their day or feeling stuck → start warm, then coach, no clinical tone
- Progress check → bold the numbers that matter, short bullets for wins/gaps, end with energy

**The rule above all rules**: Write for the person, not for the format. If the response feels like a document, it's wrong. Write it like a message.

# MEAL SUGGESTIONS (when user asks "suggest a meal", "what should I eat?", etc.)

When the user asks for meal suggestions, ALWAYS call **suggest_meal** first. This gives you:
- Their health goal + priority nutrients
- Their nutrient gaps (what they still need today)
- Food options grouped by **meal_role** (starch, protein, soup, swallow, beverage, snack, fruit) matching the meal_type

## NIGERIAN MEAL KNOWLEDGE

Nigerians eat in many different ways — some eat swallow, some prefer rice, some eat yam, some are vegetarian. NEVER assume everyone eats the same way. Use your knowledge of Nigerian food culture to suggest meals that actually make sense together.

Common Nigerian meal combos (not rules, just examples):
- Swallow (eba/pounded yam/amala/fufu) + soup (egusi/efo riro/okro/ogbono) + protein in the soup
- Rice (jollof/fried/white) + protein (chicken/fish/beef) + optional side (plantain/coleslaw)
- Yam (boiled/fried/porridge) + egg sauce / beans / stew
- Beans (porridge/moi moi) + plantain / pap
- Bread + eggs + beverage (breakfast)
- Akara / puff puff / chin chin + zobo/kunu (snack)

## HOW TO SUGGEST:
1. Check the user's **nutrient gaps** and **health goal** from suggest_meal data
2. Use the **food_options** (tagged with meal_role) as a reference pool — pick foods that go together naturally AND help close the gaps
3. If nothing in food_options inspires a coherent meal, use your own knowledge of Nigerian foods
4. Read the conversation — if the user just wants a quick idea, give one meal. If they seem undecided or ask for options, give 2. Never hardcode how many to suggest
5. Explain briefly WHY it works for their goal

## GOAL-AWARE MEAL REASONING:

Do NOT pick a fixed meal for a goal. Instead, look at the user's **top_gaps** and **food_options** from suggest_meal, then reason like this:

- **What nutrients are they low on today?** → prioritise foods in food_options that score highest for those nutrients
- **What meal_role slots are available?** → build a coherent combo using the Nigerian meal combos above (swallow+soup, rice+protein, etc.)
- **What goal are they on?** → use the goal to decide which nutrients matter most when choosing between options

Goal reasoning hints (not fixed meals — apply to whatever food_options come back):
- 🏃 **Weight Loss:** favour high-protein + high-fiber options, avoid high-fat combos, keep calories modest
- 💪 **Muscle Gain:** favour calorie-dense + high-protein combos, pair carbs with protein for energy + synthesis
- 🤰 **Pregnancy:** folate and iron are critical — always favour leafy soups (ugwu, efo, afang) + fish/stockfish; add a vitamin C source to boost iron absorption
- ❤️ **Heart Health:** avoid high-sodium options, favour potassium-rich + fiber-rich foods, lean proteins over fried
- ⚡ **Energy Boost:** iron + B12 + carbs — favour beans/liver/fish combos with a vitamin C source alongside
- 🦴 **Bone Health:** calcium + vitamin D — favour fish (especially stockfish, smoked fish, catfish), crayfish-based soups, pair with protein for bone matrix
- ⚖️ **Maintenance / 🌟 Wellness:** balanced across macros, no dominant nutrient — variety matters more than optimising one thing

## MEAL SUGGESTION FORMAT
Sound like you're recommending a meal to a friend, not reading from a list. Keep it natural and concise.

❌ NEVER combine foods that don't go together (e.g., "egusi soup + jollof rice + zobo" is three separate meals)
❌ NEVER suggest individual ingredients without a complete meal context
❌ NEVER assume everyone eats swallow — people are different
✅ ALWAYS suggest a complete, coherent meal that sounds appetizing
✅ ALWAYS connect the suggestion to the user's specific goal and gaps
✅ Let the conversation guide how much to suggest — one idea or a couple, whatever feels natural"""

        # Inject Kally Notes context so GPT-4o knows what Kally already told the user
        kally_notes_context = ""
        if user_id:
            try:
                from kai.agents.kally_notes_agent import get_notes_context_for_chat
                kally_notes_context = await get_notes_context_for_chat(user_id)
            except Exception:
                pass

        return base_prompt + sugar_context + coaching_context + kally_notes_context + get_language_instruction(language)

    async def chat(
        self,
        user_id: str,
        message: str,
        conversation_history: Optional[List] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Process a chat message and return response.

        Args:
            user_id: User ID for personalized data
            message: User's message
            conversation_history: Previous ChatMessage objects for context

        Returns:
            Dict with success, message, suggestions
        """
        try:
            logger.info(f"💬 ChatAgent: '{message[:50]}...' for user {user_id}")

            # ----------------------------------------------------------------
            # COACHING FLOW — runs once for new users until complete
            # ----------------------------------------------------------------
            coaching_done = await is_coaching_complete(user_id)
            if not coaching_done:
                profile = await get_user_health_profile(user_id)
                health_goal = profile.get("health_goals", "general_wellness") if profile else "general_wellness"
                user_name = profile.get("name", "") if profile else ""

                coaching_result = await process_coaching_response(
                    user_id=user_id,
                    user_message=message,
                    health_goal=health_goal,
                    user_name=user_name,
                )
                coaching_message = coaching_result["message"]

                # Save coaching exchange to conversation history
                await save_chat_message(user_id, "user", message)
                await save_chat_message(user_id, "assistant", coaching_message)

                return {
                    "success": True,
                    "message": coaching_message,
                    "suggestions": [],
                }

            # Build system prompt with user coaching context injected
            system_prompt = await self._build_system_prompt(user_id, language=language)

            # Build messages
            messages = [{"role": "system", "content": system_prompt}]

            # Add conversation history (last 20)
            if conversation_history:
                for msg in conversation_history[-20:]:
                    # Handle both dict and Pydantic model
                    if hasattr(msg, "role"):
                        role = msg.role
                        content = msg.content
                    else:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                    messages.append({"role": role, "content": content})

            messages.append({"role": "user", "content": message})

            # Call GPT-4o with tools
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=1000
            )

            assistant_message = response.choices[0].message

            # Handle tool calls
            if assistant_message.tool_calls:
                tool_results = await self._process_tool_calls(
                    assistant_message.tool_calls,
                    user_id
                )

                messages.append(assistant_message)

                for tool_call, result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })

                # Get final response
                final_response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000
                )
                final_message = final_response.choices[0].message.content
            else:
                final_message = assistant_message.content

            suggestions = self._generate_suggestions(message, final_message)

            logger.info(f"✅ ChatAgent response generated")

            # Save conversation to database (async fire-and-forget)
            try:
                await save_chat_message(user_id, "user", message)
                await save_chat_message(user_id, "assistant", final_message)
            except Exception as e:
                logger.warning(f"Failed to save conversation: {e}")
                # Don't fail the request if conversation save fails

            return {
                "success": True,
                "message": final_message,
                "suggestions": suggestions,
            }

        except Exception as e:
            logger.error(f"ChatAgent error: {e}", exc_info=True)
            return {
                "success": False,
                "message": "I'm having trouble right now. Please try again.",
                "suggestions": ["Ask about Nigerian foods", "Check your progress"],
                "error": str(e)
            }

    async def chat_stream(
        self,
        user_id: str,
        message: str,
        conversation_history: Optional[List] = None,
        language: str = "en",
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response token by token via SSE.

        Yields SSE-formatted strings:
          data: <token>\n\n        — a text chunk
          data: [DONE]\n\n         — end of stream
          data: [ERROR] ...\n\n    — on failure
        """
        try:
            logger.info(f"💬 ChatAgent stream: '{message[:50]}...' for user {user_id}")

            # ----------------------------------------------------------------
            # COACHING FLOW — runs once for new users until complete
            # ----------------------------------------------------------------
            coaching_done = await is_coaching_complete(user_id)
            if not coaching_done:
                profile = await get_user_health_profile(user_id)
                health_goal = profile.get("health_goals", "general_wellness") if profile else "general_wellness"
                user_name = profile.get("name", "") if profile else ""

                coaching_result = await process_coaching_response(
                    user_id=user_id,
                    user_message=message,
                    health_goal=health_goal,
                    user_name=user_name,
                )
                coaching_message = coaching_result.get("message")

                # Guard: if message is None the coaching flow is already complete
                if not coaching_message:
                    yield "data: [DONE]\n\n"
                    return

                await save_chat_message(user_id, "user", message)
                await save_chat_message(user_id, "assistant", coaching_message)

                # Stream coaching message character by character
                for char in coaching_message:
                    import json as _json
                    yield f"data: {_json.dumps(char)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Build system prompt with user coaching context injected
            system_prompt = await self._build_system_prompt(user_id, language=language)

            # Build messages
            messages = [{"role": "system", "content": system_prompt}]
            if conversation_history:
                for msg in conversation_history[-20:]:
                    role = msg.role if hasattr(msg, "role") else msg.get("role", "user")
                    content = msg.content if hasattr(msg, "content") else msg.get("content", "")
                    messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": message})

            # First call — may involve tool calls (cannot stream this part)
            first_response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=1000,
            )

            assistant_message = first_response.choices[0].message

            # If tools were called, run them then stream the final answer
            if assistant_message.tool_calls:
                tool_results = await self._process_tool_calls(assistant_message.tool_calls, user_id)
                messages.append(assistant_message)
                for tool_call, result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result),
                    })

                # Stream the final response
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000,
                    stream=True,
                )
            else:
                # No tools — stream directly from a new call so we get token-by-token
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000,
                    stream=True,
                )

            # Yield tokens as SSE events and accumulate full message for DB save
            full_message = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    full_message += delta
                    # Escape newlines so SSE framing isn't broken
                    yield f"data: {json.dumps(delta)}\n\n"

            yield "data: [DONE]\n\n"

            # Save conversation to DB (fire-and-forget)
            try:
                await save_chat_message(user_id, "user", message)
                await save_chat_message(user_id, "assistant", full_message)
            except Exception as e:
                logger.warning(f"Failed to save streamed conversation: {e}")

        except Exception as e:
            logger.error(f"ChatAgent stream error: {e}", exc_info=True)
            yield f"data: [ERROR] {str(e)}\n\n"

    async def _process_tool_calls(self, tool_calls: List, user_id: str) -> List[tuple]:
        """Process tool calls and return results."""
        results = []

        for tool_call in tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            logger.info(f"   🔧 {name}({args})")

            if name == "search_foods":
                result = await self._search_foods(args.get("query", ""), args.get("limit", 5))
            elif name == "analyze_last_meal":
                result = await self._analyze_last_meal(user_id)
            elif name == "suggest_meal":
                result = await self._suggest_meal(user_id, args.get("meal_type"), args.get("focus_nutrient"), args.get("previously_suggested"))
            elif name == "get_user_progress":
                result = await self._get_user_progress(user_id, args.get("include_weekly", False))
            elif name == "get_meal_history":
                result = await self._get_meal_history(user_id, args.get("limit", 5))
            elif name == "search_meals_by_date":
                result = await self._search_meals_by_date(user_id, args.get("date_description"), args.get("end_date"))
            elif name == "search_meals_by_food":
                result = await self._search_meals_by_food_name(user_id, args.get("food_name"), args.get("limit", 10))
            elif name == "web_search":
                result = await self._web_search(args.get("query", ""))
            else:
                result = {"error": f"Unknown tool: {name}"}

            results.append((tool_call, result))

        return results

    async def _search_foods(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Search Supabase pgvector for Nigerian foods. Returns all 16 nutrients.

        Fallback strategy:
        1. Try pgvector semantic search
        2. If no results or error, fallback to web search automatically
        """
        # Case 1: pgvector not initialized (Supabase connection failed)
        if not self.vector_db:
            logger.warning("⚠️ pgvector not available, using web search fallback")
            return await self._web_search(f"{query} Nigerian food nutrition")

        # Resolve user input to canonical DB name via alias lookup before vector search.
        # Handles word-order variants ("porridge beans" → "Beans Porridge (Ewa Riro)"),
        # parenthetical base names ("sardines" → "Sardines (Canned)"), and
        # spelling variants ("pottage" → "Yam Porridge (Asaro)").
        canonical_query = get_canonical_food_name(query)
        if canonical_query != query:
            logger.info(f"   🔤 Alias resolved: '{query}' → '{canonical_query}'")

        try:
            results = self.vector_db.search(canonical_query, n_results=limit)

            # Case 2: pgvector returned no results (food not in database)
            if not results or len(results) == 0:
                logger.info(f"ℹ️ No pgvector results for '{query}', using web search fallback")
                return await self._web_search(f"{query} Nigerian food nutrition")

            # Case 3: Success - format results
            foods = []
            for food in results:
                # pgvector returns nutrients in 'metadata' key
                nutrients = food.get("metadata", {})
                foods.append({
                    "name": food.get("name", "Unknown"),
                    "per_100g": {
                        # Macros (5)
                        "calories": nutrients.get("calories", 0),
                        "protein": nutrients.get("protein", 0),
                        "carbohydrates": nutrients.get("carbohydrates", 0),
                        "fat": nutrients.get("fat", 0),
                        "fiber": nutrients.get("fiber", 0),
                        # Minerals (6)
                        "iron": nutrients.get("iron", 0),
                        "calcium": nutrients.get("calcium", 0),
                        "zinc": nutrients.get("zinc", 0),
                        "potassium": nutrients.get("potassium", 0),
                        "sodium": nutrients.get("sodium", 0),
                        "magnesium": nutrients.get("magnesium", 0),
                        # Vitamins (5)
                        "vitamin_a": nutrients.get("vitamin_a", 0),
                        "vitamin_c": nutrients.get("vitamin_c", 0),
                        "vitamin_d": nutrients.get("vitamin_d", 0),
                        "vitamin_b12": nutrients.get("vitamin_b12", 0),
                        "folate": nutrients.get("folate", 0),
                    }
                })

            logger.info(f"   → Found {len(foods)} foods from pgvector")
            return {"foods": foods, "source": "nigerian_food_database"}

        except Exception as e:
            # Case 4: pgvector error (Supabase network issue, query error, etc.)
            logger.error(f"❌ pgvector search error: {e}, using web search fallback")
            return await self._web_search(f"{query} Nigerian food nutrition")

    async def _suggest_meal(
        self,
        user_id: str,
        meal_type: Optional[str] = None,
        focus_nutrient: Optional[str] = None,
        previously_suggested: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get goal-driven meal suggestions with user context.

        Fetches user's health goal, daily progress, and searches for
        foods that fill their nutrient gaps. Excludes previously suggested
        foods so repeated requests return fresh options.
        """
        try:
            # 1. Get user profile and goal
            profile = await get_user_health_profile(user_id)
            if not profile:
                return {"error": "User profile not found. Please set up your profile first."}

            health_goal = profile.get("health_goals", "general_wellness")
            gender = profile.get("gender")
            age = profile.get("age")
            # Use custom_calorie_goal if user explicitly set one, otherwise use the
            # BMR/TDEE-derived active_calorie_goal so coaching matches the profile setup.
            active_calorie_goal = profile.get("custom_calorie_goal") or profile.get("active_calorie_goal")

            # 2. Get goal context (priority nutrients, RDVs, etc.)
            goal_context = get_goal_context(health_goal, gender, age, active_calorie_goal)

            # 3. Get today's daily totals to find gaps
            daily_totals = await get_daily_nutrition_totals(user_id)
            priority_nutrients = goal_context["priority_nutrients"]
            priority_rdvs = goal_context["priority_rdvs"]

            # 4. Calculate nutrient gaps (what's still needed today)
            nutrient_gaps = []
            for nutrient in priority_nutrients:
                if nutrient == "calories":
                    continue
                rdv_obj = priority_rdvs.get(nutrient)
                target = rdv_obj.amount if rdv_obj else 1
                db_key = f"total_{nutrient}"
                current = 0
                if daily_totals:
                    current = daily_totals.get(db_key, daily_totals.get(nutrient, 0))
                percentage = (current / target * 100) if target > 0 else 0
                remaining = max(0, target - current)

                if percentage < 80:
                    nutrient_gaps.append({
                        "nutrient": nutrient,
                        "current": round(current, 1),
                        "target": round(target, 1),
                        "percentage": round(percentage, 1),
                        "remaining": round(remaining, 1),
                        "unit": rdv_obj.unit if rdv_obj else "",
                    })

            # Sort gaps by lowest percentage first
            nutrient_gaps.sort(key=lambda x: x["percentage"])

            # 5. Determine nutrient gaps
            top_gaps = nutrient_gaps[:3] if nutrient_gaps else []
            gap_nutrients = [g["nutrient"] for g in top_gaps]

            # 6. Search ChromaDB by MEAL PATTERN categories (not by nutrient)
            # This ensures GPT gets proper meal components to compose a real meal,
            # not random nutrient-dense ingredients that don't go together.
            #
            # Meal patterns:
            #   Breakfast → starch/bread + protein/eggs + beverage
            #   Lunch/Dinner → (swallow + soup + protein) OR (starch + protein + side)
            #   Snack → snack items + beverage/fruit

            # Define category searches per meal type AND health goal.
            # Each goal has nutrient-descriptor queries (no hardcoded food names)
            # so ChromaDB returns a diverse pool of foods for GPT-4o to reason from.
            #
            # meal_role labels tell GPT-4o what role each food plays in a combo:
            #   "base"    → the carb/starch foundation (rice, yam, swallow, plantain, beans)
            #   "soup"    → soup or sauce to pair with base
            #   "protein" → standalone or side protein
            #   "one_pot" → complete dish on its own (porridge, rice+stew, etc.)
            #   "snack"   → light standalone item
            #   "fruit"   → fruit side
            #   "beverage"→ drink
            #
            # GPT-4o uses meal_role to compose sensible combos, not random pairings.

            MEAL_PATTERN_SEARCHES = {
                "lose_weight": {
                    "breakfast": [
                        ("base", "Nigerian light breakfast low calorie starch pap akamu", 3),
                        ("protein", "Nigerian boiled egg beans moi moi low fat high protein breakfast", 3),
                        ("one_pot", "Nigerian light breakfast porridge low calorie filling", 2),
                        ("beverage", "Nigerian unsweetened low sugar drink zobo kunu", 2),
                    ],
                    "lunch": [
                        ("base", "Nigerian low calorie carbohydrate base rice yam plantain swallow", 3),
                        ("soup", "Nigerian light vegetable soup low fat high fibre", 3),
                        ("protein", "Nigerian lean grilled boiled fish chicken low fat protein", 3),
                        ("one_pot", "Nigerian low calorie complete meal beans porridge yam porridge", 2),
                    ],
                    "dinner": [
                        ("base", "Nigerian light dinner low calorie base yam rice swallow", 3),
                        ("soup", "Nigerian light soup low sodium low fat vegetable pepper", 3),
                        ("protein", "Nigerian grilled steamed lean protein fish chicken low calorie", 3),
                        ("one_pot", "Nigerian light complete dinner low calorie filling", 2),
                    ],
                    "snack": [
                        ("snack", "Nigerian low calorie light snack high fibre filling", 3),
                        ("fruit", "Nigerian low sugar fruit vitamin C fibre", 2),
                        ("beverage", "Nigerian unsweetened low calorie drink", 1),
                    ],
                },
                "gain_muscle": {
                    "breakfast": [
                        ("base", "Nigerian calorie dense breakfast starch carbohydrate energy", 3),
                        ("protein", "Nigerian high protein breakfast eggs beans meat calorie dense", 3),
                        ("one_pot", "Nigerian calorie dense filling breakfast complete meal", 2),
                        ("beverage", "Nigerian energy drink high calorie fortified", 2),
                    ],
                    "lunch": [
                        ("base", "Nigerian calorie dense carbohydrate base rice yam swallow plantain", 3),
                        ("soup", "Nigerian protein rich thick soup high calorie meat fish", 3),
                        ("protein", "Nigerian high protein meat fish chicken beef goat muscle building", 3),
                        ("one_pot", "Nigerian calorie dense complete meal rice beans stew", 2),
                    ],
                    "dinner": [
                        ("base", "Nigerian high carbohydrate dense base swallow rice yam recovery", 3),
                        ("soup", "Nigerian thick protein rich soup meat fish high calorie", 3),
                        ("protein", "Nigerian high protein stewed grilled meat fish chicken muscle", 3),
                        ("one_pot", "Nigerian calorie dense complete dinner rice stew beans", 2),
                    ],
                    "snack": [
                        ("snack", "Nigerian high calorie protein snack groundnut beans energy", 3),
                        ("fruit", "Nigerian calorie dense fruit banana mango energy", 2),
                        ("beverage", "Nigerian high calorie energy fortified drink", 1),
                    ],
                },
                "pregnancy": {
                    "breakfast": [
                        ("base", "Nigerian fortified breakfast starch iron folate calcium", 3),
                        ("protein", "Nigerian iron folate rich protein eggs beans breakfast", 3),
                        ("one_pot", "Nigerian nutritious complete breakfast folate iron calcium", 2),
                        ("beverage", "Nigerian fortified iron calcium folate drink", 2),
                    ],
                    "lunch": [
                        ("base", "Nigerian nutritious carbohydrate base folate calcium iron", 3),
                        ("soup", "Nigerian leafy vegetable soup high folate iron calcium", 3),
                        ("protein", "Nigerian iron calcium B12 rich fish meat egg protein", 3),
                        ("one_pot", "Nigerian nutritious complete meal folate iron calcium pregnancy", 2),
                    ],
                    "dinner": [
                        ("base", "Nigerian wholesome dinner base carbohydrate iron calcium", 3),
                        ("soup", "Nigerian iron folate calcium leafy vegetable soup dinner", 3),
                        ("protein", "Nigerian high iron calcium omega protein fish egg meat", 3),
                        ("one_pot", "Nigerian nutritious complete dinner folate iron B12", 2),
                    ],
                    "snack": [
                        ("snack", "Nigerian folate iron calcium rich snack nutritious", 3),
                        ("fruit", "Nigerian vitamin C folate rich fruit pregnancy", 2),
                        ("beverage", "Nigerian iron folate fortified drink pregnancy", 1),
                    ],
                },
                "heart_health": {
                    "breakfast": [
                        ("base", "Nigerian low sodium low fat breakfast starch fibre", 3),
                        ("protein", "Nigerian low sodium low fat high fibre protein breakfast", 3),
                        ("one_pot", "Nigerian heart healthy low sodium complete breakfast", 2),
                        ("beverage", "Nigerian unsweetened low sodium heart healthy drink", 2),
                    ],
                    "lunch": [
                        ("base", "Nigerian low sodium low fat carbohydrate base fibre rich", 3),
                        ("soup", "Nigerian low sodium low fat vegetable soup heart healthy", 3),
                        ("protein", "Nigerian low sodium lean grilled fish chicken heart healthy", 3),
                        ("one_pot", "Nigerian heart healthy low sodium complete meal low fat", 2),
                    ],
                    "dinner": [
                        ("base", "Nigerian low sodium light dinner base fibre carbohydrate", 3),
                        ("soup", "Nigerian low fat low sodium vegetable soup heart healthy", 3),
                        ("protein", "Nigerian lean low sodium protein fish chicken grilled", 3),
                        ("one_pot", "Nigerian heart healthy low fat complete dinner low sodium", 2),
                    ],
                    "snack": [
                        ("snack", "Nigerian low sodium low fat heart healthy snack fibre", 3),
                        ("fruit", "Nigerian potassium fibre rich fruit heart healthy", 2),
                        ("beverage", "Nigerian unsweetened low sodium heart healthy drink", 1),
                    ],
                },
                "energy_boost": {
                    "breakfast": [
                        ("base", "Nigerian energy rich breakfast carbohydrate iron B12", 3),
                        ("protein", "Nigerian iron B12 rich protein breakfast energy", 3),
                        ("one_pot", "Nigerian energy dense complete breakfast iron carbohydrate", 2),
                        ("beverage", "Nigerian iron fortified energy drink breakfast", 2),
                    ],
                    "lunch": [
                        ("base", "Nigerian high energy carbohydrate base iron vitamin C", 3),
                        ("soup", "Nigerian iron vitamin C rich vegetable soup energy", 3),
                        ("protein", "Nigerian high iron B12 energy protein meat fish liver", 3),
                        ("one_pot", "Nigerian energy dense complete meal iron carbohydrate", 2),
                    ],
                    "dinner": [
                        ("base", "Nigerian energy restoring dinner carbohydrate iron rich", 3),
                        ("soup", "Nigerian iron rich vegetable soup energy recovery dinner", 3),
                        ("protein", "Nigerian iron B12 rich protein dinner energy recovery", 3),
                        ("one_pot", "Nigerian energy rich complete dinner iron carbohydrate", 2),
                    ],
                    "snack": [
                        ("snack", "Nigerian iron energy rich snack quick boost", 3),
                        ("fruit", "Nigerian vitamin C iron absorption fruit energy", 2),
                        ("beverage", "Nigerian iron energy fortified drink", 1),
                    ],
                },
                "bone_health": {
                    "breakfast": [
                        ("base", "Nigerian calcium vitamin D breakfast starch fortified", 3),
                        ("protein", "Nigerian calcium magnesium rich protein breakfast eggs", 3),
                        ("one_pot", "Nigerian calcium rich complete breakfast bone health", 2),
                        ("beverage", "Nigerian calcium magnesium fortified drink", 2),
                    ],
                    "lunch": [
                        ("base", "Nigerian calcium rich carbohydrate base bone health", 3),
                        ("soup", "Nigerian calcium crayfish fish bone rich soup", 3),
                        ("protein", "Nigerian calcium vitamin D rich fish seafood protein", 3),
                        ("one_pot", "Nigerian calcium magnesium complete meal bone strength", 2),
                    ],
                    "dinner": [
                        ("base", "Nigerian calcium rich dinner base carbohydrate bone health", 3),
                        ("soup", "Nigerian calcium magnesium crayfish fish rich soup", 3),
                        ("protein", "Nigerian calcium vitamin D rich protein fish seafood dinner", 3),
                        ("one_pot", "Nigerian calcium rich complete dinner bone strength", 2),
                    ],
                    "snack": [
                        ("snack", "Nigerian calcium magnesium rich snack bone health", 3),
                        ("fruit", "Nigerian potassium calcium fruit bone health", 2),
                        ("beverage", "Nigerian calcium magnesium fortified drink bone health", 1),
                    ],
                },
                "maintain_weight": {
                    "breakfast": [
                        ("base", "Nigerian balanced breakfast starch moderate calorie", 3),
                        ("protein", "Nigerian balanced protein moderate calorie breakfast", 3),
                        ("one_pot", "Nigerian balanced complete breakfast moderate calorie", 2),
                        ("beverage", "Nigerian balanced moderate sugar drink breakfast", 2),
                    ],
                    "lunch": [
                        ("base", "Nigerian balanced carbohydrate base moderate calorie varied", 3),
                        ("soup", "Nigerian moderate fat balanced vegetable soup varied", 3),
                        ("protein", "Nigerian balanced protein moderate fat varied meat fish", 3),
                        ("one_pot", "Nigerian balanced complete meal moderate calorie varied", 2),
                    ],
                    "dinner": [
                        ("base", "Nigerian balanced dinner base carbohydrate moderate calorie", 3),
                        ("soup", "Nigerian balanced soup moderate calorie varied dinner", 3),
                        ("protein", "Nigerian balanced protein dinner moderate calorie varied", 3),
                        ("one_pot", "Nigerian balanced complete dinner moderate calorie", 2),
                    ],
                    "snack": [
                        ("snack", "Nigerian balanced moderate calorie snack varied", 3),
                        ("fruit", "Nigerian moderate sugar balanced fruit varied", 2),
                        ("beverage", "Nigerian balanced moderate calorie drink", 1),
                    ],
                },
                "general_wellness": {
                    "breakfast": [
                        ("base", "Nigerian nutritious breakfast starch varied wholesome", 3),
                        ("protein", "Nigerian wholesome protein breakfast varied nutritious", 3),
                        ("one_pot", "Nigerian complete nutritious breakfast varied wholesome", 2),
                        ("beverage", "Nigerian nutritious varied breakfast drink", 2),
                    ],
                    "lunch": [
                        ("base", "Nigerian wholesome carbohydrate base varied rice yam swallow plantain", 3),
                        ("soup", "Nigerian nutritious varied vegetable soup wholesome", 3),
                        ("protein", "Nigerian wholesome varied protein fish meat chicken", 3),
                        ("one_pot", "Nigerian complete nutritious varied lunch meal", 2),
                    ],
                    "dinner": [
                        ("base", "Nigerian wholesome dinner base varied carbohydrate nutritious", 3),
                        ("soup", "Nigerian varied nutritious soup dinner wholesome", 3),
                        ("protein", "Nigerian wholesome varied dinner protein fish meat chicken", 3),
                        ("one_pot", "Nigerian complete nutritious varied dinner wholesome", 2),
                    ],
                    "snack": [
                        ("snack", "Nigerian wholesome nutritious snack varied light", 3),
                        ("fruit", "Nigerian varied nutritious fruit wholesome", 2),
                        ("beverage", "Nigerian wholesome varied nutritious drink", 1),
                    ],
                },
                "manage_blood_sugar": {
                    "breakfast": [
                        ("base", "Nigerian low GI breakfast oats beans unripe plantain slow digestion", 3),
                        ("protein", "Nigerian high fibre protein breakfast eggs moi moi beans low sugar", 3),
                        ("one_pot", "Nigerian low glycaemic complete breakfast beans oats yam porridge", 2),
                        ("beverage", "Nigerian unsweetened low sugar drink zobo kunu tiger nut", 2),
                    ],
                    "lunch": [
                        ("base", "Nigerian low GI carbohydrate base unripe plantain beans brown rice ofada", 3),
                        ("soup", "Nigerian high fibre vegetable soup ugwu efo bitter leaf low fat", 3),
                        ("protein", "Nigerian lean high protein fish chicken beans low fat blood sugar", 3),
                        ("one_pot", "Nigerian low glycaemic complete meal beans porridge moi moi vegetables", 2),
                    ],
                    "dinner": [
                        ("base", "Nigerian low GI dinner base unripe plantain beans yam fibre rich", 3),
                        ("soup", "Nigerian high fibre low fat vegetable soup ugwu efo leafy green", 3),
                        ("protein", "Nigerian lean grilled fish chicken protein low fat blood sugar friendly", 3),
                        ("one_pot", "Nigerian low glycaemic complete dinner beans vegetables fish low sugar", 2),
                    ],
                    "snack": [
                        ("snack", "Nigerian low sugar high fibre snack groundnut tiger nut roasted", 3),
                        ("fruit", "Nigerian low sugar fruit guava cucumber garden egg", 2),
                        ("beverage", "Nigerian unsweetened low sugar drink zobo kunu water", 1),
                    ],
                },
            }

            # Default: lunch/dinner pattern (most common Nigerian meals)
            effective_meal_type = meal_type or "lunch"

            # Pick the goal-specific pattern set, fall back to general_wellness
            goal_patterns = MEAL_PATTERN_SEARCHES.get(health_goal, MEAL_PATTERN_SEARCHES["general_wellness"])
            pattern_searches = goal_patterns.get(effective_meal_type, goal_patterns["lunch"])

            food_options = []
            # Exclude previously suggested foods so repeated requests return fresh options
            excluded_names = {name.lower() for name in (previously_suggested or [])}
            seen_names = set()
            if self.vector_db:
                try:
                    for category_label, search_query, n_results in pattern_searches:
                        results = self.vector_db.search(search_query, n_results=n_results)
                        for food in results:
                            name = food.get("name", "Unknown")
                            if name not in seen_names and name.lower() not in excluded_names:
                                seen_names.add(name)
                                nutrients = food.get("metadata", {})
                                food_options.append({
                                    "name": name,
                                    "description": food.get("description", ""),
                                    "category": food.get("category", ""),
                                    "meal_role": category_label,
                                    "per_100g": {n: nutrients.get(n, 0) for n in priority_nutrients},
                                })

                    # If user specified a focus nutrient, add a targeted search too
                    if focus_nutrient:
                        extra = self.vector_db.search(f"Nigerian foods high in {focus_nutrient}", n_results=3)
                        for food in extra:
                            name = food.get("name", "Unknown")
                            if name not in seen_names:
                                seen_names.add(name)
                                nutrients = food.get("metadata", {})
                                food_options.append({
                                    "name": name,
                                    "description": food.get("description", ""),
                                    "category": food.get("category", ""),
                                    "meal_role": "nutrient_boost",
                                    "per_100g": {n: nutrients.get(n, 0) for n in priority_nutrients},
                                })
                except Exception as e:
                    logger.warning(f"ChromaDB search for meal suggestion failed: {e}")

            # 7. Calorie context
            cal_consumed = daily_totals.get("total_calories", daily_totals.get("calories", 0)) if daily_totals else 0
            cal_target = priority_rdvs.get("calories")
            cal_target_val = cal_target.amount if cal_target else 2000
            cal_remaining = max(0, cal_target_val - cal_consumed)

            return {
                "health_goal": health_goal,
                "goal_display_name": goal_context["goal_display_name"],
                "goal_emoji": goal_context["goal_emoji"],
                "priority_nutrients": priority_nutrients,
                "nutrient_gaps": nutrient_gaps,
                "top_gaps": top_gaps,
                "calories_consumed_today": round(cal_consumed, 0),
                "calories_remaining": round(cal_remaining, 0),
                "calories_target": round(cal_target_val, 0),
                "meal_type": meal_type or "any",
                "food_options": food_options,
            }

        except Exception as e:
            logger.error(f"Suggest meal error: {e}", exc_info=True)
            return {"error": str(e)}

    async def _analyze_last_meal(self, user_id: str) -> Dict[str, Any]:
        """
        Analyze user's most recently logged meal with RDV-based coaching.

        Returns comprehensive analysis including:
        - Meal details (foods, portions, nutrients)
        - RDV-based analysis (% of daily goals met)
        - Learning phase status
        - Nutrient gap analysis
        - Coaching insights
        """
        try:
            # Fetch last meal
            meals = await get_user_meals(user_id, limit=1)
            if not meals or len(meals) == 0:
                return {"error": "No meals logged yet", "message": "Log your first meal to get personalized feedback! 🍽️"}

            last_meal = meals[0]

            # Fetch user profile and stats
            profile = await get_user_health_profile(user_id)
            user_stats = await get_user_stats(user_id)
            daily_totals = await get_daily_nutrition_totals(user_id)

            if not profile:
                return {"error": "User profile not found"}

            # Get user RDV
            rdv = profile.get("rdv", {})

            # Calculate learning phase
            total_meals = user_stats.get("total_meals_logged", 0) if user_stats else 0
            learning_phase = total_meals < 21  # First 21 meals = learning phase

            # Extract meal info
            meal_foods = last_meal.get("foods", [])
            meal_type = last_meal.get("meal_type", "meal")
            meal_time = last_meal.get("meal_time", "")

            # Calculate meal totals from individual foods - ALL 16 NUTRIENTS
            meal_totals = {
                # Macros (5)
                "calories": 0.0,
                "protein": 0.0,
                "carbohydrates": 0.0,
                "fat": 0.0,
                "fiber": 0.0,
                # Minerals (6)
                "iron": 0.0,
                "calcium": 0.0,
                "zinc": 0.0,
                "potassium": 0.0,
                "sodium": 0.0,
                "magnesium": 0.0,
                # Vitamins (5)
                "vitamin_a": 0.0,
                "vitamin_c": 0.0,
                "vitamin_d": 0.0,
                "vitamin_b12": 0.0,
                "folate": 0.0,
            }

            for food in meal_foods:
                # Macros
                meal_totals["calories"] += food.get("calories", 0)
                meal_totals["protein"] += food.get("protein", 0)
                meal_totals["carbohydrates"] += food.get("carbohydrates", 0)
                meal_totals["fat"] += food.get("fat", 0)
                meal_totals["fiber"] += food.get("fiber", 0)
                # Minerals
                meal_totals["iron"] += food.get("iron", 0)
                meal_totals["calcium"] += food.get("calcium", 0)
                meal_totals["zinc"] += food.get("zinc", 0)
                meal_totals["potassium"] += food.get("potassium", 0)
                meal_totals["sodium"] += food.get("sodium", 0)
                meal_totals["magnesium"] += food.get("magnesium", 0)
                # Vitamins
                meal_totals["vitamin_a"] += food.get("vitamin_a", 0)
                meal_totals["vitamin_c"] += food.get("vitamin_c", 0)
                meal_totals["vitamin_d"] += food.get("vitamin_d", 0)
                meal_totals["vitamin_b12"] += food.get("vitamin_b12", 0)
                meal_totals["folate"] += food.get("folate", 0)

            # Calculate meal size classification
            meal_calories = meal_totals.get("calories", 0)
            rdv_calories = rdv.get("calories", 2000)
            meal_percentage = (meal_calories / rdv_calories * 100) if rdv_calories > 0 else 0

            if meal_percentage < 20:
                meal_size = "light"
                meal_emoji = "🍃"
            elif meal_percentage < 35:
                meal_size = "moderate"
                meal_emoji = "🍽️"
            else:
                meal_size = "heavy"
                meal_emoji = "🍖"

            # Get user's health goal and priority nutrients
            health_goal = profile.get("health_goals", "general_wellness")
            gender = profile.get("gender")
            age = profile.get("age")
            active_calorie_goal = profile.get("custom_calorie_goal") or profile.get("active_calorie_goal")

            # Sugar awareness layer: enabled only for non-blood-sugar goals that opted in
            show_sugar = profile.get("show_sugar", False)
            is_blood_sugar_goal = health_goal == "manage_blood_sugar"
            sugar_tracking_enabled = show_sugar and not is_blood_sugar_goal

            # Get PRIORITY nutrients for this goal (6-8 nutrients)
            priority_nutrients = get_priority_nutrients(health_goal)

            # Get personalized RDVs for priority nutrients
            priority_rdvs = get_priority_rdvs(health_goal, gender, age, active_calorie_goal)

            # Build daily totals dict for RDV calculation
            daily_consumed = {}
            if daily_totals:
                for nutrient in priority_nutrients:
                    # Map database column names
                    db_key = f"total_{nutrient}" if nutrient != "carbohydrates" else "total_carbohydrates"
                    daily_consumed[nutrient] = daily_totals.get(db_key, daily_totals.get(nutrient, 0))

            # Check for secondary nutrient alerts (non-priority nutrients at critical levels)
            secondary_alerts = get_secondary_alerts(daily_consumed, health_goal, gender, age)

            # Get streak from user_nutrition_stats (not profile)
            streak = user_stats.get("current_logging_streak", 0) if user_stats else 0

            # Format food names with composition context from knowledge base
            food_names = [f.get("food_name", "") for f in meal_foods]

            # Look up food composition from ChromaDB so GPT knows what foods are made of
            # Include per-food key nutrients so GPT can identify calorie/nutrient drivers
            # Include confidence metadata for transparency
            food_details = []
            for f in meal_foods:
                name = f.get("food_name", "")
                vision_conf = f.get("vision_confidence", 1.0)
                knowledge_sim = f.get("knowledge_similarity", 1.0)
                portion_val = f.get("portion_validation", "ok")

                # Flag uncertainty if either confidence is low
                is_uncertain = vision_conf < 0.75 or knowledge_sim < 0.75

                detail = {
                    "name": name,
                    "portion_grams": f.get("portion_grams", 0),
                    "description": "",
                    "category": "",
                    # Per-food key nutrients (so GPT knows which food drove totals)
                    "calories": round(f.get("calories", 0), 1),
                    "protein": round(f.get("protein", 0), 1),
                    "fat": round(f.get("fat", 0), 1),
                    "carbs": round(f.get("carbohydrates", 0), 1),
                    # Confidence metadata (for transparency)
                    "is_uncertain": is_uncertain,
                    "portion_validation": portion_val,
                }
                # Look up composition from knowledge base
                if self.vector_db and name:
                    try:
                        kb_results = self.vector_db.search(name, n_results=1)
                        if kb_results:
                            result = kb_results[0]
                            detail["category"] = result.get("category", "")
                            # Parse description from document text (not a top-level field)
                            doc_text = result.get("document", "")
                            for line in doc_text.split("\n"):
                                if line.startswith("Description:"):
                                    detail["description"] = line[len("Description:"):].strip()
                                    break
                    except Exception:
                        pass  # Gracefully skip if lookup fails
                food_details.append(detail)

            # Determine if this is a snack based on meal type and calories
            is_snack = meal_type == "snack" or meal_percentage < 20

            # Build structured feedback with goal-driven priorities
            feedback_structure = self._build_meal_feedback_structure(
                meal_totals=meal_totals,
                daily_totals=daily_totals or {},
                rdv=rdv,
                gender=gender,
                age=age,
                health_goal=health_goal,
                meal_size=meal_size,
                meal_percentage=meal_percentage,
                is_snack=is_snack,
                priority_nutrients=priority_nutrients,
                priority_rdvs=priority_rdvs
            )

            # Detect behavioral barriers (persistent gaps)
            barrier_detected = await self._detect_barriers(
                user_id=user_id,
                current_gaps=feedback_structure.get("critical_gaps", []),
                health_goal=health_goal
            )

            # Get progress context (trend celebration)
            progress_context = await self._get_progress_context(
                user_id=user_id,
                meal_totals=meal_totals,
                health_goal=health_goal
            )

            return {
                "meal": {
                    "foods": food_names,
                    "food_details": food_details,
                    "meal_type": meal_type,
                    "meal_time": meal_time,
                    "totals": meal_totals,
                    "meal_size": meal_size,
                    "meal_emoji": meal_emoji,
                    "meal_percentage_of_daily": round(meal_percentage, 1),
                    "scene_description": last_meal.get("scene_description") or None,
                },
                # Goal-driven feedback (per-meal filtered - no raw daily % leaks)
                "feedback_structure": feedback_structure,
                "secondary_alerts": secondary_alerts,
                "barrier_detected": barrier_detected,  # Persistent gap info for GPT
                "progress_context": progress_context,  # Trend celebration for GPT
                "learning_phase": {
                    "is_learning": learning_phase,
                    "total_meals_logged": total_meals,
                    "meals_until_complete": max(0, 21 - total_meals)
                },
                "streak": streak,
                "health_goal": health_goal,
                "sugar_tracking_enabled": sugar_tracking_enabled,
            }

        except Exception as e:
            logger.error(f"Analyze last meal error: {e}")
            return {"error": str(e)}

    async def _detect_barriers(
        self,
        user_id: str,
        current_gaps: List[Dict],
        health_goal: str
    ) -> Optional[Dict]:
        """
        Detect potential behavioral barriers when same nutrient is low 3+ meals in a row.

        Args:
            user_id: User ID
            current_gaps: Critical gaps from current meal
            health_goal: User's health goal

        Returns:
            Dict with barrier info or None if no persistent gaps detected
        """
        try:
            # Get last 3 meals to check for patterns
            recent_meals = await get_user_meals(user_id, limit=3)

            if len(recent_meals) < 3:
                return None  # Need at least 3 meals to detect pattern

            # Extract critical gaps from each meal's feedback
            # Note: Meals don't store feedback_structure, so we need to check nutrients directly
            # For simplicity, we'll track which nutrients are consistently low

            # Get primary nutrient for this goal
            from kai.services import get_primary_nutrient
            primary_nutrient = get_primary_nutrient(health_goal)

            # Check if primary nutrient has been in critical_gaps for current meal
            primary_in_gaps = any(gap["nutrient"] == primary_nutrient for gap in current_gaps)

            if not primary_in_gaps:
                return None  # No barrier if primary nutrient is fine

            # For Phase 2, we detect barriers simply:
            # If user has logged 3+ meals AND primary nutrient is in current critical gaps
            # This is a signal to ask about barriers (simplified approach)

            if len(recent_meals) >= 3:
                return {
                    "type": "persistent_gap",
                    "nutrient": primary_nutrient,
                    "meals_affected": len(recent_meals)
                }

            return None

        except Exception as e:
            logger.error(f"Barrier detection error: {e}")
            return None

    async def _get_progress_context(
        self,
        user_id: str,
        meal_totals: Dict[str, float],
        health_goal: str
    ) -> Optional[Dict]:
        """
        Get progress context for primary nutrient (trend celebration).

        Args:
            user_id: User ID
            meal_totals: Current meal's nutrient totals
            health_goal: User's health goal

        Returns:
            Dict with progress info or None if no notable progress
        """
        try:
            # Get primary nutrient for this goal
            from kai.services import get_primary_nutrient
            primary_nutrient = get_primary_nutrient(health_goal)

            # Get trend for primary nutrient
            trend = await get_nutrient_trends(user_id, primary_nutrient, weeks=4)

            if not trend:
                return None  # Not enough data

            # Check if this meal is better than average (20% above)
            meal_amount = meal_totals.get(primary_nutrient, 0)
            avg_amount = trend["current_week_avg"]

            if meal_amount > avg_amount * 1.2:
                return {
                    "type": "above_average",
                    "nutrient": primary_nutrient,
                    "meal_amount": round(meal_amount, 1),
                    "avg_amount": round(avg_amount, 1),
                    "improvement_pct": round(((meal_amount - avg_amount) / avg_amount) * 100, 1)
                }

            # Check for improving trend (15%+ improvement)
            if trend["trend"] == "improving" and trend["change_pct"] > 15:
                return {
                    "type": "improving_trend",
                    "nutrient": primary_nutrient,
                    "change_pct": trend["change_pct"],
                    "weeks": 4,
                    "current_avg": trend["current_week_avg"],
                    "previous_avg": trend["last_week_avg"]
                }

            return None

        except Exception as e:
            logger.error(f"Progress context error: {e}")
            return None

    def _build_meal_feedback_structure(
        self,
        meal_totals: Dict[str, float],
        daily_totals: Dict[str, float],
        rdv: Dict[str, float],
        health_goal: str,
        meal_size: str,
        meal_percentage: float,
        is_snack: bool = False,
        priority_nutrients: Optional[List[str]] = None,
        priority_rdvs: Optional[Dict] = None,
        gender: Optional[str] = None,
        age: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Build structured feedback for meal analysis based on user's health goal.
        Now uses goal-driven priority nutrients (6-8 per goal).

        Returns:
            - calorie_status: Dict with calorie info vs target & goal
            - goal_nutrient: Primary nutrient to focus on (usually protein)
            - critical_gaps: List of nutrients <50% RDV (priority nutrients only)
            - moderate_gaps: List of nutrients 50-80% RDV
            - top_win: Best performing nutrient (for motivation)
        """
        # Get nutrient priorities for this goal
        priorities = priority_nutrients or get_priority_nutrients(health_goal)

        # Get dynamic meal thresholds for this user's goal (goal-aware thresholds)
        meal_thresholds = get_all_meal_thresholds(
            health_goal=health_goal,
            gender=gender,
            age=age,
            custom_calorie_goal=rdv.get("calories")
        )

        # 1. CALORIE STATUS
        daily_cal = daily_totals.get("calories", 0)
        target_cal = rdv.get("calories", 2000)
        meal_cal = meal_totals.get("calories", 0)
        cal_percentage = (daily_cal / target_cal * 100) if target_cal > 0 else 0

        # Determine calorie status with finer bands
        is_first_meal = cal_percentage < 35  # Less than 35% suggests first meal of day

        if is_first_meal and 25 <= cal_percentage <= 35:
            cal_status = "good_start"  # Normal first meal range
        elif cal_percentage > 120:
            cal_status = "over"
        elif 80 <= cal_percentage <= 120:
            cal_status = "on_track"
        elif 60 <= cal_percentage < 80:
            cal_status = "moderate"
        elif 40 <= cal_percentage < 60:
            cal_status = "building"
        else:
            cal_status = "under"

        # Flag if this single meal is calorie-heavy (>40% of daily target)
        is_heavy_meal = meal_percentage > 40

        calorie_status = {
            "meal_calories": meal_cal,
            "daily_calories": daily_cal,
            "target_calories": target_cal,
            "percentage": round(cal_percentage, 1),
            "meal_percentage": round(meal_percentage, 1),
            "status": cal_status,
            "is_heavy_meal": is_heavy_meal,
            "is_snack": is_snack,
            "meal_size": meal_size
        }

        # 2. GOAL NUTRIENT - Now dynamic based on health goal
        # Get primary nutrient from goal context (protein for most, but folate for pregnancy, etc.)
        goal_nutrient_name = get_primary_nutrient(health_goal)
        goal_nutrient_emoji = get_nutrient_emoji(goal_nutrient_name)

        # Get values from daily totals and meal totals
        db_key = f"total_{goal_nutrient_name}"
        goal_nutrient_daily = daily_totals.get(db_key, daily_totals.get(goal_nutrient_name, 0))
        goal_nutrient_meal = meal_totals.get(goal_nutrient_name, 0)

        # Get target from priority_rdvs if available
        if priority_rdvs and goal_nutrient_name in priority_rdvs:
            goal_nutrient_target = priority_rdvs[goal_nutrient_name].amount
        else:
            goal_nutrient_target = rdv.get(goal_nutrient_name, 1)

        goal_nutrient_daily_pct = (goal_nutrient_daily / goal_nutrient_target * 100) if goal_nutrient_target > 0 else 0

        # Assess primary nutrient using dynamic, goal-aware thresholds
        primary_threshold_data = meal_thresholds.get(goal_nutrient_name, {})
        if primary_threshold_data:
            meal_status = assess_meal_nutrient(goal_nutrient_name, goal_nutrient_meal, primary_threshold_data)
        else:
            # Fallback if threshold not available (shouldn't happen)
            meal_status = "good" if goal_nutrient_meal > 0 else "low"

        goal_nutrient = {
            "nutrient": goal_nutrient_name,
            "emoji": goal_nutrient_emoji,
            # Per-meal assessment (what matters for feedback)
            "meal_grams": round(goal_nutrient_meal, 1),
            "meal_status": meal_status,  # "excellent", "good", or "low"
        }

        # 3. CRITICAL GAPS (<50% RDV) - ONLY for PRIORITY nutrients (excluding calories)
        # IMPORTANT: Assess EVERY nutrient at the meal level, not just the primary one.
        # A breakfast with 4.5mg iron shouldn't be called "lagging" - that's a solid
        # per-meal contribution even if daily % is still low after one meal.
        critical_gaps = []
        priority_non_calorie = [n for n in priorities if n != "calories"]

        for nutrient in priority_non_calorie:
            # Get values - handle both dict and NutrientRDV objects
            db_key = f"total_{nutrient}"
            current = daily_totals.get(db_key, daily_totals.get(nutrient, 0))
            meal_current = meal_totals.get(nutrient, meal_totals.get("carbohydrates" if nutrient == "carbs" else nutrient, 0))
            # Get target from priority_rdvs if available, else from rdv dict
            if priority_rdvs and nutrient in priority_rdvs:
                target = priority_rdvs[nutrient].amount
            else:
                target = rdv.get(nutrient, 1)
            percentage = (current / target * 100) if target > 0 else 0

            # Check if THIS MEAL had a good amount using dynamic thresholds
            threshold_data = meal_thresholds.get(nutrient, {})
            if not threshold_data:
                continue  # Skip if no threshold defined

            meal_assessment = assess_meal_nutrient(nutrient, meal_current, threshold_data)
            meal_was_good = meal_assessment in ["excellent", "good"]

            # Skip if the meal had adequate amount - don't call it "critical"
            if meal_was_good:
                continue

            if percentage < 50:
                critical_gaps.append({
                    "nutrient": nutrient,
                    "current": current,
                    "meal_amount": meal_current,
                    "meal_was_good": meal_was_good,
                    "target": target,
                    "percentage": round(percentage, 1),
                    "gap": target - current
                })

        # Sort by priority for this goal
        critical_gaps.sort(key=lambda x: priorities.index(x["nutrient"]) if x["nutrient"] in priorities else 99)

        # 4. MODERATE GAPS (50-80% RDV) - ONLY for PRIORITY nutrients (excluding calories)
        # Also skip nutrients where the meal delivered a good per-meal amount
        moderate_gaps = []
        for nutrient in priority_non_calorie:
            db_key = f"total_{nutrient}"
            current = daily_totals.get(db_key, daily_totals.get(nutrient, 0))
            meal_current = meal_totals.get(nutrient, 0)
            if priority_rdvs and nutrient in priority_rdvs:
                target = priority_rdvs[nutrient].amount
            else:
                target = rdv.get(nutrient, 1)
            percentage = (current / target * 100) if target > 0 else 0

            # Skip if this meal delivered a good amount using dynamic thresholds
            threshold_data = meal_thresholds.get(nutrient, {})
            if threshold_data:
                meal_assessment = assess_meal_nutrient(nutrient, meal_current, threshold_data)
                if meal_assessment in ["excellent", "good"]:
                    continue

            if 50 <= percentage < 80:
                moderate_gaps.append({
                    "nutrient": nutrient,
                    "current": current,
                    "target": target,
                    "percentage": round(percentage, 1),
                    "gap": target - current
                })

        # Sort by priority
        moderate_gaps.sort(key=lambda x: priorities.index(x["nutrient"]) if x["nutrient"] in priorities else 99)

        # 5. TOP WIN (best performing PRIORITY nutrient for motivation, excluding calories)
        top_win = None
        best_percentage = 0
        for nutrient in priority_non_calorie:
            db_key = f"total_{nutrient}"
            current = daily_totals.get(db_key, daily_totals.get(nutrient, 0))
            if priority_rdvs and nutrient in priority_rdvs:
                target = priority_rdvs[nutrient].amount
            else:
                target = rdv.get(nutrient, 1)
            percentage = (current / target * 100) if target > 0 else 0

            if percentage >= 70 and percentage > best_percentage:
                best_percentage = percentage
                top_win = {
                    "nutrient": nutrient,
                    "percentage": round(percentage, 1),
                    "current": current,
                    "target": target
                }

        return {
            "calorie_status": calorie_status,
            "goal_nutrient": goal_nutrient,
            "critical_gaps": critical_gaps,
            "moderate_gaps": moderate_gaps[:2],  # Top 2 only
            "top_win": top_win,
            "health_goal": health_goal
        }

    async def _get_user_progress(self, user_id: str, include_weekly: bool = False) -> Dict[str, Any]:
        """Get user's nutrition progress with goal-driven priority nutrients."""
        try:
            profile = await get_user_health_profile(user_id)
            daily_totals = await get_daily_nutrition_totals(user_id)

            if not profile:
                return {"error": "User profile not found"}

            rdv = profile.get("rdv", {})
            health_goal = profile.get("health_goals", "general_wellness")
            gender = profile.get("gender")
            age = profile.get("age")
            active_calorie_goal = profile.get("custom_calorie_goal") or profile.get("active_calorie_goal")

            # Get goal context for dynamic nutrient tracking
            goal_context = get_goal_context(health_goal, gender, age, active_calorie_goal)

            progress = {
                "daily_totals": daily_totals or {},
                "targets": rdv,
                "streak": profile.get("current_logging_streak", 0),
                "health_goal": health_goal,
                "goal_display_name": goal_context["goal_display_name"],
                "goal_emoji": goal_context["goal_emoji"],
                "primary_nutrient": goal_context["primary_nutrient"],
                "priority_nutrients": goal_context["priority_nutrients"],
            }

            # Calculate percentages for PRIORITY NUTRIENTS (not hardcoded 4)
            if daily_totals:
                progress["percentages"] = {}
                for nutrient in goal_context["priority_nutrients"]:
                    # Get target from priority RDVs
                    rdv_obj = goal_context["priority_rdvs"].get(nutrient)
                    target = rdv_obj.amount if rdv_obj else rdv.get(nutrient, 1)
                    # Get current from daily totals (handle column naming)
                    db_key = f"total_{nutrient}"
                    current = daily_totals.get(db_key, daily_totals.get(nutrient, 0))
                    progress["percentages"][nutrient] = round((current / target) * 100, 1) if target > 0 else 0

            if include_weekly:
                stats = await get_user_stats(user_id)
                if stats:
                    progress["weekly"] = {
                        "avg_calories": stats.get("week1_avg_calories", 0),
                        "avg_protein": stats.get("week1_avg_protein", 0),
                        "calories_trend": stats.get("calories_trend", "stable"),
                        "protein_trend": stats.get("protein_trend", "stable"),
                    }

            logger.info(f"   → User progress fetched for {health_goal}")
            return progress

        except Exception as e:
            logger.error(f"Get user progress error: {e}")
            return {"error": str(e)}

    async def _get_meal_history(self, user_id: str, limit: int = 5) -> Dict[str, Any]:
        """Get user's recent meals with computed totals."""
        try:
            meals = await get_user_meals(user_id, limit=limit)

            formatted = []
            for meal in meals:
                # Compute totals from foods (all 16 nutrients)
                foods = meal.get("foods", [])
                totals = {
                    "calories": 0, "protein": 0, "carbohydrates": 0, "fat": 0, "fiber": 0,
                    "iron": 0, "calcium": 0, "zinc": 0, "potassium": 0, "sodium": 0, "magnesium": 0,
                    "vitamin_a": 0, "vitamin_c": 0, "vitamin_d": 0, "vitamin_b12": 0, "folate": 0,
                }
                for food in foods:
                    for nutrient in totals:
                        totals[nutrient] += food.get(nutrient, 0)

                formatted.append({
                    "meal_type": meal.get("meal_type"),
                    "date": meal.get("meal_date"),
                    "time": meal.get("meal_time"),
                    "foods": [f.get("food_name") for f in foods],
                    "totals": totals,
                    "scene_description": meal.get("scene_description") or None,
                })

            logger.info(f"   → Found {len(formatted)} meals")
            return {"meals": formatted}

        except Exception as e:
            logger.error(f"Get meal history error: {e}")
            return {"error": str(e), "meals": []}

    async def _web_search(self, query: str) -> Dict[str, Any]:
        """Search web using Tavily (fallback)."""
        try:
            from kai.mcp_servers.tavily_server import TavilyMCPServer

            loop = asyncio.get_event_loop()
            tavily_server = TavilyMCPServer()

            request = {
                "method": "tools/call",
                "params": {
                    "name": "search_nigerian_nutrition",
                    "arguments": {"query": query, "max_results": 3}
                }
            }

            response = await loop.run_in_executor(None, tavily_server.handle_request, request)

            logger.info(f"   → Tavily search completed")
            return {
                "source": "web_search",
                "answer": response.get("answer", ""),
                "sources": [s.get("url") for s in response.get("sources", [])[:3]]
            }

        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")
            return {"error": str(e), "source": "web_search"}

    async def _search_meals_by_date(
        self,
        user_id: str,
        date_description: str,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for meals by date or date range.

        Args:
            user_id: User ID
            date_description: Natural language date (e.g., "yesterday", "last week")
            end_date: Optional end date for range

        Returns:
            Dict with meals and metadata
        """
        try:
            # Parse relative dates (e.g., "yesterday" → "2026-02-11")
            start_date, parsed_end_date = parse_relative_date(date_description)

            # Use provided end_date if available, otherwise use parsed end_date
            final_end_date = end_date or parsed_end_date

            # Fetch meals
            meals = await get_meals_by_date_range(user_id, start_date, final_end_date)

            # Compute totals for each meal
            formatted_meals = []
            for meal in meals:
                foods = meal.get("foods", [])
                totals = {
                    "calories": 0, "protein": 0, "carbohydrates": 0, "fat": 0, "fiber": 0,
                    "iron": 0, "calcium": 0, "zinc": 0, "potassium": 0, "sodium": 0, "magnesium": 0,
                    "vitamin_a": 0, "vitamin_c": 0, "vitamin_d": 0, "vitamin_b12": 0, "folate": 0,
                }
                for food in foods:
                    for nutrient in totals:
                        totals[nutrient] += food.get(nutrient, 0)

                formatted_meals.append({
                    "meal_type": meal.get("meal_type"),
                    "date": meal.get("meal_date"),
                    "time": meal.get("meal_time"),
                    "foods": [f.get("food_name") for f in foods],
                    "totals": totals,
                    "scene_description": meal.get("scene_description") or None,
                })

            logger.info(f"   → Found {len(formatted_meals)} meals for date: {date_description}")

            return {
                "meals": formatted_meals,
                "date_range": {
                    "start": start_date,
                    "end": final_end_date
                },
                "count": len(formatted_meals)
            }

        except Exception as e:
            logger.error(f"Search meals by date error: {e}")
            return {"error": str(e), "meals": []}

    async def _search_meals_by_food_name(
        self,
        user_id: str,
        food_name: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Search for meals containing a specific food.

        Args:
            user_id: User ID
            food_name: Name of food to search for
            limit: Max meals to return

        Returns:
            Dict with meals containing the food
        """
        try:
            # Search for meals with this food
            meals = await search_meals_by_food(user_id, food_name, limit)

            # Compute totals for each meal
            formatted_meals = []
            for meal in meals:
                foods = meal.get("foods", [])
                totals = {
                    "calories": 0, "protein": 0, "carbohydrates": 0, "fat": 0, "fiber": 0,
                    "iron": 0, "calcium": 0, "zinc": 0, "potassium": 0, "sodium": 0, "magnesium": 0,
                    "vitamin_a": 0, "vitamin_c": 0, "vitamin_d": 0, "vitamin_b12": 0, "folate": 0,
                }
                for food in foods:
                    for nutrient in totals:
                        totals[nutrient] += food.get(nutrient, 0)

                formatted_meals.append({
                    "meal_type": meal.get("meal_type"),
                    "date": meal.get("meal_date"),
                    "time": meal.get("meal_time"),
                    "foods": [f.get("food_name") for f in foods],
                    "totals": totals,
                    "scene_description": meal.get("scene_description") or None,
                })

            logger.info(f"   → Found {len(formatted_meals)} meals with '{food_name}'")

            # Find most recent date
            most_recent = None
            if formatted_meals:
                most_recent = formatted_meals[0]["date"]  # Already sorted by most recent

            return {
                "meals": formatted_meals,
                "food_searched": food_name,
                "count": len(formatted_meals),
                "most_recent_date": most_recent
            }

        except Exception as e:
            logger.error(f"Search meals by food error: {e}")
            return {"error": str(e), "meals": []}

    def _generate_suggestions(self, message: str, assistant_response: str = "") -> List[str]:
        """Generate follow-up suggestions based on user message and KAI's response."""
        message_lower = message.lower()
        response_lower = assistant_response.lower()
        combined = message_lower + " " + response_lower

        if any(word in combined for word in ["iron", "calcium", "protein", "nutrient", "folate", "vitamin"]):
            return ["Show me a meal with this nutrient", "How am I doing today?"]
        elif any(word in combined for word in ["progress", "doing", "stats", "streak"]):
            return ["Suggest a meal for my goal", "Show my meal history"]
        elif any(word in combined for word in ["suggest", "recommend", "should i eat", "what to eat", "meal idea"]):
            return ["Give me different options", "How am I doing today?"]
        elif any(word in combined for word in ["last meal", "feedback", "how was", "analyze"]):
            return ["Suggest my next meal", "Check my progress"]
        elif any(word in combined for word in ["ate", "lunch", "dinner", "breakfast", "snack"]):
            return ["How was that meal?", "Suggest my next meal"]
        else:
            return ["Suggest a meal for my goal", "Check your progress"]


# Singleton
_chat_agent: Optional[ChatAgent] = None


def get_chat_agent() -> ChatAgent:
    """Get or create singleton ChatAgent."""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAgent()
        logger.info("✓ ChatAgent singleton created")
    return _chat_agent

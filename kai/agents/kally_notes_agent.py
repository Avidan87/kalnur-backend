"""
Kally Notes Agent — Coach's Notebook Architecture

Cards are generated once per day per user via scheduled jobs (8AM and 8PM WAT).
The /kally-notes endpoint reads from cache — no on-demand generation.

Morning job: 3 cards in one GPT call — Notice, Goal Pulse, Intel.
Evening job: Notice only, only if new meals logged since morning.

New user gate: users with fewer than 3 days of meal history get a separate
welcome-mode summary that prevents false pattern conclusions from thin data.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, date
from typing import Optional

from openai import AsyncOpenAI

from kai.database import get_meals_by_date_range, get_user_health_profile
from kai.database.db_setup import get_supabase
from kai.services.nutrition_priorities import get_priority_rdvs, GOAL_LIMIT_NUTRIENTS, LIMIT_NUTRIENTS

logger = logging.getLogger(__name__)

_openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_MODEL_MINI = "gpt-4o-mini"

# ── In-memory caches ──────────────────────────────────────────────────────────
# { user_id: { date, generated_at, notice, goal_pulse, intel, nutrient_summary } }
_morning_cache: dict[str, dict] = {}
# { user_id: { date, notice } }
_evening_cache: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Pre-processing (no GPT)
# ─────────────────────────────────────────────────────────────────────────────

MEAL_BASES = [
    "tomato stew", "pepper stew", "tomato sauce", "palm oil stew",
]
SOUPS = [
    "egusi soup", "ogbono soup", "efo riro", "edikang ikong",
    "banga soup", "ofe onugbu", "afang soup", "okra soup",
    "gbegiri", "abula", "ewedu", "pepper soup", "bitterleaf soup",
]
SWALLOWS = [
    "eba", "pounded yam", "amala", "fufu", "semovita",
    "tuwo shinkafa", "wheat", "semo",
]
PROTEINS = [
    "grilled chicken", "fried chicken", "grilled fish", "fried fish",
    "beef", "goat meat", "turkey", "ponmo", "shaki", "stockfish",
    "snail", "periwinkle", "crayfish", "dried fish",
]
SIDES = [
    "fried plantain", "boiled plantain", "yam", "sweet potato",
    "moi moi", "akara", "rice", "jollof rice", "ofada rice",
]


def _detect_occasion(timestamp_str: Optional[str]) -> str:
    if not timestamp_str:
        return "meal"
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        h = ts.hour
        if h < 11:
            return "breakfast"
        if h < 16:
            return "lunch"
        if h < 21:
            return "dinner"
        return "late meal"
    except Exception:
        return "meal"


def _detect_cooking_method(food_name: str) -> Optional[str]:
    name = food_name.lower()
    if any(kw in name for kw in ("fried", "fry")):
        return "fried"
    if any(kw in name for kw in ("grilled", "roasted", "bole")):
        return "grilled"
    if any(kw in name for kw in ("boiled", "steamed")):
        return "boiled"
    if "smoked" in name:
        return "smoked"
    return None


def _group_meal_foods(food_names: list[str]) -> str:
    """Group a flat list of food names into a coherent Nigerian meal description."""
    name_lower = [n.lower() for n in food_names]

    swallow = next((n for n in name_lower if any(s in n for s in SWALLOWS)), None)
    soup = next((n for n in name_lower if any(s in n for s in SOUPS)), None)

    used = set()
    parts = []

    if swallow and soup:
        parts.append(f"{swallow} with {soup}")
        used.add(swallow)
        used.add(soup)
    elif soup:
        parts.append(soup)
        used.add(soup)

    for name in name_lower:
        if name not in used:
            if any(b in name for b in MEAL_BASES):
                used.add(name)
                parts.append(name)

    for name in name_lower:
        if name not in used:
            parts.append(name)
            used.add(name)

    return ", ".join(parts) if parts else ", ".join(food_names)


def _build_todays_meal_summary(meals: list[dict], today: date) -> str:
    today_str = today.isoformat()
    today_meals = [m for m in meals if m.get("meal_date", "")[:10] == today_str]

    if not today_meals:
        return "No meals logged today yet."

    occasions: dict[str, list[str]] = {}
    highlights: list[str] = []

    for meal in today_meals:
        occasion = _detect_occasion(meal.get("created_at") or meal.get("meal_date"))
        foods = meal.get("foods", [])
        food_names = [f.get("name") or f.get("food_name", "") for f in foods if f.get("name") or f.get("food_name")]

        if not food_names:
            continue

        grouped = _group_meal_foods(food_names)
        occasions.setdefault(occasion, []).append(grouped)

        nutrients: dict[str, float] = {}
        for food in foods:
            n = food.get("nutrients", food.get("total_nutrients", {}))
            for k, v in n.items():
                if isinstance(v, (int, float)):
                    nutrients[k] = nutrients.get(k, 0) + v

        if nutrients.get("protein", 0) > 25:
            highlights.append(f"good protein from {food_names[0]}")
        if nutrients.get("fiber", 0) > 8:
            highlights.append("solid fiber")

    lines = ["TODAY (logged so far):"]
    for occasion, items in occasions.items():
        lines.append(f"- {occasion.capitalize()}: {'; '.join(items)}")

    if highlights:
        lines.append(f"Nutritional highlight: {', '.join(highlights[:2])}.")

    return "\n".join(lines)


def _build_new_user_summary(meals: list[dict], profile: dict, today: date) -> str:
    """
    Welcome-mode summary for users with fewer than 3 days of meal history.
    Describes what little data exists without drawing pattern conclusions.
    Steers GPT toward an encouraging, exploratory tone — not pattern analysis.
    """
    name = profile.get("name", "the user")
    goal = profile.get("health_goals", "general_wellness")

    food_names: list[str] = []
    for meal in meals:
        for food in meal.get("foods", []):
            n = food.get("name") or food.get("food_name", "")
            if n:
                food_names.append(n)

    days_logged = len({m.get("meal_date", "")[:10] for m in meals if m.get("meal_date")})
    food_str = ", ".join(food_names[:5]) if food_names else "their first meal"

    lines = [
        f"NEW USER CONTEXT:",
        f"- Name: {name}, Goal: {goal}",
        f"- Days logged so far: {days_logged} (not enough data for pattern analysis yet)",
        f"- Foods logged: {food_str}",
        f"",
        f"INSTRUCTION: There is not enough data to draw any nutrient pattern conclusions.",
        f"Do NOT flag any deficits or excesses. Do NOT manufacture problems.",
        f"Write a warm, genuine observation about what their first meal(s) show.",
        f"Set the expectation that Kally will build a fuller picture as they log more.",
        f"Tone: encouraging, curious, like meeting someone for the first time.",
    ]
    return "\n".join(lines)


def _build_nutrient_pattern_summary(meals: list[dict], profile: dict) -> tuple[str, bool]:
    """
    Compute 7-day nutrient patterns and return (plain_english_summary, is_new_user).

    New user gate: if fewer than 3 days have meal data, returns a welcome-mode
    summary that prevents false pattern conclusions from thin data.

    Thresholds:
    - Deficit: avg < 35% of target for 3+ of 7 days
    - Excess: avg > 130% of ceiling for 3+ of 7 days
    - Positive: 5+ of 7 days hitting 70%+ of target for key goal nutrients
    """
    today = date.today()

    # Group meals by day
    by_day: dict[str, dict[str, float]] = {}
    for meal in meals:
        meal_date = meal.get("meal_date", "")[:10]
        if not meal_date:
            continue
        day = by_day.setdefault(meal_date, {})
        for food in meal.get("foods", []):
            n = food.get("nutrients", food.get("total_nutrients", {}))
            for k, v in n.items():
                if isinstance(v, (int, float)):
                    day[k] = day.get(k, 0) + v

    days_with_meals = len(by_day)

    # New user gate — fewer than 3 days means no meaningful pattern analysis
    if days_with_meals < 3:
        return _build_new_user_summary(meals, profile, today), True

    goal = profile.get("health_goals") or "general_wellness"
    gender = profile.get("gender")
    age = profile.get("age")
    custom_calorie_goal = profile.get("active_calorie_goal") or profile.get("custom_calorie_goal")

    priority_rdvs = get_priority_rdvs(goal, gender, age, custom_calorie_goal)
    limit_nutrients = set(GOAL_LIMIT_NUTRIENTS.get(goal, LIMIT_NUTRIENTS))

    days = days_with_meals
    lines = ["NUTRIENT PATTERNS (last 7 days):"]

    for nutrient, rdv_obj in list(priority_rdvs.items())[:6]:
        target = rdv_obj.amount
        if not target:
            continue
        label = rdv_obj.display_name
        is_limit = nutrient in limit_nutrients

        daily_vals = [day.get(nutrient, 0) for day in by_day.values()]
        if not daily_vals:
            continue
        avg = sum(daily_vals) / len(daily_vals)

        if is_limit:
            days_over = sum(1 for v in daily_vals if v > target * 1.3)
            if days_over >= 3:
                lines.append(
                    f"- {label}: elevated — over the recommended ceiling {days_over} of {days} days"
                )
            else:
                lines.append(f"- {label}: within range — no persistent excess")
        else:
            days_below_35 = sum(1 for v in daily_vals if v < target * 0.35)
            days_above_70 = sum(1 for v in daily_vals if v >= target * 0.70)

            if days_below_35 >= 3:
                today_val = list(by_day.values())[-1].get(nutrient, 0) if by_day else 0
                today_note = " Today was better." if today_val >= target * 0.50 else ""
                lines.append(
                    f"- {label}: consistently low — below target {days_below_35} of {days} days.{today_note}"
                )
            elif days_above_70 >= 5:
                lines.append(f"- {label}: on track — above 70% of target most days")
            elif days_above_70 >= 3 and days_above_70 > days_below_35:
                lines.append(f"- {label}: improving — hitting target more days than not")
            else:
                lines.append(f"- {label}: mixed — some days on track, some below")

    if len(lines) == 1:
        return "NUTRIENT PATTERNS (last 7 days):\n- All tracked nutrients appear to be within normal range.", False

    return "\n".join(lines), False


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Fact selection (no GPT)
# ─────────────────────────────────────────────────────────────────────────────

async def _get_unseen_fact(
    user_id: str,
    section: str,
    goal: Optional[str],
    nutrient_summary: str,
) -> Optional[dict]:
    """
    Select one unseen fact for the given section.

    Goal Pulse: filter by goal_tags, score by relevance to nutrient summary.
    Intel: no trigger-food sorting, serve by goal relevance then unseen order.
    """
    supabase = get_supabase()

    seen_resp = (
        supabase.table("user_seen_facts")
        .select("fact_id")
        .eq("user_id", user_id)
        .not_.is_("fact_id", "null")
        .execute()
    )
    seen_ids = {row["fact_id"] for row in (seen_resp.data or [])}

    query = (
        supabase.table("health_facts")
        .select("id, content, section, category, goal_tags, trigger_foods, severity")
        .eq("section", section)
    )
    if goal and section == "goal_fact":
        query = query.contains("goal_tags", [goal])

    resp = query.limit(50 + len(seen_ids)).execute()
    rows = resp.data or []
    unseen = [r for r in rows if r["id"] not in seen_ids]

    if not unseen:
        # All seen — reset and serve from full pool
        unseen = rows

    if not unseen:
        return None

    if section == "goal_fact":
        def _score(fact: dict) -> int:
            score = 0
            cat = (fact.get("category") or "").lower().replace("_", " ")
            if cat and cat in nutrient_summary.lower():
                score += 2
            if fact.get("severity", "low") == "high":
                score += 1
            return score

        unseen.sort(key=lambda f: (-_score(f),))

    return unseen[0]


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — GPT generation
# ─────────────────────────────────────────────────────────────────────────────

async def _generate_morning_cards(
    user_id: str,
    profile: dict,
    nutrient_summary: str,
    todays_summary: str,
    goal_fact: Optional[dict],
    intel_fact: Optional[dict],
    is_new_user: bool,
) -> dict:
    """
    Single GPT call that generates all 3 cards (Notice, Goal Pulse, Intel).
    is_new_user flag adjusts the Notice instruction to welcome-mode.
    """
    name = profile.get("name", "the user")
    age = profile.get("age", "")
    gender = profile.get("gender", "")
    goal = profile.get("health_goals", "general_wellness")

    show_sugar = profile.get("show_sugar", False)
    sugar_tracking_enabled = show_sugar and goal != "manage_blood_sugar"

    sugar_instruction = ""
    if sugar_tracking_enabled:
        sugar_instruction = """
## Sugar awareness
This user has chosen to track their sugar intake alongside their primary goal.
Where relevant and natural (not forced), you may weave sugar impact into the cards.

Rules:
- Lead with the primary goal always. Sugar is a footnote, not a headline.
- Only mention sugar when the user's carb patterns make it genuinely relevant
- Suggest lower-sugar versions of Nigerian foods the user already eats — never introduce unfamiliar foods just for sugar
- ALWAYS explain blood sugar technical terms in plain English immediately where used (same sentence or right after):
  * GI / glycaemic index → "how fast the food raises your blood sugar"
  * Glycaemic load → "how fast AND how much sugar the food releases"
  * Net carbs → "carbs that actually affect blood sugar — total carbs minus fibre"
  * Blood glucose → "the sugar in your bloodstream"
  * Insulin → "the hormone that moves sugar from blood into your cells"
  * Insulin resistance → "when cells stop responding to insulin properly"
  * Blood sugar spike → "a sharp, fast rise in blood sugar after eating"
  * Blood sugar crash → "the energy dip that follows a spike"
  * Refined carbs → "carbs stripped of fibre — like white rice, white bread — they spike blood sugar fast"
  * Complex carbs → "carbs with fibre intact — like oats, beans — they release sugar slowly"
- Never repeat a term explanation in the same set of cards
- Nigerian food is normal and valid — never make it sound dangerous
"""

    intel_sugar_note = ""
    if sugar_tracking_enabled:
        intel_sugar_note = "\nIf the intel fact relates to sugar, carbohydrates, or GI — this is a natural moment to teach it. Explain all technical terms in plain English immediately."

    goal_fact_content = (
        goal_fact.get("content", "")
        if goal_fact
        else "No specific goal fact available — write a genuine goal coaching insight based on their patterns."
    )
    intel_fact_content = (
        intel_fact.get("content", "")
        if intel_fact
        else "No specific intel fact available — share a genuinely useful nutrition insight relevant to Nigerian food culture."
    )

    if is_new_user:
        notice_instruction = """CARD 1 — THE NOTICE (WELCOME MODE)
This user is just starting out — there is not enough data for pattern analysis.
Write a warm, genuine first observation based on what they logged.
Celebrate that they started. Mention something specific from their first meal(s) if available.
Set the expectation that Kally will build a fuller picture as they log more.
Do NOT flag any deficits or excesses. Do NOT manufacture problems.
Severity: "low". Sentiment: "positive"."""
    else:
        notice_instruction = """CARD 1 — THE NOTICE
Connect today's meals to their 7-day pattern. Observe honestly.
- If the pattern shows a genuine concern (3+ days below threshold): name it clearly, connect it to today, give ONE practical action
- If today broke a bad pattern: celebrate that specifically
- If the pattern is genuinely good: celebrate it with specifics — name what they did right and why it matters for their goal
- If nothing significant either way: a warm, grounded observation about what today showed
High bar for concern — only flag genuine multi-day patterns, not single-meal observations. Do NOT manufacture problems.
Severity: "high" for excesses, "medium" for persistent deficits, "low" for positive or neutral
Sentiment: "urgent" if severity is high or medium, "positive" if low"""

    prompt = f"""SYSTEM:
You are Kally, the nutrition coach inside the Kalnur app.
You write like a brilliant friend who studied nutrition — plain, warm, real.
No jargon without explanation. No medical terms without plain English immediately after.
Nigerian food is normal and valid — never treat it as strange or unhealthy by default.

USER:
## About this user
Name: {name}
Age: {age}, Gender: {gender}
Health goal: {goal}
{sugar_instruction}
## Their 7-day nutrient patterns
{nutrient_summary}

## What they ate today
{todays_summary}

## Unseen health fact for Goal Pulse
{goal_fact_content}

## Unseen health fact for Intel
{intel_fact_content}

## Write exactly 3 cards:

{notice_instruction}

CARD 2 — GOAL PULSE
Reframe the goal fact for this specific user's goal journey.
Connect it to where they actually are this week based on their patterns.
Do NOT review what they ate — the Notice already did that.
One sharp insight + one practical action specific to their goal.

CARD 3 — INTEL
Reframe the intel fact as pure education. Teach it clearly.
Rules for heavy content (disease risks, chemical compounds, medical terms):
- Always lead with context before the concern
- Explain every technical term immediately in plain English in brackets
- Use analogies and real examples, not abstract descriptions
- Pattern vs occasion framing — occasional eating is fine, patterns matter
- Never make normal Nigerian food feel dangerous
- End with something the user can actually do or know{intel_sugar_note}

## Rules for ALL cards:
- Plain English. Talk like a friend, not a medical report
- Explain any technical term IMMEDIATELY after using it, in plain language
- Use analogies when explaining complex concepts
- Be specific — name the food, name the nutrient, name the action
- Full emotional range — celebrate genuinely, warn honestly, never shame
- 2-3 sentences per card. Every sentence earns its place
- Never open with a greeting or "Your recently logged meal was..."
- Never repeat content across cards
- Nigerian food culture is normal and valid

Return JSON only — no markdown, no commentary:
{{
  "notice": {{"title": "...", "body": "...", "severity": "high|medium|low", "sentiment": "urgent|positive"}},
  "goal_pulse": {{"title": "...", "body": "..."}},
  "intel": {{"title": "...", "body": "..."}}
}}"""

    resp = await _openai.chat.completions.create(
        model=_MODEL_MINI,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=600,
    )
    raw = resp.choices[0].message.content or "{}"
    parsed = json.loads(raw)

    notice_raw = parsed.get("notice", {})
    goal_pulse_raw = parsed.get("goal_pulse", {})
    intel_raw = parsed.get("intel", {})

    # New users always get positive sentiment regardless of GPT output
    if is_new_user:
        sentiment = "positive"
        severity = "low"
    else:
        sentiment = notice_raw.get("sentiment", "positive")
        severity = notice_raw.get("severity", "low")

    return {
        "notice": {
            "type": "notice",
            "id": f"notice-{user_id}-{date.today().isoformat()}",
            "title": notice_raw.get("title", "Today's Pattern"),
            "body": notice_raw.get("body", ""),
            "severity": severity,
            "sentiment": sentiment,
        },
        "goal_pulse": {
            "type": "goal_fact",
            "id": goal_fact["id"] if goal_fact else f"goal-{user_id}",
            "title": goal_pulse_raw.get("title", "For Your Goal"),
            "body": goal_pulse_raw.get("body", ""),
            "severity": "low",
            "sentiment": "positive",
        },
        "intel": {
            "type": "general_intel",
            "id": intel_fact["id"] if intel_fact else f"intel-{user_id}",
            "title": intel_raw.get("title", "Health Intel"),
            "body": intel_raw.get("body", ""),
            "severity": "low",
            "sentiment": "positive",
        },
    }


async def _generate_evening_notice(
    user_id: str,
    profile: dict,
    nutrient_summary: str,
    todays_summary: str,
    is_new_user: bool,
) -> dict:
    """Evening GPT call — Notice card only. Reflects the full day of eating."""
    name = profile.get("name", "the user")
    age = profile.get("age", "")
    gender = profile.get("gender", "")
    goal = profile.get("health_goals", "general_wellness")

    if is_new_user:
        notice_instruction = """Write a warm, encouraging evening reflection for a user who is just starting out.
Celebrate that they logged today. Mention something specific from their meals.
Do NOT flag any deficits or excesses.
Severity: "low". Sentiment: "positive"."""
    else:
        notice_instruction = """Write 1 card — THE NOTICE (evening update)
This is the evening update. The user has finished most of their eating for today.
Kally's observation should reflect the full picture of today, not just encourage more logging.
Connect today's full eating to their 7-day pattern. Observe honestly.
- If the pattern shows a genuine concern: name it clearly, connect it to today, give ONE practical action
- If today was a good day in context of their week: celebrate it specifically
- If nothing significant: a warm, grounded reflection on today's eating
High bar for concern — only flag genuine multi-day patterns.
Severity: "high" for excesses, "medium" for persistent deficits, "low" for positive or neutral
Sentiment: "urgent" if severity is high or medium, "positive" if low"""

    prompt = f"""SYSTEM:
You are Kally, the nutrition coach inside the Kalnur app.
You write like a brilliant friend who studied nutrition — plain, warm, real.
Nigerian food is normal and valid — never treat it as strange or unhealthy by default.

USER:
## About this user
Name: {name}
Age: {age}, Gender: {gender}
Health goal: {goal}

## Their 7-day nutrient patterns (today now included)
{nutrient_summary}

## What they ate today (full day)
{todays_summary}

## {notice_instruction}

Rules:
- Plain English — talk like a friend
- 2-3 sentences. Every sentence earns its place
- Never open with a greeting or "Your recently logged meal was..."

Return JSON only:
{{"notice": {{"title": "...", "body": "...", "severity": "high|medium|low", "sentiment": "urgent|positive"}}}}"""

    resp = await _openai.chat.completions.create(
        model=_MODEL_MINI,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=200,
    )
    raw = resp.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    notice_raw = parsed.get("notice", {})

    if is_new_user:
        sentiment = "positive"
        severity = "low"
    else:
        sentiment = notice_raw.get("sentiment", "positive")
        severity = notice_raw.get("severity", "low")

    return {
        "type": "notice",
        "id": f"notice-{user_id}-{date.today().isoformat()}-eve",
        "title": notice_raw.get("title", "Today's Wrap"),
        "body": notice_raw.get("body", ""),
        "severity": severity,
        "sentiment": sentiment,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Cache management (called by scheduler jobs)
# ─────────────────────────────────────────────────────────────────────────────

async def _generate_and_cache_morning(user_id: str) -> None:
    """
    Full morning generation for one user: pre-process → fact selection → 1 GPT call → cache.
    Called by the 8AM scheduler job and as a fallback from the API endpoint.
    """
    try:
        profile_raw = await get_user_health_profile(user_id)
        profile = profile_raw or {}

        today = date.today()
        week_ago = (today - timedelta(days=7)).isoformat()
        meals = await get_meals_by_date_range(user_id, week_ago, today.isoformat())

        if not meals:
            logger.info("kally_notes: no meals for user %s — skipping morning generation", user_id)
            return

        nutrient_summary, is_new_user = _build_nutrient_pattern_summary(meals, profile)
        todays_summary = _build_todays_meal_summary(meals, today)

        goal = profile.get("health_goals")
        goal_fact, intel_fact = await asyncio.gather(
            _get_unseen_fact(user_id, "goal_fact", goal, nutrient_summary),
            _get_unseen_fact(user_id, "general_intel", goal, nutrient_summary),
        )

        cards = await _generate_morning_cards(
            user_id, profile, nutrient_summary, todays_summary,
            goal_fact, intel_fact, is_new_user,
        )

        _morning_cache[user_id] = {
            "date": today,
            "generated_at": datetime.now(),
            "notice": cards["notice"],
            "goal_pulse": cards["goal_pulse"],
            "intel": cards["intel"],
            "nutrient_summary": nutrient_summary,
        }
        logger.info("kally_notes: morning cache set for user %s (new_user=%s)", user_id, is_new_user)

    except Exception:
        logger.exception("kally_notes: morning generation error for user %s", user_id)


async def _generate_and_cache_evening(user_id: str) -> None:
    """Evening notice update for one user. Only runs if new meals logged since morning."""
    try:
        morning = _morning_cache.get(user_id)
        today = date.today()

        profile_raw = await get_user_health_profile(user_id)
        profile = profile_raw or {}

        week_ago = (today - timedelta(days=7)).isoformat()
        meals = await get_meals_by_date_range(user_id, week_ago, today.isoformat())

        # Check if any meals logged since the morning cache was generated
        if morning and morning.get("date") == today:
            morning_generated_at = morning.get("generated_at", datetime.min)
            new_meals = [m for m in meals if _parse_meal_time(m) > morning_generated_at]
            if not new_meals:
                logger.info("kally_notes: no new meals for user %s since morning — skipping evening", user_id)
                return

        nutrient_summary, is_new_user = _build_nutrient_pattern_summary(meals, profile)
        todays_summary = _build_todays_meal_summary(meals, today)

        notice = await _generate_evening_notice(
            user_id, profile, nutrient_summary, todays_summary, is_new_user
        )

        _evening_cache[user_id] = {
            "date": today,
            "notice": notice,
        }
        logger.info("kally_notes: evening notice cached for user %s", user_id)

    except Exception:
        logger.exception("kally_notes: evening generation error for user %s", user_id)


def _parse_meal_time(meal: dict) -> datetime:
    raw = meal.get("created_at") or meal.get("meal_date", "")
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.min


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Public API (called by server.py and scheduler)
# ─────────────────────────────────────────────────────────────────────────────

async def get_notes_for_user(user_id: str) -> dict:
    """
    Read Kally Notes from cache for the user.
    Falls back to generating morning cards on-demand if cache is empty or stale.
    Response shape is unchanged from previous version.
    """
    today = date.today()

    morning = _morning_cache.get(user_id)
    if not morning or morning.get("date") != today:
        logger.info("kally_notes: cache miss for user %s — generating now", user_id)
        await _generate_and_cache_morning(user_id)
        morning = _morning_cache.get(user_id)

    if not morning:
        return {
            "notices": [],
            "goal_facts": [],
            "general_intel": [],
            "sentiment": "none",
        }

    evening = _evening_cache.get(user_id)
    notice = (
        evening["notice"]
        if evening and evening.get("date") == today
        else morning["notice"]
    )

    return {
        "notices": [notice],
        "goal_facts": [morning["goal_pulse"]],
        "general_intel": [morning["intel"]],
        "sentiment": notice.get("sentiment", "positive"),
    }


def invalidate_notes_cache(user_id: str) -> None:
    """
    Kept for compatibility — new architecture does NOT bust cache on meal log.
    Evening job handles updates at 8PM. This is a no-op.
    """
    pass


async def get_notes_context_for_chat(user_id: str) -> str:
    """
    Returns last ~5 seen facts + notices as a text block for injection
    into chat_agent's system prompt.
    """
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("user_seen_facts")
            .select("fact_id, notice_text, section, seen_at")
            .eq("user_id", user_id)
            .order("seen_at", desc=True)
            .limit(5)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return ""

        fact_ids = [r["fact_id"] for r in rows if r.get("fact_id")]
        facts_map: dict[str, str] = {}
        if fact_ids:
            facts_resp = (
                supabase.table("health_facts")
                .select("id, content")
                .in_("id", fact_ids)
                .execute()
            )
            facts_map = {f["id"]: f["content"] for f in (facts_resp.data or [])}

        lines = ["[Kally has already told this user:]"]
        for row in rows:
            if row.get("fact_id") and row["fact_id"] in facts_map:
                lines.append(f"- {facts_map[row['fact_id']]}")
            elif row.get("notice_text"):
                lines.append(f"- {row['notice_text']}")

        return "\n".join(lines)

    except Exception:
        logger.exception("get_notes_context_for_chat error for user %s", user_id)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — Bulk generation functions (called by push_scheduler.py)
# ─────────────────────────────────────────────────────────────────────────────

async def bulk_generate_morning_notes(user_ids: list[str]) -> None:
    """Generate morning notes for a list of user IDs in batches of 20."""
    batch_size = 20
    for i in range(0, len(user_ids), batch_size):
        batch = user_ids[i: i + batch_size]
        await asyncio.gather(*[_generate_and_cache_morning(uid) for uid in batch])
        logger.info(
            "kally_notes: morning batch %d/%d complete",
            i // batch_size + 1,
            (len(user_ids) + batch_size - 1) // batch_size,
        )


async def bulk_generate_evening_notices(user_ids: list[str]) -> None:
    """Generate evening notices for a list of user IDs in batches of 20."""
    batch_size = 20
    for i in range(0, len(user_ids), batch_size):
        batch = user_ids[i: i + batch_size]
        await asyncio.gather(*[_generate_and_cache_evening(uid) for uid in batch])
        logger.info(
            "kally_notes: evening batch %d/%d complete",
            i // batch_size + 1,
            (len(user_ids) + batch_size - 1) // batch_size,
        )

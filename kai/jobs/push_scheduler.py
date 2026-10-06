"""
Push + Email Notification Scheduler

Sends personalised Web Push AND email notifications to Kalnur users.
Triggered by APScheduler on a cron schedule (wired in server.py lifespan).

Notification types:
- meal_reminder    : User hasn't logged a meal today by a certain hour
- streak_alert     : User is about to lose their streak (no log yet today, had one yesterday)
- streak_milestone : User hits 3, 7, 14, 30-day streak
- daily_summary    : Evening summary of today's calories vs goal
- coaching_nudge   : User has not completed coaching chat onboarding
- milestone        : First week streak, 10 meals logged, etc.
- weekly_summary   : Sunday evening recap for all users
- re_engagement    : User inactive for 3+ days
"""

import os
import json
import asyncio
import logging
from datetime import datetime, date, timedelta
import zoneinfo

import httpx
from pywebpush import webpush, WebPushException  # type: ignore[import]

from kai.database import (
    get_all_subscriptions,
    delete_push_subscription,
    get_all_native_tokens,
    delete_native_push_token,
    get_native_push_tokens,
    get_supabase,
)
from kai.services.nutrition_priorities import calculate_rdv_percentages
from kai.services.email_service import (
    send_streak_at_risk_email,
    send_streak_milestone_email,
    send_weekly_summary_email,
    send_reengagement_email,
)

WAT = zoneinfo.ZoneInfo("Africa/Lagos")

logger = logging.getLogger(__name__)

# ── VAPID keys (set these in .env) ────────────────────────────────────────────
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS      = {"sub": os.getenv("VAPID_SUBJECT", "mailto:hello@kalnur.com")}

# Endpoints that returned 404/410 during this process run — deleted at end of job
_dead_endpoints: list[str] = []


# ── Low-level send ─────────────────────────────────────────────────────────────

def send_push(subscription: dict, title: str, body: str, url: str = "/") -> bool:
    """
    Send a single Web Push notification.
    Returns True on success, False on failure.
    Expired subscriptions (404/410) are collected in _dead_endpoints and
    deleted asynchronously by the calling async job — never inside this sync fn.
    """
    if not VAPID_PRIVATE_KEY:
        logger.warning("VAPID_PRIVATE_KEY not set — skipping push send")
        return False

    payload = json.dumps({"title": title, "body": body, "url": url})

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS,
        )
        return True
    except WebPushException as e:
        status = e.response.status_code if e.response else None
        if status in (404, 410):
            # Mark for async cleanup — never call asyncio.create_task() in sync
            endpoint = subscription.get("endpoint", "")
            if endpoint:
                _dead_endpoints.append(endpoint)
        else:
            logger.warning("Push failed (%s): %s", status, e)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("Push error: %s", e)
        return False


async def _cleanup_dead_endpoints() -> None:
    """Delete any expired subscriptions collected during the last send batch."""
    while _dead_endpoints:
        endpoint = _dead_endpoints.pop()
        await delete_push_subscription(endpoint)


# ── Expo Push (React Native) ───────────────────────────────────────────────────

_dead_native_tokens: list[str] = []

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_expo_push(tokens: list[str], title: str, body: str) -> list[dict]:
    """
    Send a push notification to a list of Expo push tokens.
    Invalid/expired tokens are collected in _dead_native_tokens for async cleanup.
    Returns the raw per-token result list from Expo's API (empty list on failure).
    """
    if not tokens:
        return []

    messages = [{"to": t, "title": title, "body": body, "sound": "default"} for t in tokens]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"Accept": "application/json", "Accept-Encoding": "gzip, deflate"},
            )
            data = resp.json()
            results = data.get("data", [])
            print(f"📲 EXPO PUSH HTTP {resp.status_code} — full response: {data}", flush=True)
            for item, token in zip(results, tokens):
                status = item.get("status")
                error  = item.get("details", {}).get("error", "")
                print(f"  token=...{token[-10:]}  status={status}  error={error}", flush=True)
                if status == "error" and error == "DeviceNotRegistered":
                    _dead_native_tokens.append(token)
            return results
    except Exception as e:
        logger.warning("Expo push failed: %s", e)
        return []


async def _cleanup_dead_native_tokens() -> None:
    while _dead_native_tokens:
        token = _dead_native_tokens.pop()
        await delete_native_push_token(token)


# ── Per-user helpers ───────────────────────────────────────────────────────────

def _has_logged_today(user_id: str) -> bool:
    client = get_supabase()
    today = date.today().isoformat()
    result = client.table("meals") \
        .select("meal_id") \
        .eq("user_id", user_id) \
        .eq("meal_date", today) \
        .limit(1) \
        .execute()
    return bool(result.data)


def _get_streak(user_id: str) -> int:
    client = get_supabase()
    result = client.table("user_nutrition_stats") \
        .select("current_logging_streak") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    if result.data:
        return result.data[0].get("current_logging_streak", 0)
    return 0


def _get_calories_today(user_id: str) -> tuple[float, float]:
    """Returns (calories_logged_today, calorie_goal)."""
    client = get_supabase()
    today = date.today().isoformat()

    # Today's total
    totals = client.table("daily_nutrients") \
        .select("total_calories") \
        .eq("user_id", user_id) \
        .eq("date", today) \
        .limit(1) \
        .execute()
    logged = totals.data[0]["total_calories"] if totals.data else 0.0

    # Goal
    health = client.table("user_health") \
        .select("active_calorie_goal") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    goal = health.data[0].get("active_calorie_goal") or 2000.0 if health.data else 2000.0

    return float(logged), float(goal)


def _get_user_goal(user_id: str) -> str:
    """Returns health_goals string e.g. 'weight_loss', 'muscle_gain', 'maintenance'."""
    client = get_supabase()
    result = client.table("user_health") \
        .select("health_goals") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    return result.data[0].get("health_goals") or "general" if result.data else "general"


def _is_coaching_incomplete(user_id: str) -> bool:
    client = get_supabase()
    result = client.table("user_coaching") \
        .select("coaching_complete") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    if result.data:
        return not result.data[0].get("coaching_complete", False)
    return True  # no row = never started


def _get_user_name(user_id: str) -> str:
    client = get_supabase()
    result = client.table("users") \
        .select("name") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    return result.data[0].get("name") or "there" if result.data else "there"


def _get_user_email(user_id: str) -> str | None:
    """Returns email only if user has not unsubscribed."""
    client = get_supabase()
    result = client.table("users") \
        .select("email, email_unsubscribed") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    if not result.data:
        return None
    row = result.data[0]
    if row.get("email_unsubscribed"):
        return None
    return row.get("email")


def _get_all_users() -> list[dict]:
    """Returns all users with user_id, email, name — excludes unsubscribed users."""
    client = get_supabase()
    result = client.table("users") \
        .select("user_id, email, name, email_unsubscribed") \
        .neq("email_unsubscribed", True) \
        .execute()
    return result.data or []


def _get_days_since_last_meal(user_id: str) -> int:
    """Returns number of days since the user last logged a meal. 0 = logged today."""
    client = get_supabase()
    result = client.table("meals") \
        .select("meal_date") \
        .eq("user_id", user_id) \
        .order("meal_date", desc=True) \
        .limit(1) \
        .execute()
    if not result.data:
        return 999  # never logged
    last = date.fromisoformat(result.data[0]["meal_date"])
    return (date.today() - last).days


def _get_weekly_stats(user_id: str) -> dict:
    """Returns stats for the past 7 days for weekly summary email."""
    client = get_supabase()
    today = date.today()
    week_ago = (today - timedelta(days=7)).isoformat()

    meals = client.table("daily_nutrients") \
        .select("date, total_calories") \
        .eq("user_id", user_id) \
        .gte("date", week_ago) \
        .execute()

    days_logged = len(meals.data)
    avg_calories = (
        sum(r.get("total_calories", 0) or 0 for r in meals.data) / days_logged
        if days_logged > 0 else 0.0
    )

    # Top meal this week (meal_foods holds food_name, joined via meals)
    top_meals = client.table("meal_foods") \
        .select("food_name, meals!inner(meal_date, user_id)") \
        .eq("meals.user_id", user_id) \
        .gte("meals.meal_date", week_ago) \
        .execute()
    meal_counts: dict[str, int] = {}
    for m in (top_meals.data or []):
        food = m.get("food_name", "")
        if food:
            meal_counts[food] = meal_counts.get(food, 0) + 1
    top_meal = max(meal_counts, key=meal_counts.get) if meal_counts else None

    return {"days_logged": days_logged, "avg_calories": avg_calories, "top_meal": top_meal}


def _get_total_meals(user_id: str) -> int:
    client = get_supabase()
    result = client.table("user_nutrition_stats") \
        .select("total_meals_logged") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    return result.data[0].get("total_meals_logged", 0) if result.data else 0


def _get_user_profile_for_rdv(user_id: str) -> tuple[str, str | None, int | None]:
    """Returns (goal, gender, age) for RDV calculations."""
    client = get_supabase()
    user_result = client.table("users") \
        .select("gender, age") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    health_result = client.table("user_health") \
        .select("health_goals") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    gender = user_result.data[0].get("gender") if user_result.data else None
    age = user_result.data[0].get("age") if user_result.data else None
    goal = health_result.data[0].get("health_goals") or "general" if health_result.data else "general"
    return goal, gender, age


def _get_nutrient_gaps_today(user_id: str) -> list[tuple[str, str]]:
    """
    Returns up to 3 nutrients that are below 40% of RDV today.
    Each entry is (nutrient_label, emoji) e.g. ("protein", "💪").
    Computes RDV percentages in-memory from the total_* columns.
    """
    client = get_supabase()
    today = date.today().isoformat()

    NUTRIENT_EMOJI = {
        "protein": "💪", "fiber": "🌾", "iron": "🩸",
        "calcium": "🦴", "vitamin_c": "🍊", "vitamin_d": "☀️",
        "potassium": "🍌", "magnesium": "💎", "zinc": "⚡",
        "folate": "🥬", "vitamin_b12": "🧬",
    }
    NUTRIENT_LABEL = {
        "protein": "protein", "fiber": "fibre", "iron": "iron",
        "calcium": "calcium", "vitamin_c": "Vitamin C", "vitamin_d": "Vitamin D",
        "potassium": "potassium", "magnesium": "magnesium", "zinc": "zinc",
        "folate": "folate", "vitamin_b12": "B12",
    }
    # Map nutrient key → DB column name
    DB_COL = {
        "protein": "total_protein", "fiber": "total_fiber", "iron": "total_iron",
        "calcium": "total_calcium", "vitamin_c": "total_vitamin_c",
        "vitamin_d": "total_vitamin_d", "potassium": "total_potassium",
        "magnesium": "total_magnesium", "zinc": "total_zinc",
        "folate": "total_folate", "vitamin_b12": "total_vitamin_b12",
    }

    cols = ",".join(DB_COL.values())
    result = client.table("daily_nutrients") \
        .select(cols) \
        .eq("user_id", user_id) \
        .eq("date", today) \
        .limit(1) \
        .execute()

    if not result.data:
        return []

    row = result.data[0]
    consumed = {key: float(row.get(db_col) or 0) for key, db_col in DB_COL.items()}

    goal, gender, age = _get_user_profile_for_rdv(user_id)
    try:
        rdv = calculate_rdv_percentages(consumed, goal, gender, age)
    except Exception:
        rdv = {}

    gaps = []
    for key, emoji in NUTRIENT_EMOJI.items():
        pct = rdv.get(key, 0) or 0
        if pct < 40:
            gaps.append((NUTRIENT_LABEL[key], emoji))
        if len(gaps) == 3:
            break
    return gaps


# ── Notification message builder ───────────────────────────────────────────────

def _days_since_signup(user_id: str) -> int:
    """Days since the user's row was created. Used to vary coaching nudges."""
    client = get_supabase()
    result = client.table("users") \
        .select("created_at") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()
    if not result.data:
        return 0
    created_raw = result.data[0].get("created_at", "")
    try:
        created = datetime.fromisoformat(created_raw.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return 0
    return (date.today() - created).days


def _build_morning_message(user_id: str, name: str) -> tuple[str, str]:
    """
    Dynamic morning log reminder — personalised by streak, goal, and yesterday's
    nutrient gaps. Priority: streak context → goal-specific → default.
    """
    streak = _get_streak(user_id)
    goal = _get_user_goal(user_id)
    gaps = _get_nutrient_gaps_today(user_id)  # yesterday's gaps (today not logged yet)
    days_inactive = _get_days_since_last_meal(user_id)

    # ── Streak context (highest priority — user has momentum to protect) ──────
    if streak >= 30:
        return (
            "Kalnur 🏆",
            f"{name}, you're on a 30-day streak. That's rare. Log today's first meal and protect it.",
        )
    if streak >= 14:
        return (
            "Kalnur 🔥",
            f"{streak} days straight, {name}. Two weeks of showing up. Don't let today be the break — log your first meal.",
        )
    if streak >= 7:
        return (
            "Kalnur 🔥",
            f"Day {streak + 1} of your streak, {name}. A full week in — log this morning's meal before anything else.",
        )
    if streak >= 3:
        return (
            "Kalnur 🌱",
            f"{streak} days logged in a row, {name}. You're building something — what did you eat first today?",
        )
    if streak == 1:
        return (
            "Kalnur 🌿",
            f"You logged yesterday, {name}. Do it again today and a real streak begins. What's breakfast?",
        )

    # ── Coming back after a gap ───────────────────────────────────────────────
    if days_inactive == 1:
        return (
            "Kalnur ☀️",
            f"Morning {name}. You were on it yesterday — pick up right where you left off. What's the first meal?",
        )

    # ── Goal-specific with actual nutrient gaps from yesterday ────────────────
    if gaps and goal == "weight_loss":
        gap_str = " and ".join(f"{e} {n}" for n, e in gaps[:2])
        return (
            "Kalnur ☀️",
            f"Morning {name}. Yesterday you were low on {gap_str}. Log breakfast and Kally tracks whether you're covering the gap today.",
        )
    if gaps and goal in ("muscle_gain", "gain_muscle"):
        gap_str = " and ".join(f"{e} {n}" for n, e in gaps[:2])
        return (
            "Kalnur 💪",
            f"Morning {name}. You were short on {gap_str} yesterday. Log breakfast now — Kally tracks every nutrient from the first bite.",
        )
    if gaps and goal == "heart_health":
        gap_str = " and ".join(f"{e} {n}" for n, e in gaps[:2])
        return (
            "Kalnur ☀️",
            f"Morning {name}. Yesterday your {gap_str} were low — both matter for blood pressure and heart function. Log breakfast and Kally tracks them from the first bite.",
        )
    if gaps and goal == "bone_health":
        n, e = gaps[0]
        return (
            "Kalnur ☀️",
            f"Morning {name}. {e} {n.capitalize()} was low yesterday — your bones need consistent intake to stay strong. Log today's first meal and Kally picks up right where you left off.",
        )
    if gaps and goal == "energy_boost":
        gap_str = " and ".join(f"{e} {n}" for n, e in gaps[:2])
        return (
            "Kalnur ☀️",
            f"Morning {name}. Your {gap_str} were low yesterday — those are directly linked to energy and focus. Log breakfast and Kally tracks whether today covers the gap.",
        )
    if gaps and goal == "pregnancy":
        n, e = gaps[0]
        return (
            "Kalnur 🌿",
            f"Morning {name}. {e} {n.capitalize()} was low yesterday — it's one of the most important nutrients right now. Log your first meal and Kally keeps a close eye on it today.",
        )
    if gaps and goal in ("maintain_weight", "maintenance"):
        gap_str = " and ".join(f"{e} {n}" for n, e in gaps[:2])
        return (
            "Kalnur 🌿",
            f"Morning {name}. {gap_str} were both low yesterday. Staying balanced is what maintenance is about — log breakfast and Kally tracks it.",
        )
    if gaps and goal == "general":
        n, e = gaps[0]
        return (
            "Kalnur 🌿",
            f"Morning {name}. {e} {n.capitalize()} was low yesterday. Start today strong — log your first meal and Kally picks up the tracking.",
        )

    # ── Goal-specific (no gaps — clean slate) ────────────────────────────────
    if goal == "weight_loss":
        return (
            "Kalnur ☀️",
            f"Morning {name}. Logging breakfast is the habit that keeps weight loss on track. What did you eat first?",
        )
    if goal in ("muscle_gain", "gain_muscle"):
        return (
            "Kalnur 💪",
            f"Morning {name}. Log breakfast early and Kally starts tracking all your nutrients from the first bite.",
        )
    if goal == "heart_health":
        return (
            "Kalnur ☀️",
            f"Morning {name}. Heart-healthy eating starts with knowing what's in your food. Log breakfast and Kally tracks the nutrients that matter most for you.",
        )
    if goal == "bone_health":
        return (
            "Kalnur ☀️",
            f"Morning {name}. Calcium and Vitamin D work best when you're consistent. Log today's first meal and Kally keeps your bone health on track.",
        )
    if goal == "energy_boost":
        return (
            "Kalnur ☀️",
            f"Morning {name}. Energy crashes often come from gaps in your nutrients, not just sleep. Log breakfast and Kally tracks what's fuelling you today.",
        )
    if goal == "pregnancy":
        return (
            "Kalnur 🌿",
            f"Morning {name}. Every meal counts right now. Log your first meal and Kally watches your key nutrients — folate, iron, calcium — all day.",
        )
    if goal in ("maintain_weight", "maintenance"):
        return (
            "Kalnur 🌿",
            f"Morning {name}. Maintenance is about consistency, not perfection. Log breakfast and Kally keeps your picture complete.",
        )

    # ── Default ───────────────────────────────────────────────────────────────
    return (
        "Kalnur 🌿",
        f"Morning {name}. What's the first thing you ate today? Log it in 10 seconds and Kally handles the rest.",
    )


def _build_coaching_nudge_message(user_id: str, name: str) -> tuple[str | None, str | None]:
    """
    Pick a coaching-incomplete push that escalates with day count.
    Returns (None, None) after day 7 — we stop nagging and let email take over.
    """
    days = _days_since_signup(user_id)
    if days <= 0:
        return ("Kalnur 🌱", f"{name}, Kally has a quick question — takes 30 seconds and shapes your whole plan.")
    if days == 1:
        return ("Kalnur 🌿", f"Morning {name}! Kally is still waiting to learn about you. Want to finish setting things up?")
    if days <= 3:
        return ("Kalnur ☕", f"{name}, your nutrition plan isn't personalised yet. 3 quick questions and Kally takes it from there.")
    if days <= 7:
        return ("Kalnur 🌱", f"It's been a minute, {name}. Tap to finish onboarding and unlock your goal-matched coaching.")
    return (None, None)  # cap reached — stop sending


def _build_streak_alert_message(user_id: str, name: str) -> tuple[str, str] | tuple[None, None]:
    """
    7:00 PM WAT — streak-at-risk warning. Only fires if user has a streak ≥ 2
    and hasn't logged today. Gives them a real window to log before the day ends.
    Returns (None, None) if no streak is at risk.
    """
    streak = _get_streak(user_id)
    logged_today = _has_logged_today(user_id)

    if streak >= 2 and not logged_today:
        return (
            "Kalnur 🔥",
            f"You haven't logged today, {name}. Your {streak}-day streak is still alive — log your last meal before the day ends.",
        )
    return (None, None)


def _build_evening_message(user_id: str, name: str) -> tuple[str, str]:
    """
    Picks the most relevant evening message for this user based on their day.
    Fully personalised by streak, health goal, nutrient gaps, and calorie progress.
    Streak pressure is handled separately at 7 PM — this job focuses on coaching.

    Priority:
    1. Didn't log today — calm tomorrow-focused nudge
    2. Nutrient gaps — specific nutrients, goal-aware advice
    3. Low calorie day — goal-aware explanation
    4. Calorie goal recap — streak-aware celebration
    """
    streak = _get_streak(user_id)
    goal = _get_user_goal(user_id)
    logged_today = _has_logged_today(user_id)
    days_inactive = _get_days_since_last_meal(user_id)

    # 1. Didn't log today — calm, no streak pressure, redirect to tomorrow
    if not logged_today:
        if days_inactive >= 2:
            return (
                "Kalnur 🌿",
                f"Kally hasn't heard from you in a couple of days, {name}. No pressure — start fresh tomorrow and log your first meal in the morning.",
            )
        return (
            "Kalnur 🌿",
            f"No log today, {name}. Streaks reset but habits don't — Kally will be here tomorrow. Log your first meal in the morning and keep the momentum going.",
        )

    # User logged today — give them something genuinely useful
    logged_cal, goal_cal = _get_calories_today(user_id)
    pct = int((logged_cal / goal_cal) * 100) if goal_cal > 0 else 0
    gaps = _get_nutrient_gaps_today(user_id)

    # 3. Nutrient gaps — most actionable, fully personalised by goal
    if len(gaps) >= 2:
        labels = " and ".join(f"{e} {n}" for n, e in gaps[:2])
        if goal == "weight_loss":
            return (
                "Kalnur 🌱",
                f"Good logging today, {name}. {labels} were low though — getting these from whole foods keeps fat loss sustainable. Kally can suggest what to add tomorrow.",
            )
        if goal == "muscle_gain":
            return (
                "Kalnur 💪",
                f"Solid day, {name}. One gap to close — {labels} were both low. These matter for recovery and growth. Prioritise them in tomorrow's first meal.",
            )
        return (
            "Kalnur 🌱",
            f"Tomorrow, focus on {labels} — both were low today. Kally can suggest Nigerian meals that cover the gap.",
        )

    if len(gaps) == 1:
        n, e = gaps[0]
        if goal == "weight_loss":
            return (
                "Kalnur 🌱",
                f"{e} {n.capitalize()} was the one gap today, {name}. Adding it to tomorrow's breakfast keeps your nutrition balanced while you lose weight.",
            )
        if goal == "muscle_gain":
            return (
                "Kalnur 💪",
                f"{e} {n.capitalize()} was low today, {name}. Your muscles need it to recover overnight — try to cover it in your last meal or snack.",
            )
        return (
            "Kalnur 🌱",
            f"{e} {n.capitalize()} was low today, {name}. Try adding it to your first meal tomorrow — small adjustments compound fast.",
        )

    # 4. Low calorie day — goal-aware, not lecture-y
    if pct < 60:
        shortfall = int(goal_cal - logged_cal)
        if goal == "weight_loss":
            return (
                "Kalnur 🌿",
                f"You ate light today, {name}. Eating too little actually slows fat loss — your body needs enough fuel to burn. Aim for {shortfall} more kcal tomorrow.",
            )
        if goal == "muscle_gain":
            return (
                "Kalnur 💪",
                f"Low calorie day, {name}. You're {shortfall} kcal short of your goal — muscle needs consistent fuel to grow. Start tomorrow with a bigger first meal.",
            )
        return (
            "Kalnur 🌿",
            f"You logged {int(logged_cal)} kcal today, {name} — {shortfall} kcal below your goal. Consistent eating keeps your energy and focus steady. Aim to start stronger tomorrow.",
        )

    # 5. Calorie recap — celebrate streaks, acknowledge effort
    if streak >= 7 and pct >= 80:
        return (
            f"Kalnur 🔥",
            f"{streak} days and counting, {name} — and you hit {pct}% of your goal today. That combination is rare. Keep showing up.",
        )
    if pct >= 90:
        return (
            "Kalnur 🎯",
            f"You nailed it today, {name} — {int(logged_cal)} kcal, right on target. That's exactly what consistent progress looks like.",
        )
    return (
        "Kalnur 💪",
        f"Good day, {name}. You hit {pct}% of your calorie goal — {int(goal_cal - logged_cal)} kcal left if you want to top up before bed.",
    )


# ── Notification jobs (max 2 per user per day) ────────────────────────────────

async def send_morning_nudge() -> None:
    """
    10:00 AM WAT — one morning push per user.
    Priority: coaching incomplete → log reminder (skip if already logged).
    Users who already logged before 10 AM get nothing — they're on top of it.
    """
    all_subs = await get_all_subscriptions()
    seen: set[str] = set()
    for row in all_subs:
        user_id = row["user_id"]
        if user_id in seen:
            continue
        seen.add(user_id)
        name = _get_user_name(user_id)

        if _is_coaching_incomplete(user_id):
            title, body = _build_coaching_nudge_message(user_id, name)
            if title is None:
                continue
        elif not _has_logged_today(user_id):
            title, body = _build_morning_message(user_id, name)
        else:
            continue  # already logged — don't disturb them

        send_push(subscription=row["subscription_json"], title=title, body=body, url="/")
    await _cleanup_dead_endpoints()

    all_native = await get_all_native_tokens()
    tokens_by_user: dict[str, list[str]] = {}
    for row in all_native:
        tokens_by_user.setdefault(row["user_id"], []).append(row["token"])

    for user_id, tokens in tokens_by_user.items():
        name = _get_user_name(user_id)

        if _is_coaching_incomplete(user_id):
            title, body = _build_coaching_nudge_message(user_id, name)
            if title is None:
                continue  # capped — stop nagging after day 7
        elif not _has_logged_today(user_id):
            title, body = _build_morning_message(user_id, name)
        else:
            continue

        await send_expo_push(tokens, title, body)
    await _cleanup_dead_native_tokens()


async def send_streak_alert() -> None:
    """
    7:00 PM WAT — streak-at-risk push for users who haven't logged today
    and have a streak ≥ 2. Gives them a real window to act before the day ends.
    Also fires the streak-at-risk email as a second channel.
    """
    all_subs = await get_all_subscriptions()
    seen: set[str] = set()
    for row in all_subs:
        user_id = row["user_id"]
        if user_id in seen:
            continue
        seen.add(user_id)
        name = _get_user_name(user_id)
        title, body = _build_streak_alert_message(user_id, name)
        if title is None:
            continue
        send_push(subscription=row["subscription_json"], title=title, body=body, url="/")
    await _cleanup_dead_endpoints()

    all_native = await get_all_native_tokens()
    tokens_by_user: dict[str, list[str]] = {}
    for row in all_native:
        tokens_by_user.setdefault(row["user_id"], []).append(row["token"])

    for user_id, tokens in tokens_by_user.items():
        name = _get_user_name(user_id)
        title, body = _build_streak_alert_message(user_id, name)
        if title is None:
            continue
        await send_expo_push(tokens, title, body)
    await _cleanup_dead_native_tokens()

    # ── Streak-at-risk email (separate channel) ───────────────────────────────
    for user in _get_all_users():
        user_id = user["user_id"]
        email = user.get("email")
        name = user.get("name") or "there"
        if not email:
            continue
        streak = _get_streak(user_id)
        if streak >= 2 and not _has_logged_today(user_id):
            send_streak_at_risk_email(email, name, streak)
            await asyncio.sleep(0.6)


async def send_evening_insight() -> None:
    """
    9:00 PM WAT — one intelligent evening push per user.
    Message is dynamically chosen based on the user's day:
    no-log calm nudge → nutrient gaps → calorie recap.
    Streak pressure is handled separately at 7 PM by send_streak_alert.
    """
    all_subs = await get_all_subscriptions()
    seen: set[str] = set()
    for row in all_subs:
        user_id = row["user_id"]
        if user_id in seen:
            continue
        seen.add(user_id)
        name = _get_user_name(user_id)
        title, body = _build_evening_message(user_id, name)
        send_push(subscription=row["subscription_json"], title=title, body=body, url="/")
    await _cleanup_dead_endpoints()

    all_native = await get_all_native_tokens()
    tokens_by_user: dict[str, list[str]] = {}
    for row in all_native:
        tokens_by_user.setdefault(row["user_id"], []).append(row["token"])

    for user_id, tokens in tokens_by_user.items():
        name = _get_user_name(user_id)
        title, body = _build_evening_message(user_id, name)
        await send_expo_push(tokens, title, body)
    await _cleanup_dead_native_tokens()


async def send_milestone_notifications(user_id: str) -> None:
    """
    Called immediately after meal logging when a milestone is hit.
    Milestones: 1st meal, 7-day streak, 10 meals, 25 meals.
    Push + email both fire.
    """
    total = _get_total_meals(user_id)
    streak = _get_streak(user_id)
    name = _get_user_name(user_id)

    title = None
    body = None
    streak_milestone = None  # tracks streak milestones for email

    goal = _get_user_goal(user_id)

    if total == 1:
        title = "Kalnur 🎉"
        body = (
            f"First meal logged, {name}! Kally just analysed everything — open the app to see exactly what you ate. This is how it starts."
        )
    elif total == 10:
        title = "Kalnur 🌱"
        body = (
            f"10 meals in, {name}. Kally now has a real picture of how you eat — open the app, your nutrition patterns are starting to show."
        )
    elif total == 25:
        title = "Kalnur ⚡"
        body = (
            f"25 meals logged, {name}. That's not a trial anymore — that's a habit forming. Kally knows your eating patterns well now."
        )

    if streak == 3:
        streak_milestone = streak
        if not title:
            title = "Kalnur 🌱"
            body = f"3 days in a row, {name}. Most people quit before this point. You didn't — keep going."
    elif streak == 7:
        streak_milestone = streak
        if not title:
            title = "Kalnur 🔥"
            body = (
                f"One full week of logging, {name}. Kally has enough data now to really understand your eating patterns. This is where it gets interesting."
            )
    elif streak == 14:
        streak_milestone = streak
        if not title:
            title = "Kalnur ⚡"
            body = f"Two weeks straight, {name}. That's not motivation anymore — that's a habit. Kally's proud of you."
    elif streak == 30:
        streak_milestone = streak
        if not title:
            title = "Kalnur 🏆"
            body = (
                f"30 days, {name}. One month of showing up every single day. Very few people get here. You're one of them."
            )

    if not title:
        return

    # ── Web Push ──────────────────────────────────────────────────────────────
    from kai.database import get_push_subscriptions
    subs = await get_push_subscriptions(user_id)
    for sub in subs:
        send_push(subscription=sub, title=title, body=body, url="/")

    # ── Expo Push (native) ────────────────────────────────────────────────────
    native_tokens = await get_native_push_tokens(user_id)
    if native_tokens:
        await send_expo_push(native_tokens, title, body)
    await _cleanup_dead_native_tokens()

    # ── Email: streak milestones ──────────────────────────────────────────────
    if streak_milestone:
        email = _get_user_email(user_id)
        if email:
            send_streak_milestone_email(email, name, streak_milestone)


async def send_weekly_summaries() -> None:
    """
    Sunday 8:00 PM WAT — weekly recap email for all users.
    """
    for user in _get_all_users():
        user_id = user["user_id"]
        email = user.get("email")
        name = user.get("name") or "there"
        if not email:
            continue
        stats = _get_weekly_stats(user_id)
        if stats["days_logged"] == 0:
            continue  # never logged this week — skip
        _, calorie_goal = _get_calories_today(user_id)
        send_weekly_summary_email(
            to=email,
            name=name,
            days_logged=stats["days_logged"],
            best_streak=_get_streak(user_id),
            avg_calories=stats["avg_calories"],
            calorie_goal=calorie_goal,
            top_meal=stats["top_meal"],
        )
        await asyncio.sleep(0.6)  # stay under Resend's 2 req/sec limit


async def send_reengagement_notifications() -> None:
    """
    Daily 10:00 AM WAT — email users inactive for exactly 3 days.
    """
    for user in _get_all_users():
        user_id = user["user_id"]
        email = user.get("email")
        name = user.get("name") or "there"
        if not email:
            continue
        days_inactive = _get_days_since_last_meal(user_id)
        if days_inactive == 3:  # only on exactly day 3 — not every day after
            send_reengagement_email(email, name, days_inactive)
            await asyncio.sleep(0.6)  # stay under Resend's 2 req/sec limit


async def reset_broken_streaks() -> None:
    """
    Daily 00:05 AM WAT — reset current_logging_streak to 0 for users
    whose last logged meal was 2+ days ago (streak is genuinely broken).
    """
    client = get_supabase()

    for user in _get_all_users():
        user_id = user["user_id"]
        days_inactive = _get_days_since_last_meal(user_id)

        if days_inactive >= 2:
            client.table("user_nutrition_stats") \
                .update({"current_logging_streak": 0}) \
                .eq("user_id", user_id) \
                .execute()
            logger.info(f"🔴 Streak reset for user {user_id} ({days_inactive} days inactive)")


# ── Kally Notes scheduled generation ─────────────────────────────────────────

async def generate_morning_notes() -> None:
    """
    8:00 AM WAT — generate morning Kally Notes cards for all active users.
    Active = at least one meal logged in the last 7 days.
    """
    from kai.agents.kally_notes_agent import bulk_generate_morning_notes

    try:
        supabase = get_supabase()
        today = datetime.now(WAT).date()
        week_ago = (today - timedelta(days=7)).isoformat()

        resp = (
            supabase.table("daily_nutrients")
            .select("user_id")
            .gte("date", week_ago)
            .execute()
        )
        rows = resp.data or []
        user_ids = list({r["user_id"] for r in rows if r.get("user_id")})
        logger.info("kally_notes morning job: %d active users", len(user_ids))

        if user_ids:
            await bulk_generate_morning_notes(user_ids)

    except Exception:
        logger.exception("generate_morning_notes job failed")


async def generate_evening_notice() -> None:
    """
    8:00 PM WAT — update the Notice card for users who logged meals since 8AM.
    Runs alongside send_evening_insight — both fire at 20:00.
    """
    from kai.agents.kally_notes_agent import bulk_generate_evening_notices

    try:
        supabase = get_supabase()
        today = datetime.now(WAT).date()
        today_str = today.isoformat()

        resp = (
            supabase.table("daily_nutrients")
            .select("user_id")
            .eq("date", today_str)
            .execute()
        )
        rows = resp.data or []
        user_ids = list({r["user_id"] for r in rows if r.get("user_id")})
        logger.info("kally_notes evening job: %d users with today meals", len(user_ids))

        if user_ids:
            await bulk_generate_evening_notices(user_ids)

    except Exception:
        logger.exception("generate_evening_notice job failed")

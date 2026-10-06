"""
FastAPI server for KAI

Endpoints (v1):
Auth (Supabase Auth with password):
- POST /api/v1/auth/signup              # Sign up with email + password, get JWT token
- POST /api/v1/auth/login               # Login with email + password, get JWT token

Chat:
- POST /api/v1/chat                     # Chat with KAI (nutrition questions, progress, feedback)

Food Logging:
- POST /api/v1/food-logging-upload      # Vision → Knowledge → Save (returns facts, feedback in chat)

Meals:
- GET  /api/v1/meals/history            # Get meal history (user_id from JWT)

Users:
- GET    /api/v1/users/profile          # Get user profile + health + RDV (user_id from JWT)
- PUT    /api/v1/users/health-profile   # Update health profile with BMR/TDEE calculations
- GET    /api/v1/users/nutrition-plan   # Get goal-driven nutrition plan with priority nutrients
- GET    /api/v1/users/stats            # Get daily nutrition stats (user_id from JWT)
- DELETE /api/v1/users/account          # Permanently delete account and all data
- PATCH  /api/v1/users/sugar-preference # Update sugar tracking preference

Kally Notes:
- GET  /api/v1/kally-notes             # All notes: notices, goal_facts, general_intel
- POST /api/v1/kally-notes/seen        # Mark note seen { fact_id?, notice_text?, tapped_through }
"""

import os
import hmac
import time
import uuid
import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Header
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import base64

logger = logging.getLogger(__name__)

from kai.models.agent_models import (
    ChatRequest,
    ChatResponse,
    DetectedFood,
    FoodLoggingResponse,
    KnowledgeResult,
    MealHistoryResponse,
    UserProfileResponse,
    UserStatsResponse,
)
from kai.agents.chat_agent import get_chat_agent
from kai.orchestrator import handle_user_request
from kai.api.food_logging_stream import stream_food_analysis, calculate_nutrition
from kai.auth import sign_up_user, sign_in_user, get_current_user_id, get_current_user, refresh_session
from kai.database import (
    initialize_database,
    get_user,
    create_user,
    get_user_by_email,
    update_user,
    update_user_health,
    get_user_health_profile,
    delete_user,
    get_user_meals,
    get_daily_nutrition_totals,
    get_conversation_history,
    clear_conversation_history,
    get_user_stats as get_user_stats_db,
    is_coaching_complete,
    get_user_coaching,
    reset_coaching_step,
    reset_coaching_full,
    save_push_subscription,
    delete_push_subscription,
    save_native_push_token,
    update_sugar_preference,
)
from kai.services import get_priority_nutrients, get_priority_rdvs, get_nutrient_emoji, get_goal_context
from kai.utils.meal_title import generate_meal_title
from kai.services.nutrition_priorities import get_priority_rdvs as get_rdvs
from kai.jobs.push_scheduler import (
    send_push,
    send_morning_nudge,
    send_streak_alert,
    send_evening_insight,
    send_milestone_notifications,
    send_weekly_summaries,
    send_reengagement_notifications,
    reset_broken_streaks,
    generate_morning_notes,
    generate_evening_notice,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    await initialize_database()
    print("✅ Database initialized")

    # Start push notification scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler(timezone="Africa/Lagos")  # WAT — West Africa Time

    # 10:00 AM WAT — morning nudge (coaching incomplete → log reminder)
    scheduler.add_job(send_morning_nudge,              "cron", hour=10, minute=0)
    # 7:00 PM WAT — streak-at-risk alert (users with streak ≥ 2 who haven't logged yet)
    scheduler.add_job(send_streak_alert,               "cron", hour=19, minute=0)
    # 9:00 PM WAT — evening insight (no-log nudge → nutrient gaps → calorie recap)
    scheduler.add_job(send_evening_insight,            "cron", hour=21, minute=0)
    # 10:05 AM WAT — re-engagement email for users inactive exactly 3 days
    scheduler.add_job(send_reengagement_notifications, "cron", hour=10, minute=5)
    # Sunday 8:00 PM WAT — weekly summary email
    scheduler.add_job(send_weekly_summaries,           "cron", day_of_week="sun", hour=20, minute=0)
    # 00:05 AM WAT — reset streaks for users who missed yesterday
    scheduler.add_job(reset_broken_streaks,            "cron", hour=0,  minute=5)
    # 8:00 AM WAT — generate Kally Notes morning cards for all active users (3 cards, 1 GPT call)
    scheduler.add_job(generate_morning_notes,          "cron", hour=8,  minute=0)
    # 8:00 PM WAT — update Kally Notes notice card for users who logged since 8AM
    scheduler.add_job(generate_evening_notice,         "cron", hour=20, minute=0)  # stays at 8 PM — Kally Notes, not push

    scheduler.start()
    print("✅ Push + Email notification scheduler started (WAT timezone)")

    yield

    scheduler.shutdown(wait=False)
    print("🛑 Push notification scheduler stopped")


app = FastAPI(
    title="Kalnur Nutrition Intelligence API",
    description="Nigerian nutrition coaching with AI-powered agents",
    version="2.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True}  # Keep auth token in Swagger
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_operations_key(
    x_operations_key: Optional[str] = Header(default=None),
) -> None:
    """Protect routes that can invoke paid benchmark providers.

    Operations routes are disabled unless OPERATIONS_API_KEY is configured.
    Keep that key in server-side deployment secrets only.
    """
    expected_key = os.getenv("OPERATIONS_API_KEY")
    if not expected_key or not x_operations_key or not hmac.compare_digest(x_operations_key, expected_key):
        # Avoid advertising expensive internal operations on public hosts.
        raise HTTPException(status_code=404, detail="Not found")


@app.get("/")
async def root():
    return {
        "service": "Kalnur Nutrition Intelligence API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Kalnur Backend", "version": "2.0.0"}


# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.post("/api/v1/auth/signup")
async def signup(
    email: str = Form(...),
    password: str = Form(..., min_length=6),
    name: str = Form(...),
    gender: str = Form(...),
    age: int = Form(...)
):
    """
    Sign up new user with password and return JWT token.

    All fields are required for signup. Health profile (weight, height, activity, goals)
    can be completed later via /api/v1/users/health-profile endpoint.

    Password must be at least 6 characters.
    """
    # Clean and validate email
    email_clean = email.strip().lower()

    # Validate name
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Name is required and cannot be empty")

    # Validate and normalize gender
    gender_normalized = gender.lower().strip()
    if gender_normalized not in ["male", "female"]:
        raise HTTPException(status_code=400, detail="Gender must be 'male' or 'female'")

    # Validate age
    if age < 13 or age > 120:
        raise HTTPException(status_code=400, detail="Age must be between 13 and 120")

    try:
        # 1. Create user in Supabase Auth (handles password hashing)
        auth_result = sign_up_user(email=email_clean, password=password)
        user_id = auth_result["user_id"]

        # 2. Create user profile in our database
        user = await create_user(
            user_id=user_id,
            email=email_clean,
            name=name,
            gender=gender_normalized,
            age=age
        )

        # 3. Send welcome email (non-blocking — never fail signup if email fails)
        try:
            from kai.services.email_service import send_welcome_email
            send_welcome_email(email_clean, name)
        except Exception as e:
            logger.warning("Welcome email failed for %s: %s", email_clean, e)

        return {
            "access_token": auth_result["access_token"],
            "refresh_token": auth_result["refresh_token"],
            "token_type": "bearer",
            "user_id": user_id,
            "user": user
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/auth/login")
async def login(
    email: str = Form(...),
    password: str = Form(...)
):
    """
    Login existing user with password and return JWT token.

    Returns access_token and refresh_token for authenticated sessions.
    """
    try:
        # Authenticate with Supabase Auth
        auth_result = sign_in_user(email=email, password=password)

        return {
            "access_token": auth_result["access_token"],
            "refresh_token": auth_result["refresh_token"],
            "token_type": "bearer",
            "user_id": auth_result["user_id"]
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.get("/api/v1/unsubscribe")
async def unsubscribe(email: str):
    """
    One-click unsubscribe endpoint — called from email footer links.
    Sets email_unsubscribed=True on the user's profile so schedulers skip them.
    """
    try:
        user = await get_user_by_email(email)
        if user:
            await update_user(user["id"], {"email_unsubscribed": True})
        # Always return a friendly page — never expose whether email exists
        return HTMLResponse(content="""
            <html><body style="font-family:Arial,sans-serif;text-align:center;padding:60px;background:#F7F2EB;">
              <h2 style="color:#1B4332;">✅ You've been unsubscribed</h2>
              <p style="color:#7A6A58;">You won't receive any more emails from Kalnur.</p>
              <a href="https://kalnur.com" style="color:#52976E;">Back to Kalnur</a>
            </body></html>
        """, status_code=200)
    except Exception as e:
        logger.warning("Unsubscribe failed for %s: %s", email, e)
        return HTMLResponse(content="""
            <html><body style="font-family:Arial,sans-serif;text-align:center;padding:60px;background:#F7F2EB;">
              <h2 style="color:#1B4332;">✅ You've been unsubscribed</h2>
              <p style="color:#7A6A58;">You won't receive any more emails from Kalnur.</p>
              <a href="https://kalnur.com" style="color:#52976E;">Back to Kalnur</a>
            </body></html>
        """, status_code=200)


@app.post("/api/v1/auth/refresh")
async def refresh_token(refresh_token: str = Form(...)):
    """
    Exchange a refresh token for a new access token + refresh token pair.
    Allows users to stay logged in without re-entering credentials.
    """
    try:
        result = refresh_session(refresh_token)
        return {
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "token_type": "bearer",
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/api/v1/auth/google")
async def google_auth(user: dict = Depends(get_current_user)):
    """
    Register or verify a Google OAuth user.

    Called by the frontend after Supabase Google OAuth completes.
    Creates a user row in the DB if this is a new Google user.
    Returns is_new_user=True if onboarding is required.
    """
    user_id = user["user_id"]
    email = user["email"]

    existing = await get_user(user_id)
    if existing:
        return {"user_id": user_id, "is_new_user": False}

    # First-time Google sign-in — create user row with placeholder values.
    # Name, gender, age will be filled in during onboarding.
    await create_user(user_id=user_id, email=email, name=None, gender="female", age=25)
    return {"user_id": user_id, "is_new_user": True}


@app.post("/api/v1/auth/apple")
async def apple_auth(user: dict = Depends(get_current_user)):
    """
    Register or verify an Apple Sign-In user.

    Called by the native app after Supabase Apple Sign-In completes.
    Creates a user row in the DB if this is a new Apple user.
    Returns is_new_user=True if onboarding is required.
    """
    user_id = user["user_id"]
    email = user.get("email", "")

    existing = await get_user(user_id)
    if existing:
        return {"user_id": user_id, "is_new_user": False}

    # First-time Apple sign-in — create user row with placeholder values.
    # Apple may return empty email on repeat sign-ins (user can hide it),
    # so we fall back to empty string and let onboarding collect it.
    await create_user(user_id=user_id, email=email, name=None, gender="female", age=25)
    return {"user_id": user_id, "is_new_user": True}


# ============================================================================
# Chat Endpoints
# ============================================================================

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Chat with KAI - your Nigerian nutrition assistant.

    Use for:
    - Nutrition questions ("What foods are high in iron?")
    - Progress checks ("How am I doing today?")
    - Meal feedback ("How was my last meal?")
    - General health questions

    NOTE: Conversation history is automatically loaded from database.
    Client can optionally pass conversation_history to override (e.g., for testing).
    """
    start = time.time()
    try:
        chat_agent = get_chat_agent()

        # Auto-load conversation history from database (last 20 messages)
        # Client can override by passing conversation_history in request
        conversation_history = request.conversation_history
        if not conversation_history:
            db_history = await get_conversation_history(user_id, limit=20)
            # Convert to ChatMessage format expected by agent
            conversation_history = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in db_history
            ]

        result = await chat_agent.chat(
            user_id=user_id,
            message=request.message,
            conversation_history=conversation_history,
            language=request.language,
        )

        return ChatResponse(
            success=result.get("success", True),
            message=result.get("message", ""),
            suggestions=result.get("suggestions", []),
            processing_time_ms=int((time.time() - start) * 1000),
        )
    except Exception as e:
        logger.error(f"❌ Chat failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@app.post("/api/v1/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Stream KAI's chat response token-by-token via Server-Sent Events."""
    chat_agent = get_chat_agent()

    conversation_history = request.conversation_history
    if not conversation_history:
        db_history = await get_conversation_history(user_id, limit=20)
        conversation_history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in db_history
        ]

    return StreamingResponse(
        chat_agent.chat_stream(
            user_id=user_id,
            message=request.message,
            conversation_history=conversation_history,
            language=request.language,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering on Railway
        },
    )


@app.delete("/api/v1/chat/history")
async def delete_chat_history(
    user_id: str = Depends(get_current_user_id),
):
    """
    Clear user's conversation history with KAI.

    This will permanently delete all chat messages and start fresh.
    """
    try:
        success = await clear_conversation_history(user_id)

        if success:
            return {
                "success": True,
                "message": "Conversation history cleared successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to clear conversation history")

    except Exception as e:
        logger.error(f"❌ Clear history failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Clear history failed: {str(e)}")


# ============================================================================
# Coaching Endpoints
# ============================================================================

@app.delete("/api/v1/coaching/step")
async def reset_coaching_step_endpoint(
    step: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Reset (null out) a specific coaching step answer so the user can re-answer it.
    Called when user goes back during the coaching flow.

    step must be one of: barrier, food_habits, motivation_score
    """
    try:
        success = await reset_coaching_step(user_id, step)
        if success:
            return {"success": True, "message": f"Coaching step '{step}' reset"}
        else:
            raise HTTPException(status_code=400, detail=f"Invalid or failed step reset: {step}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Reset coaching step failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/coaching/reset")
async def reset_coaching_full_endpoint(
    user_id: str = Depends(get_current_user_id),
):
    """Fully reset coaching flow — clears all answers and sets coaching_complete=False."""
    try:
        success = await reset_coaching_full(user_id)
        if success:
            return {"success": True, "message": "Coaching flow fully reset"}
        else:
            raise HTTPException(status_code=500, detail="Failed to reset coaching")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Full coaching reset failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/coaching/status")
async def get_coaching_status_endpoint(
    user_id: str = Depends(get_current_user_id),
):
    """
    Returns the real coaching step state from the DB.
    Native uses this on overlay open to sync its local step counter
    with actual progress — prevents step pills and completion logic
    from being out of sync when a user resumes a mid-session flow.
    """
    try:
        coaching = await get_user_coaching(user_id)
        if not coaching:
            return {
                "coaching_complete": False,
                "barrier_done": False,
                "food_habits_done": False,
                "favourite_meal_done": False,
                "motivation_done": False,
                "current_step": 0,
            }
        barrier_done       = coaching.get("barrier") is not None
        food_habits_done   = coaching.get("food_habits") is not None
        favourite_meal_done = coaching.get("favourite_meal") is not None
        motivation_done    = coaching.get("motivation_score") is not None
        coaching_complete  = coaching.get("coaching_complete", False)

        # current_step = how many answers already saved (0-4)
        # native uses this to initialise stepRef so pills + completion are correct
        current_step = sum([barrier_done, food_habits_done, favourite_meal_done, motivation_done])

        return {
            "coaching_complete": coaching_complete,
            "barrier_done": barrier_done,
            "food_habits_done": food_habits_done,
            "favourite_meal_done": favourite_meal_done,
            "motivation_done": motivation_done,
            "current_step": current_step,
        }
    except Exception as e:
        logger.error(f"❌ Get coaching status failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Push Notification Endpoints
# ============================================================================

@app.get("/api/v1/push/vapid-public-key")
async def get_vapid_public_key():
    """Return the VAPID public key so the frontend can subscribe."""
    key = os.getenv("VAPID_PUBLIC_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"public_key": key}


@app.post("/api/v1/push/subscribe")
async def subscribe_push(
    subscription: dict,
    user_id: str = Depends(get_current_user_id),
):
    """
    Save a browser push subscription for the current user.

    Body: the PushSubscription object from the browser
    (endpoint, keys.p256dh, keys.auth).
    """
    try:
        await save_push_subscription(user_id, subscription)
        return {"success": True, "message": "Subscribed to push notifications"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Push subscribe failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/push/subscribe")
async def unsubscribe_push(
    endpoint: str,
    user_id: str = Depends(get_current_user_id),
):
    """Remove a push subscription by endpoint URL."""
    try:
        await delete_push_subscription(endpoint)
        return {"success": True, "message": "Unsubscribed from push notifications"}
    except Exception as e:
        logger.error(f"❌ Push unsubscribe failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/push/subscribe-native")
async def subscribe_push_native(
    body: dict,
    user_id: str = Depends(get_current_user_id),
):
    """
    Save an Expo push token for the current user (React Native app).
    Body: { "token": "ExponentPushToken[...]" }
    """
    token = body.get("token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    try:
        await save_native_push_token(user_id, token)
        return {"success": True, "message": "Native push token registered"}
    except Exception as e:
        logger.error(f"❌ Native push subscribe failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/push/test")
async def test_push(
    user_id: str = Depends(get_current_user_id),
):
    """
    Send a test push notification to all subscribed devices of the current user.
    Use this to verify the full push pipeline is working end-to-end.
    Returns how many devices were notified.
    """
    from kai.database import get_push_subscriptions
    subs = await get_push_subscriptions(user_id)
    if not subs:
        raise HTTPException(status_code=404, detail="No push subscriptions found for this user. Subscribe first.")

    sent = 0
    failed = 0
    for sub in subs:
        ok = send_push(
            subscription=sub,
            title="Kalnur 🌱",
            body="Test notification — your push setup is working!",
            url="/",
        )
        if ok:
            sent += 1
        else:
            failed += 1

    from kai.jobs.push_scheduler import _cleanup_dead_endpoints
    await _cleanup_dead_endpoints()

    return {"success": sent > 0, "sent": sent, "failed": failed}


@app.post("/api/v1/push/test-native")
async def test_push_native(
    user_id: str = Depends(get_current_user_id),
):
    """
    Send a test Expo push to all native tokens for the current user.
    Returns the raw per-token result from Expo's API so we can diagnose failures.
    """
    from kai.database import get_native_push_tokens
    from kai.jobs.push_scheduler import send_expo_push, _cleanup_dead_native_tokens

    tokens = await get_native_push_tokens(user_id)
    if not tokens:
        raise HTTPException(status_code=404, detail="No native push tokens found for this user. Subscribe first.")

    results = await send_expo_push(
        tokens,
        title="Kalnur 🌱",
        body="Native push test — if you see this, it's working!",
    )
    await _cleanup_dead_native_tokens()

    per_token = [
        {"token": t, "result": r}
        for t, r in zip(tokens, results)
    ]
    all_ok = all(r.get("status") == "ok" for r in results)
    return {"success": all_ok, "tokens_tested": len(tokens), "details": per_token}


@app.post("/api/v1/email/test")
async def test_email(
    user_id: str = Depends(get_current_user_id),
):
    """
    Send a test welcome email to the current user.
    Use this to verify the Resend API key and domain are working.
    """
    from kai.services.email_service import send_welcome_email
    profile = await get_user_health_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    email = profile.get("email")
    name = profile.get("name") or "there"
    if not email:
        raise HTTPException(status_code=400, detail="No email address found for this user")
    ok = send_welcome_email(email, name)
    return {"success": ok, "sent_to": email}


# ============================================================================
# ── Notification message generator ───────────────────────────────────────────

async def _build_notification_message(
    user_id: str,
    meal_title: str,
    meal_type: str,
    knowledge: "KnowledgeResult | None",
    health_goal: str,
) -> str:
    """
    Generate a dynamic Kally notification message based on:
    - The meal just logged (nutrients, calories)
    - The user's last 7 days of meals (pattern detection)
    - The user's health goal (sentiment direction)

    Returns a short, warm, specific body for the push notification.
    """
    try:
        # Fetch last 7 days of meals for pattern detection
        recent_meals = await get_user_meals(user_id, limit=14)

        # Count how many recent meals were low in key nutrients
        low_protein_count = 0
        low_iron_count    = 0
        high_cal_count    = 0

        rdvs = get_rdvs(health_goal)
        protein_rdv  = rdvs.get("protein", 50)
        iron_rdv     = rdvs.get("iron", 18)
        calorie_rdv  = rdvs.get("calories", 2000)

        for m in recent_meals[:7]:
            foods = m.get("foods", [])
            meal_protein  = sum(f.get("protein", 0) for f in foods)
            meal_iron     = sum(f.get("iron", 0) for f in foods)
            meal_calories = sum(f.get("calories", 0) for f in foods)
            if meal_protein < (protein_rdv * 0.15):  # less than 15% RDV per meal
                low_protein_count += 1
            if meal_iron < (iron_rdv * 0.10):
                low_iron_count += 1
            if meal_calories > (calorie_rdv * 0.45):  # heavy meal
                high_cal_count += 1

        # Get current meal stats
        meal_calories = knowledge.total_calories if knowledge else 0
        meal_protein  = knowledge.total_protein  if knowledge else 0
        meal_iron     = knowledge.total_iron     if knowledge else 0

        # Priority: pattern > single meal issue > positive > generic
        # Pattern — low protein streak
        if low_protein_count >= 3 and meal_protein < (protein_rdv * 0.15):
            return f"That's {low_protein_count} low-protein meals this week — Kally has a note for you on this one 👀"

        # Pattern — low iron streak
        if low_iron_count >= 3 and meal_iron < (iron_rdv * 0.10):
            return f"Iron has been low across your last few meals — Kally spotted something worth knowing 🩸"

        # Single meal — very high calories
        if meal_calories > (calorie_rdv * 0.50):
            return f"That was a heavy one — Kally has your full breakdown ready 👀"

        # Positive — good protein
        if meal_protein >= (protein_rdv * 0.25):
            return f"Solid protein hit from that {meal_type} — Kally has the full picture for you 💪"

        # Positive — general good meal
        if meal_calories > 0 and meal_calories < (calorie_rdv * 0.35):
            return f"Kally liked this one — tap to see what's working in your favour 💚"

        # Generic fallback
        return f"Kally has your full breakdown ready — tap to see what's in this one"

    except Exception:
        return "Kally has your full breakdown ready — tap to see what's in this one"


# Food Logging Endpoints
# ============================================================================

@app.post("/api/v1/food-logging-upload", response_model=FoodLoggingResponse)
async def food_logging_upload(
    image: UploadFile = File(...),
    user_description: str = Form(None),
    meal_type: str = Form(None),  # Optional: breakfast, lunch, dinner, snack
    user_id: str = Depends(get_current_user_id),
):
    """
    Food logging with image upload.

    Pipeline: Vision → Knowledge → Save to DB
    Returns nutrition facts only. For feedback, use /chat endpoint.

    Args:
        meal_type: Optional meal type (breakfast, lunch, dinner, snack).
                   If not provided, will be inferred from time of day.
                   Used for more accurate portion estimation.
    """
    start = time.time()
    try:
        # Read image and convert to base64
        image_bytes = await image.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        # Upload meal image to Supabase Storage so history/dashboard can show thumbnails.
        # Non-fatal: if upload fails we continue without image_url.
        image_url: Optional[str] = None
        try:
            from kai.database.db_setup import get_supabase
            storage_path = f"{user_id}/{int(time.time() * 1000)}.jpg"
            supabase_client = get_supabase()
            supabase_client.storage.from_("meal-images").upload(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": "image/jpeg", "upsert": "false"},
            )
            supabase_url = supabase_client.supabase_url
            image_url = f"{supabase_url}/storage/v1/object/public/meal-images/{storage_path}"
            logger.info("🖼️ Quick-log meal image uploaded: %s", image_url)
        except Exception as _upload_err:
            logger.warning("⚠️ Quick-log image upload failed: %s — saving without image_url", _upload_err)

        result = await handle_user_request(
            user_message=user_description or "Analyze this food",
            image_base64=image_base64,
            image_url=image_url,
            user_id=user_id,
            meal_type=meal_type,  # Pass meal_type for portion estimation
            conversation_history=[],
        )

        knowledge: KnowledgeResult | None = result.get("nutrition")

        # Get user's health goal for goal-driven nutrient tracking
        profile = await get_user_health_profile(user_id)
        health_goal = profile.get("health_goals", "general_wellness") if profile else "general_wellness"
        gender = profile.get("gender") if profile else None
        age = profile.get("age") if profile else None
        active_calorie_goal = (profile.get("custom_calorie_goal") or profile.get("active_calorie_goal")) if profile else None

        # Get goal context - single source of truth for goal-driven nutrition
        goal_context = get_goal_context(health_goal, gender, age, active_calorie_goal)

        # Extract only PRIORITY NUTRIENTS for this goal
        def get_nutrient(name: str) -> float:
            attr_name = f"total_{name}" if not name.startswith("total_") else name
            return getattr(knowledge, attr_name, 0.0) if knowledge else 0.0

        # Build priority nutrients dict with only goal-relevant nutrients (6-8)
        priority_nutrients = {}
        for nutrient in goal_context["priority_nutrients"]:
            priority_nutrients[nutrient] = get_nutrient(nutrient)

        # Fire milestone check in background — non-blocking, won't delay response
        if result.get("meal_id"):
            asyncio.create_task(send_milestone_notifications(user_id))

        # Build detected_foods from knowledge_result.foods — this includes
        # promoted ingredients (carrots, eggs, etc.) that _extract_foods_from_vision
        # appended after Vision ran. vision_result.detected_foods only has raw Vision
        # output and misses promoted ingredients entirely.
        detected_foods_list = []
        if knowledge:
            for food in knowledge.foods:
                detected_foods_list.append(DetectedFood(
                    name=food.name,
                    nigerian_name=None,
                    confidence=food.similarity_score,
                    estimated_portion=f"{int(food.portion_consumed_grams)}g",
                    estimated_grams=food.portion_consumed_grams,
                    visible_ingredients=[],
                    cooking_method=None,
                    oil_sheen_visible=None,
                    oil_amount_estimate=None,
                ))

        meal_title = generate_meal_title([f.name for f in detected_foods_list])

        # Generate dynamic Kally notification message for offline queue sync
        notification_message = await _build_notification_message(
            user_id=user_id,
            meal_title=meal_title,
            meal_type=meal_type or "meal",
            knowledge=knowledge,
            health_goal=health_goal,
        )

        return FoodLoggingResponse(
            success=True,
            message="Meal logged! Ask me in chat for feedback.",
            detected_foods=detected_foods_list,
            priority_nutrients=priority_nutrients,
            meal_id=result.get("meal_id"),
            meal_title=meal_title,
            notification_message=notification_message,
            processing_time_ms=int((time.time() - start) * 1000),
        )
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"❌ Food logging failed: {str(e)}\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"Food logging failed: {str(e)}")


# ============================================================================
# Real-Time Food Logging — SSE Stream + Calculate
# ============================================================================

@app.post("/api/v1/food-logging-stream")
async def food_logging_stream(
    image: UploadFile = File(...),
    meal_type: str = Form(None),
    user_id: str = Depends(get_current_user_id),
):
    """
    Real-time food analysis via Server-Sent Events.

    Phase 1: Vision Agent detects foods — streams detection events as they happen.
    Phase 2: Fires correction_window event — frontend shows chips for user to correct.
    Phase 3: Client calls /food-logging-calculate with confirmed food list.

    SSE event types:
      step               — general progress narration
      detection          — main dishes found (fires after Vision Agent completes)
      ingredients        — added ingredients promoted from visible_ingredients
      clarification_needed — low-confidence food, frontend shows options
      correction_window  — signals start of correction phase with full food list
      error              — something went wrong
    """
    image_bytes = await image.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    return StreamingResponse(
        stream_food_analysis(
            image_base64=image_base64,
            meal_type=meal_type,
            user_id=user_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/food-logging-calculate")
async def food_logging_calculate(
    request: dict,
    user_id: str = Depends(get_current_user_id),
):
    """
    Calculate nutrition for a user-confirmed food list.

    Called after the user reviews and corrects the SSE stream detections.

    Body:
    {
      "confirmed_foods": [
        {"name": "Indomie Noodles", "confidence": 0.95, "portion_grams": 140},
        {"name": "Boiled Egg",      "confidence": 0.92, "portion_grams": 50},
        {"name": "carrots",         "confidence": 0.7,  "portion_grams": 40}
      ],
      "image_base64": "...",   (optional — for SAM2 if portions not provided)
      "meal_type": "lunch"
    }

    Returns:
      Full nutrition result with priority nutrients + meal_id (saved to DB).
    """
    try:
        confirmed_foods = request.get("confirmed_foods", [])
        image_base64 = request.get("image_base64", "")
        meal_type = request.get("meal_type")

        if not confirmed_foods:
            raise HTTPException(status_code=400, detail="confirmed_foods is required")

        result = await calculate_nutrition(
            confirmed_foods=confirmed_foods,
            image_base64=image_base64,
            meal_type=meal_type,
            user_id=user_id,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("❌ food-logging-calculate failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Calculation failed: {str(e)}")


# ============================================================================
# Vision Model Benchmark Endpoints (Claude Sonnet 4.6 Bedrock vs GPT-4o)
# ============================================================================

@app.post("/api/v1/vision/benchmark")
async def vision_benchmark_upload(
    image: UploadFile = File(..., description="Meal image to test side-by-side (JPEG, PNG, WebP)"),
    meal_type: Optional[str] = Form("lunch", description="Meal type (breakfast, lunch, dinner, snack)"),
    user_description: Optional[str] = Form(None, description="Optional note or context about the meal"),
    _: None = Depends(require_operations_key),
):
    """
    Side-by-side Vision Benchmark: Claude Sonnet 4.6 (AWS Bedrock) vs OpenAI GPT-4o.

    Executes the COMPLETE Kalnur food logging workflow for both models:
    1. Identical spatial vision prompt with occlusion, submerged items, vessel depth & oil analysis
    2. Supabase live database matching (134+ enriched Nigerian foods + pgvector)
    3. Portion bounded normalization
    4. Full 16-nutrient computation
    5. Latency (ms), token metrics, and exact dollar cost per call
    """
    try:
        from kai.services.vision_benchmark_service import VisionBenchmarkService
        image_bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        benchmark_svc = VisionBenchmarkService()
        report = await benchmark_svc.execute_benchmark(
            image_bytes=image_bytes,
            meal_type=meal_type or "lunch",
            user_description=user_description,
        )
        return report

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("❌ Vision benchmark failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Benchmark execution failed: {str(exc)}")


@app.post("/api/v1/vision/benchmark-json")
async def vision_benchmark_json(
    payload: dict,
    _: None = Depends(require_operations_key),
):
    """
    JSON version of the Vision Benchmark endpoint for mobile app / automated test scripts.
    Accepts:
    {
        "image_base64": "data:image/jpeg;base64,...",
        "meal_type": "lunch",
        "user_description": "Optional note"
    }
    """
    try:
        from kai.services.vision_benchmark_service import VisionBenchmarkService
        raw_b64 = payload.get("image_base64", "")
        if not raw_b64:
            raise HTTPException(status_code=400, detail="'image_base64' is required.")

        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]

        image_bytes = base64.b64decode(raw_b64)
        meal_type = payload.get("meal_type", "lunch")
        user_description = payload.get("user_description")

        benchmark_svc = VisionBenchmarkService()
        report = await benchmark_svc.execute_benchmark(
            image_bytes=image_bytes,
            meal_type=meal_type,
            user_description=user_description,
        )
        return report

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("❌ Vision benchmark (JSON) failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Benchmark execution failed: {str(exc)}")


# ============================================================================
# Meal Endpoints
# ============================================================================

@app.get("/api/v1/meals/history", response_model=MealHistoryResponse)
async def get_meal_history(
    limit: int = 20,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),  # Extract from JWT token
):
    """Get user's meal history"""
    start = time.time()
    try:
        meals = await get_user_meals(user_id=user_id, limit=limit, offset=offset)

        return MealHistoryResponse(
            success=True,
            message=f"Retrieved {len(meals)} meals",
            meals=meals,
            total_count=len(meals),
            processing_time_ms=int((time.time() - start) * 1000),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# User Profile Endpoints
# ============================================================================

@app.get("/api/v1/users/profile", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: str = Depends(get_current_user_id),  # Extract from JWT token
):
    """
    Get user profile with health info and RDV values.

    Returns profile_complete flag indicating if weight/height/activity/goals are set.
    """
    start = time.time()
    try:
        profile = await get_user_health_profile(user_id)

        if not profile:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        coaching_done = await is_coaching_complete(user_id)

        return UserProfileResponse(
            success=True,
            message="User profile retrieved",
            user_id=profile["user_id"],
            email=profile.get("email"),
            name=profile.get("name"),
            gender=profile["gender"],
            age=profile["age"],
            weight_kg=profile.get("weight_kg"),
            height_cm=profile.get("height_cm"),
            activity_level=profile.get("activity_level"),
            health_goals=profile.get("health_goals"),
            dietary_restrictions=profile.get("dietary_restrictions"),
            target_weight_kg=profile.get("target_weight_kg"),
            calculated_calorie_goal=profile.get("calculated_calorie_goal"),
            custom_calorie_goal=profile.get("custom_calorie_goal"),
            active_calorie_goal=profile.get("active_calorie_goal"),
            profile_complete=profile.get("profile_complete", False),
            coaching_complete=coaching_done,
            rdv=profile["rdv"],
            processing_time_ms=int((time.time() - start) * 1000),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/users/account")
async def delete_user_account(
    user_id: str = Depends(get_current_user_id),
):
    """
    Permanently delete the authenticated user's account and all associated data.
    """
    try:
        deleted = await delete_user(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "message": "Account deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/users/health-profile")
async def update_health_profile(
    weight_kg: float = Form(..., description="Current weight in kilograms (30-300 kg)"),
    height_cm: float = Form(..., description="Height in centimeters (100-250 cm)"),
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"] = Form(
        ...,
        description="Activity level: sedentary (little/no exercise), light (1-3 days/week), moderate (3-5 days/week), active (6-7 days/week), very_active (physical job/athlete)"
    ),
    health_goals: Literal[
        "lose_weight", "gain_muscle", "maintain_weight", "general_wellness",
        "pregnancy", "heart_health", "energy_boost", "bone_health", "manage_blood_sugar"
    ] = Form(
        ...,
        description="Health goal: lose_weight, gain_muscle, maintain_weight, general_wellness, pregnancy, heart_health, energy_boost, bone_health, or manage_blood_sugar"
    ),
    target_weight_kg: float = Form(None, description="Goal weight for weight loss/gain tracking (optional)"),
    custom_calorie_goal: float = Form(None, description="Override KAI's calculated calorie recommendation (optional)"),
    name: str = Form(None, description="Display name (optional, used by Google OAuth users)"),
    gender: str = Form(None, description="Gender: male or female (optional, used by Google OAuth users)"),
    age: int = Form(None, description="Age in years (optional, used by Google OAuth users)"),
    user_id: str = Depends(get_current_user_id),
):
    """
    Complete or update user's health profile for full personalization.

    This endpoint enables BMR/TDEE-based calorie calculations and goal-specific coaching.

    Required fields:
        - weight_kg: Current weight (30-300 kg)
        - height_cm: Height (100-250 cm)
        - activity_level: Select from dropdown (sedentary, light, moderate, active, very_active)
        - health_goals: Select from dropdown (9 options: lose_weight, gain_muscle, maintain_weight, general_wellness, pregnancy, heart_health, energy_boost, bone_health, manage_blood_sugar)

    Optional fields:
        - target_weight_kg: Goal weight for weight loss/gain tracking
        - custom_calorie_goal: Override KAI's calculated calorie recommendation
    """
    start = time.time()

    try:
        # Validate required fields
        if not all([weight_kg, height_cm, activity_level, health_goals]):
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: weight_kg, height_cm, activity_level, health_goals"
            )

        # Validate weight range
        if weight_kg < 30 or weight_kg > 300:
            raise HTTPException(
                status_code=400,
                detail="Weight must be between 30 and 300 kg"
            )

        # Validate height range
        if height_cm < 100 or height_cm > 250:
            raise HTTPException(
                status_code=400,
                detail="Height must be between 100 and 250 cm"
            )

        # Validate activity level
        valid_activity_levels = ["sedentary", "light", "moderate", "active", "very_active"]
        if activity_level not in valid_activity_levels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid activity_level. Must be one of: {', '.join(valid_activity_levels)}"
            )

        # Validate health goals (all 9 supported goals)
        valid_health_goals = [
            "lose_weight", "gain_muscle", "maintain_weight", "general_wellness",
            "pregnancy", "heart_health", "energy_boost", "bone_health", "manage_blood_sugar"
        ]
        if health_goals not in valid_health_goals:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid health_goals. Must be one of: {', '.join(valid_health_goals)}"
            )

        # Get user profile first (needed for validation and RDV calculation)
        user = await get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User {user_id} not found. Please ensure you are logged in with a valid account."
            )

        # Google OAuth users pass name/gender/age here since they skip signup
        if name or gender or age:
            await update_user(
                user_id=user_id,
                name=name or None,
                gender=gender or None,
                age=age or None,
            )
            # Re-fetch user so RDV calculation uses updated values
            user = await get_user(user_id)

        # Treat 0 as None (user didn't provide custom goal)
        if custom_calorie_goal == 0:
            custom_calorie_goal = None

        # Validate custom calorie goal if provided
        if custom_calorie_goal is not None:
            min_calories = 1200 if user.get("gender") == "female" else 1500

            if custom_calorie_goal < min_calories:
                raise HTTPException(
                    status_code=400,
                    detail=f"Custom calorie goal is dangerously low. Minimum: {min_calories} kcal/day for {user.get('gender')}s. "
                           f"Very low calorie diets should be medically supervised."
                )

            if custom_calorie_goal > 5000:
                raise HTTPException(
                    status_code=400,
                    detail="Custom calorie goal exceeds safe maximum (5000 kcal/day)"
                )

        # Import the new RDV calculation function
        from kai.utils.nutrition_rdv import calculate_user_rdv_v2

        # Build user profile for calculation
        user_profile = {
            "weight_kg": weight_kg,
            "height_cm": height_cm,
            "age": user.get("age"),
            "gender": user.get("gender"),
            "activity_level": activity_level,
            "health_goals": health_goals,
            "target_weight_kg": target_weight_kg,
            "custom_calorie_goal": custom_calorie_goal
        }

        # Calculate personalized RDV using BMR/TDEE method
        rdv_result = calculate_user_rdv_v2(user_profile)

        # Update user_health table with new values
        await update_user_health(
            user_id=user_id,
            weight_kg=weight_kg,
            height_cm=height_cm,
            activity_level=activity_level,
            health_goals=health_goals,
            target_weight_kg=target_weight_kg,
            calculated_calorie_goal=rdv_result["recommended_calories"],
            custom_calorie_goal=custom_calorie_goal,
            active_calorie_goal=rdv_result["active_calories"],
        )

        # Build response
        response = {
            "success": True,
            "message": "Health profile updated successfully",
            "profile_complete": True,
            "calculated_rdv": {
                "bmr": rdv_result["bmr"],
                "tdee": rdv_result["tdee"],
                "recommended_calories": rdv_result["recommended_calories"],
                "active_calories": rdv_result["active_calories"]
            },
            "processing_time_ms": int((time.time() - start) * 1000)
        }

        # Add weight projection if available
        if "weight_projection" in rdv_result:
            response["weight_projection"] = rdv_result["weight_projection"]

        return response

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating health profile: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


class SugarPreferenceRequest(BaseModel):
    show_sugar: bool


@app.patch("/api/v1/users/sugar-preference")
async def update_sugar_preference_endpoint(
    request: SugarPreferenceRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Update the user's sugar tracking preference.

    When show_sugar is True, Kally will weave sugar impact awareness
    into coaching responses (chat + notes) as a complement to the
    user's primary goal — not replacing it.

    When show_sugar is False, Kally reverts to standard goal coaching.
    """
    try:
        await update_sugar_preference(user_id, request.show_sugar)
        return {
            "show_sugar": request.show_sugar,
            "message": "Sugar preference updated successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating sugar preference: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/users/nutrition-plan")
async def get_nutrition_plan(
    user_id: str = Depends(get_current_user_id),
):
    """
    Get the user's personalized nutrition plan based on their health goal.

    Returns the priority nutrients (6-8) for the user's goal with:
    - Emoji for visual display
    - Daily target value
    - Personalized explanation of why this nutrient matters

    Call this after completing health profile to show the user their plan.
    """
    start = time.time()

    try:
        # Get user profile
        profile = await get_user_health_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        # Check if profile is complete
        if not profile.get("profile_complete", False):
            raise HTTPException(
                status_code=400,
                detail="Health profile not complete. Please update your health profile first."
            )

        health_goal = profile.get("health_goals")
        gender = profile.get("gender")
        age = profile.get("age")
        active_calorie_goal = profile.get("custom_calorie_goal") or profile.get("active_calorie_goal")

        # Get priority nutrients for this goal
        priority_nutrients = get_priority_nutrients(health_goal)
        priority_rdvs = get_priority_rdvs(
            health_goal,
            gender=gender,
            age=age,
            custom_calorie_goal=active_calorie_goal
        )

        # Goal-specific explanations for WHY each nutrient matters
        nutrient_explanations = {
            "lose_weight": {
                "calories": "Track to maintain your calorie deficit",
                "protein": "Keeps you full & preserves muscle while losing fat",
                "fiber": "Increases satiety and supports gut health",
                "carbohydrates": "Manage for steady energy balance",
                "fat": "Essential but controlled for deficit",
                "sodium": "Reduce water retention and bloating",
            },
            "gain_muscle": {
                "calories": "Fuel your gains with a calorie surplus",
                "protein": "Builds and repairs muscle tissue",
                "carbohydrates": "Powers your workouts and recovery",
                "fat": "Supports hormone production for growth",
                "zinc": "Essential for protein synthesis and testosterone",
                "magnesium": "Muscle function and recovery",
                "vitamin_b12": "Energy metabolism and red blood cells",
            },
            "maintain_weight": {
                "calories": "Maintain energy balance",
                "protein": "Preserve your muscle mass",
                "carbohydrates": "Sustained daily energy",
                "fat": "Essential fatty acids for health",
                "fiber": "Digestive health and satiety",
                "iron": "Energy and vitality",
            },
            "general_wellness": {
                "calories": "Overall energy balance",
                "protein": "Body maintenance and repair",
                "fiber": "Gut health and digestion",
                "iron": "Energy and immune function",
                "vitamin_c": "Immunity and antioxidant protection",
                "calcium": "Bone and muscle function",
            },
            "pregnancy": {
                "calories": "Support growing baby (+300 kcal/day)",
                "protein": "Fetal tissue growth",
                "folate": "CRITICAL for neural tube development",
                "iron": "Prevent anemia, support blood volume",
                "calcium": "Baby's bone development",
                "vitamin_d": "Calcium absorption and immunity",
                "zinc": "Cell division and immune function",
                "vitamin_b12": "Neurological development",
            },
            "heart_health": {
                "calories": "Maintain healthy weight",
                "sodium": "Blood pressure control (limit intake)",
                "potassium": "Balances sodium for BP health",
                "fiber": "Cholesterol management",
                "fat": "Limit saturated fats",
                "magnesium": "Heart rhythm and blood pressure",
                "vitamin_c": "Vascular health and antioxidant",
            },
            "energy_boost": {
                "calories": "Adequate energy intake",
                "iron": "Oxygen transport, prevents fatigue",
                "vitamin_b12": "Energy metabolism",
                "carbohydrates": "Primary energy source",
                "magnesium": "ATP energy production",
                "vitamin_c": "Enhances iron absorption",
            },
            "bone_health": {
                "calories": "Maintain healthy weight for bones",
                "calcium": "Primary bone mineral",
                "vitamin_d": "Calcium absorption",
                "protein": "Bone matrix structure",
                "magnesium": "Bone mineral structure",
                "zinc": "Bone formation enzymes",
                "potassium": "Reduces calcium loss",
            },
        }

        goal_explanations = nutrient_explanations.get(
            health_goal,
            nutrient_explanations["general_wellness"]
        )

        # Build nutrient list with emojis
        nutrients = []
        for nutrient in priority_nutrients:
            rdv_obj = priority_rdvs.get(nutrient)
            if rdv_obj:
                nutrients.append({
                    "name": nutrient,
                    "display_name": rdv_obj.display_name,
                    "emoji": get_nutrient_emoji(nutrient),
                    "daily_target": rdv_obj.amount,
                    "unit": rdv_obj.unit,
                    "why": goal_explanations.get(nutrient, "Important for your goal"),
                })

        return {
            "success": True,
            "message": "Nutrition plan retrieved",
            "goal": health_goal,
            "nutrient_count": len(nutrients),
            "nutrients": nutrients,
            "processing_time_ms": int((time.time() - start) * 1000)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting nutrition plan: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/users/stats", response_model=UserStatsResponse)
async def get_user_stats(
    date: str = None,
    user_id: str = Depends(get_current_user_id),  # Extract from JWT token
):
    """
    Get user's daily nutrition statistics with goal-driven RDV percentages.

    Returns daily totals and percentage of RDV for each priority nutrient
    based on the user's health goal (6-8 nutrients).
    """
    start = time.time()
    try:
        from datetime import datetime as dt

        # Get daily totals
        daily_totals = await get_daily_nutrition_totals(user_id, date)

        # Fetch streak data (always, regardless of whether meals logged today)
        user_stats = await get_user_stats_db(user_id)
        current_streak = user_stats.get("current_logging_streak", 0) if user_stats else 0
        longest_streak = user_stats.get("longest_logging_streak", 0) if user_stats else 0

        if not daily_totals:
            return UserStatsResponse(
                success=True,
                message="No meals logged for this date",
                user_id=user_id,
                date=date or dt.today().date().isoformat(),
                daily_totals=None,
                rdv_percentages={},
                meal_count=0,
                current_logging_streak=current_streak,
                longest_logging_streak=longest_streak,
                processing_time_ms=int((time.time() - start) * 1000),
            )

        # Get user profile for RDV and goal info
        profile = await get_user_health_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        health_goal = profile.get("health_goals", "general_wellness")
        gender = profile.get("gender")
        age = profile.get("age")
        active_calorie_goal = profile.get("custom_calorie_goal") or profile.get("active_calorie_goal")

        # Get goal-driven priority nutrients with COMPLETE personalized RDVs
        # This uses get_priority_rdvs() which has RDVs for ALL 16 nutrients
        # (unlike profile["rdv"] which only has 8 basic ones)
        goal_context = get_goal_context(health_goal, gender, age, active_calorie_goal)
        priority_rdvs = goal_context["priority_rdvs"]

        # Map nutrient names to daily_nutrients DB column names
        nutrient_to_db_col = {
            "calories": "total_calories",
            "protein": "total_protein",
            "carbohydrates": "total_carbohydrates",
            "fat": "total_fat",
            "fiber": "total_fiber",
            "iron": "total_iron",
            "calcium": "total_calcium",
            "zinc": "total_zinc",
            "potassium": "total_potassium",
            "sodium": "total_sodium",
            "magnesium": "total_magnesium",
            "vitamin_a": "total_vitamin_a",
            "vitamin_c": "total_vitamin_c",
            "vitamin_d": "total_vitamin_d",
            "vitamin_b12": "total_vitamin_b12",
            "folate": "total_folate",
        }

        # Calculate RDV percentages using the complete priority RDVs
        rdv_percentages = {}
        for nutrient in goal_context["priority_nutrients"]:
            db_col = nutrient_to_db_col.get(nutrient, f"total_{nutrient}")
            daily_val = daily_totals.get(db_col, 0) or 0
            rdv_obj = priority_rdvs.get(nutrient)
            rdv_val = rdv_obj.amount if rdv_obj else 0
            rdv_percentages[nutrient] = round((daily_val / rdv_val) * 100, 1) if rdv_val > 0 else 0

        return UserStatsResponse(
            success=True,
            message="User statistics retrieved",
            user_id=user_id,
            date=daily_totals["date"],
            daily_totals=daily_totals,
            rdv_percentages=rdv_percentages,
            meal_count=daily_totals["meal_count"],
            current_logging_streak=current_streak,
            longest_logging_streak=longest_streak,
            processing_time_ms=int((time.time() - start) * 1000),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Stats failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Kally Notes Endpoints
# ============================================================================

@app.get("/api/v1/kally-notes")
async def get_kally_notes(
    user_id: str = Depends(get_current_user_id),
):
    """Get all Kally Notes for the user — notices, goal facts, general intel."""
    from kai.agents.kally_notes_agent import get_notes_for_user
    start = time.time()
    try:
        notes = await get_notes_for_user(user_id)
        notes["processing_time_ms"] = int((time.time() - start) * 1000)
        return notes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/kally-notes/seen")
async def mark_note_seen(
    body: dict,
    user_id: str = Depends(get_current_user_id),
):
    """
    Mark a note as seen.
    Body: { fact_id?: string, notice_text?: string, tapped_through: boolean }
    """
    from kai.database.db_setup import get_supabase
    from datetime import datetime as dt
    try:
        supabase = get_supabase()
        supabase.table("user_seen_facts").insert({
            "user_id": user_id,
            "fact_id": body.get("fact_id"),
            "notice_text": body.get("notice_text"),
            "section": body.get("section"),
            "tapped_through": body.get("tapped_through", False),
            "seen_at": dt.now().isoformat(),
        }).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================================
# Server Startup
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "kai.api.server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )


"""
Push Notification Database Operations

Stores and retrieves Web Push subscriptions per user.
Each user can have multiple subscriptions (phone + laptop etc).
"""

import logging
from typing import Optional
from datetime import datetime

from .db_setup import get_supabase

logger = logging.getLogger(__name__)


async def save_push_subscription(user_id: str, subscription: dict) -> None:
    """
    Save or update a push subscription for a user.
    Keyed on endpoint URL — same device updating just overwrites.
    """
    client = get_supabase()
    endpoint = subscription.get("endpoint", "")
    if not endpoint:
        raise ValueError("Subscription must have an endpoint")

    now = datetime.now().isoformat()

    # Upsert — same endpoint = same device, just refresh keys
    client.table("push_subscriptions").upsert({
        "user_id": user_id,
        "endpoint": endpoint,
        "subscription_json": subscription,
        "created_at": now,
        "updated_at": now,
    }, on_conflict="endpoint").execute()

    logger.info(f"✅ Push subscription saved for user {user_id}")


async def get_push_subscriptions(user_id: str) -> list[dict]:
    """
    Get all active push subscriptions for a user.
    Returns list of subscription dicts ready to pass to pywebpush.
    """
    client = get_supabase()
    result = client.table("push_subscriptions") \
        .select("subscription_json") \
        .eq("user_id", user_id) \
        .execute()

    return [row["subscription_json"] for row in (result.data or [])]


async def get_all_subscriptions() -> list[dict]:
    """
    Get all subscriptions across all users.
    Used by the scheduler to send notifications to everyone.
    Returns list of { user_id, subscription_json }.
    """
    client = get_supabase()
    result = client.table("push_subscriptions") \
        .select("user_id, subscription_json") \
        .execute()

    return result.data or []


async def delete_push_subscription(endpoint: str) -> None:
    """
    Delete a subscription by endpoint.
    Called when push delivery fails (subscription expired/revoked).
    """
    client = get_supabase()
    client.table("push_subscriptions") \
        .delete() \
        .eq("endpoint", endpoint) \
        .execute()

    logger.info(f"🗑️ Deleted expired push subscription: {endpoint[:60]}...")


# ── Native (Expo) push token operations ───────────────────────────────────────

async def save_native_push_token(user_id: str, token: str) -> None:
    """Upsert an Expo push token for a user. One row per token."""
    client = get_supabase()
    now = datetime.now().isoformat()
    client.table("native_push_tokens").upsert({
        "user_id": user_id,
        "token": token,
        "created_at": now,
        "updated_at": now,
    }, on_conflict="token").execute()
    logger.info(f"✅ Native push token saved for user {user_id}")


async def get_native_push_tokens(user_id: str) -> list[str]:
    """Return all Expo push tokens for a single user."""
    client = get_supabase()
    result = client.table("native_push_tokens") \
        .select("token") \
        .eq("user_id", user_id) \
        .execute()
    return [row["token"] for row in (result.data or [])]


async def get_all_native_tokens() -> list[dict]:
    """Return all native tokens across all users: [{ user_id, token }]."""
    client = get_supabase()
    result = client.table("native_push_tokens") \
        .select("user_id, token") \
        .execute()
    return result.data or []


async def delete_native_push_token(token: str) -> None:
    """Remove a native token (e.g. after DeviceNotRegistered error from Expo)."""
    client = get_supabase()
    client.table("native_push_tokens") \
        .delete() \
        .eq("token", token) \
        .execute()
    logger.info(f"🗑️ Deleted expired native push token: {token[:40]}...")

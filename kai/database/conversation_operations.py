"""
Conversation Database Operations - Supabase

CRUD operations for chat conversation history (persistent memory).
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

from .db_setup import get_supabase

logger = logging.getLogger(__name__)


async def save_chat_message(
    user_id: str,
    role: str,
    content: str
) -> bool:
    """
    Save a chat message to conversation history.

    Args:
        user_id: User identifier
        role: Message role ('user' or 'assistant')
        content: Message content

    Returns:
        bool: True if saved successfully

    Raises:
        ValueError: If role is invalid
    """
    if role not in ["user", "assistant"]:
        raise ValueError(f"Invalid role: {role}. Must be 'user' or 'assistant'")

    client = get_supabase()

    try:
        client.table("chat_conversations").insert({
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": datetime.now().isoformat()
        }).execute()

        logger.info(f"💬 Saved {role} message for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to save chat message: {e}")
        return False


async def get_conversation_history(
    user_id: str,
    limit: int = 20,
    today_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Get user's conversation history (most recent messages).

    Args:
        user_id: User identifier
        limit: Maximum number of messages to retrieve (default 20)
        today_only: If True, only return messages from today (default True).
                    Prevents stale old conversations from polluting current context.

    Returns:
        List of messages in chronological order (oldest first)
        Each message: {"role": str, "content": str, "created_at": str}
    """
    client = get_supabase()

    try:
        query = client.table("chat_conversations") \
            .select("role, content, created_at") \
            .eq("user_id", user_id)

        # Filter to today's messages only to avoid stale context from old sessions
        if today_only:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            query = query.gte("created_at", today_start)

        result = query \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()

        if not result.data:
            return []

        # Reverse to get chronological order (oldest first)
        messages = result.data[::-1]

        logger.info(f"📜 Retrieved {len(messages)} messages for user {user_id}")
        return messages

    except Exception as e:
        logger.error(f"Failed to retrieve conversation history: {e}")
        return []


async def clear_conversation_history(user_id: str) -> bool:
    """
    Clear user's entire conversation history.

    Args:
        user_id: User identifier

    Returns:
        bool: True if cleared successfully
    """
    client = get_supabase()

    try:
        client.table("chat_conversations") \
            .delete() \
            .eq("user_id", user_id) \
            .execute()

        logger.info(f"🗑️ Cleared conversation history for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to clear conversation history: {e}")
        return False


async def get_conversation_message_count(user_id: str) -> int:
    """
    Get total number of messages in user's conversation history.

    Args:
        user_id: User identifier

    Returns:
        int: Total message count
    """
    client = get_supabase()

    try:
        result = client.table("chat_conversations") \
            .select("id", count="exact") \
            .eq("user_id", user_id) \
            .execute()

        return result.count or 0

    except Exception as e:
        logger.error(f"Failed to count messages: {e}")
        return 0

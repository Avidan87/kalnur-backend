"""
KAI Database Package

User database management with Supabase for:
- User profiles and health data
- Meal logging history
- Daily nutrient tracking
- Session management
"""

from .db_setup import initialize_database, get_db, get_supabase
from .user_operations import (
    create_user,
    get_user,
    get_user_by_email,
    update_user,
    update_user_health,
    update_sugar_preference,
    get_user_health_profile,
    delete_user,
)
from .meal_operations import (
    log_meal,
    get_user_meals,
    get_meals_by_date,
    get_daily_nutrition_totals,
)
from .stats_operations import (
    get_user_stats,
    initialize_user_stats,
    update_user_stats,
    get_nutrient_trends,
)
from .conversation_operations import (
    save_chat_message,
    get_conversation_history,
    clear_conversation_history,
    get_conversation_message_count,
)
from .meal_search_operations import (
    get_meals_by_date_range,
    search_meals_by_food,
    get_food_frequency,
    parse_relative_date,
)
from .coaching_operations import (
    get_user_coaching,
    is_coaching_complete,
    save_user_coaching,
    mark_coaching_complete,
    reset_coaching_step,
    reset_coaching_full,
)
from .push_operations import (
    save_push_subscription,
    get_push_subscriptions,
    get_all_subscriptions,
    delete_push_subscription,
    save_native_push_token,
    get_native_push_tokens,
    get_all_native_tokens,
    delete_native_push_token,
)
from .missing_foods_operations import (
    log_missing_food,
    get_missing_foods,
    update_missing_food_status,
    mark_user_notified,
)

__all__ = [
    # Database setup
    "initialize_database",
    "get_db",

    # User operations
    "create_user",
    "get_user",
    "get_user_by_email",
    "update_user",
    "update_user_health",
    "update_sugar_preference",
    "get_user_health_profile",
    "delete_user",

    # Meal operations
    "log_meal",
    "get_user_meals",
    "get_meals_by_date",
    "get_daily_nutrition_totals",

    # Stats operations
    "get_user_stats",
    "initialize_user_stats",
    "update_user_stats",
    "get_nutrient_trends",

    # Conversation operations
    "save_chat_message",
    "get_conversation_history",
    "clear_conversation_history",
    "get_conversation_message_count",

    # Meal search operations
    "get_meals_by_date_range",
    "search_meals_by_food",
    "get_food_frequency",
    "parse_relative_date",
    "get_supabase",

    # Coaching operations
    "get_user_coaching",
    "is_coaching_complete",
    "save_user_coaching",
    "mark_coaching_complete",
    "reset_coaching_step",
    "reset_coaching_full",

    # Push notification operations
    "save_push_subscription",
    "get_push_subscriptions",
    "get_all_subscriptions",
    "delete_push_subscription",
    "save_native_push_token",
    "get_native_push_tokens",
    "get_all_native_tokens",
    "delete_native_push_token",

    # Missing foods logger
    "log_missing_food",
    "get_missing_foods",
    "update_missing_food_status",
    "mark_user_notified",
]

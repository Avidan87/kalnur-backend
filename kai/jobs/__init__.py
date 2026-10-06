"""
KAI Background Jobs Package

Background jobs for async operations:
- User stats calculation
- Weekly food frequency reset
- Recommendation tracking
"""

from .update_user_stats import calculate_and_update_user_stats

__all__ = [
    "calculate_and_update_user_stats",
]

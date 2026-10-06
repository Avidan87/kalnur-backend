-- ============================================================================
-- Missing Foods — User Tracking Columns
-- Adds user_ids and notified_user_ids arrays so we can:
--   1. Know which users requested each missing food (for Email 2 later)
--   2. Track who already received Email 1 (no duplicate notifications)
-- ============================================================================

ALTER TABLE missing_foods
    ADD COLUMN IF NOT EXISTS user_ids          TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS notified_user_ids TEXT[] DEFAULT '{}';

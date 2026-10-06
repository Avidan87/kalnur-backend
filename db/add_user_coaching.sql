-- ============================================================================
-- Add user_coaching table
-- Run this in the Supabase SQL Editor
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_coaching (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    barrier TEXT,                          -- goal-specific barrier answer
    food_habits TEXT,                      -- food habits answer
    motivation_score INTEGER CHECK(motivation_score >= 1 AND motivation_score <= 10),
    coaching_complete BOOLEAN DEFAULT FALSE,
    completed_at TIMESTAMPTZ
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_user_coaching_user_id ON user_coaching(user_id);

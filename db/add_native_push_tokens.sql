-- Migration: native_push_tokens
-- Stores Expo push tokens for React Native app users.
-- One row per token; a user can have multiple devices.

CREATE TABLE IF NOT EXISTS native_push_tokens (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token       TEXT        NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_native_push_tokens_user_id ON native_push_tokens(user_id);

-- RLS: users can only see their own tokens; service role bypasses RLS.
ALTER TABLE native_push_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own native tokens"
    ON native_push_tokens
    FOR ALL
    USING (auth.uid()::TEXT = user_id)
    WITH CHECK (auth.uid()::TEXT = user_id);

-- ============================================================================
-- Migration 003: Add Conversation Memory System
-- Version: 3.2.0
-- Date: February 2026
-- ============================================================================

-- Chat conversation history (persistent memory)
CREATE TABLE IF NOT EXISTS chat_conversations (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient conversation retrieval
CREATE INDEX IF NOT EXISTS idx_chat_conversations ON chat_conversations(user_id, created_at DESC);

-- ============================================================================
-- Verification Query
-- ============================================================================
-- Run this to verify the migration:
-- SELECT * FROM chat_conversations LIMIT 1;

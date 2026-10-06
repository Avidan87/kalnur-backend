-- ============================================================================
-- Missing Foods Logger
-- Tracks foods users add that are not found in Kalnur's knowledge base.
-- Avidan reviews this table, researches nutrition data, and adds to KB.
-- ============================================================================

CREATE TABLE IF NOT EXISTS missing_foods (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    food_name        TEXT NOT NULL,
    requested_count  INTEGER DEFAULT 1,
    unique_users     INTEGER DEFAULT 1,
    first_seen       TIMESTAMPTZ DEFAULT NOW(),
    last_seen        TIMESTAMPTZ DEFAULT NOW(),
    status           TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'researching', 'added'))
);

-- Index for fast lookups by name (for upsert on new requests)
CREATE INDEX IF NOT EXISTS idx_missing_foods_name
    ON missing_foods (LOWER(food_name));

-- Index for dashboard queries sorted by most requested
CREATE INDEX IF NOT EXISTS idx_missing_foods_count
    ON missing_foods (requested_count DESC);

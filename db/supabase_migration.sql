-- ============================================================================
-- KAI Supabase Migration Script
-- Run this in the Supabase SQL Editor to create all tables + pgvector
-- ============================================================================

-- Enable pgvector extension for food embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Core Tables
-- ============================================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    name TEXT,
    gender TEXT CHECK(gender IN ('male', 'female')),
    age INTEGER CHECK(age >= 13 AND age <= 120),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- User health information
CREATE TABLE IF NOT EXISTS user_health (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    weight_kg REAL,
    height_cm REAL,
    activity_level TEXT CHECK(activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')),
    health_goals TEXT CHECK(health_goals IN ('lose_weight', 'gain_muscle', 'maintain_weight', 'general_wellness', 'pregnancy', 'heart_health', 'energy_boost', 'bone_health')),
    target_weight_kg REAL,
    calculated_calorie_goal REAL,
    custom_calorie_goal REAL,
    active_calorie_goal REAL,
    dietary_restrictions TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Meals table
CREATE TABLE IF NOT EXISTS meals (
    meal_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    meal_type TEXT CHECK(meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
    meal_date TEXT NOT NULL,
    meal_time TEXT NOT NULL,
    image_url TEXT,
    user_description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Foods within meals - 16 nutrients
CREATE TABLE IF NOT EXISTS meal_foods (
    id SERIAL PRIMARY KEY,
    meal_id TEXT NOT NULL REFERENCES meals(meal_id) ON DELETE CASCADE,
    food_name TEXT NOT NULL,
    food_id TEXT,
    portion_grams REAL NOT NULL,
    -- Macros (5)
    calories REAL NOT NULL,
    protein REAL NOT NULL,
    carbohydrates REAL NOT NULL,
    fat REAL NOT NULL,
    fiber REAL DEFAULT 0.0,
    -- Minerals (6)
    iron REAL NOT NULL,
    calcium REAL NOT NULL,
    zinc REAL NOT NULL,
    potassium REAL NOT NULL,
    sodium REAL DEFAULT 0.0,
    magnesium REAL DEFAULT 0.0,
    -- Vitamins (5)
    vitamin_a REAL DEFAULT 0.0,
    vitamin_c REAL DEFAULT 0.0,
    vitamin_d REAL DEFAULT 0.0,
    vitamin_b12 REAL DEFAULT 0.0,
    folate REAL DEFAULT 0.0,
    confidence REAL DEFAULT 1.0
);

-- Daily nutrient totals (aggregated) - 16 nutrients
CREATE TABLE IF NOT EXISTS daily_nutrients (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    -- Macros (5)
    total_calories REAL DEFAULT 0,
    total_protein REAL DEFAULT 0,
    total_carbohydrates REAL DEFAULT 0,
    total_fat REAL DEFAULT 0,
    total_fiber REAL DEFAULT 0,
    -- Minerals (6)
    total_iron REAL DEFAULT 0,
    total_calcium REAL DEFAULT 0,
    total_zinc REAL DEFAULT 0,
    total_potassium REAL DEFAULT 0,
    total_sodium REAL DEFAULT 0,
    total_magnesium REAL DEFAULT 0,
    -- Vitamins (5)
    total_vitamin_a REAL DEFAULT 0,
    total_vitamin_c REAL DEFAULT 0,
    total_vitamin_d REAL DEFAULT 0,
    total_vitamin_b12 REAL DEFAULT 0,
    total_folate REAL DEFAULT 0,
    meal_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

-- ============================================================================
-- Coaching System Tables
-- ============================================================================

-- Chat conversation history (persistent memory)
CREATE TABLE IF NOT EXISTS chat_conversations (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User nutrition statistics (pre-computed)
CREATE TABLE IF NOT EXISTS user_nutrition_stats (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    total_meals_logged INTEGER DEFAULT 0,
    account_age_days INTEGER DEFAULT 0,
    learning_phase_complete BOOLEAN DEFAULT FALSE,
    current_logging_streak INTEGER DEFAULT 0,
    longest_logging_streak INTEGER DEFAULT 0,
    last_logged_date TEXT,
    -- Week 1 Averages
    week1_avg_calories REAL DEFAULT 0,
    week1_avg_protein REAL DEFAULT 0,
    week1_avg_carbs REAL DEFAULT 0,
    week1_avg_fat REAL DEFAULT 0,
    week1_avg_iron REAL DEFAULT 0,
    week1_avg_calcium REAL DEFAULT 0,
    week1_avg_potassium REAL DEFAULT 0,
    week1_avg_zinc REAL DEFAULT 0,
    -- Week 2 Averages
    week2_avg_calories REAL DEFAULT 0,
    week2_avg_protein REAL DEFAULT 0,
    week2_avg_carbs REAL DEFAULT 0,
    week2_avg_fat REAL DEFAULT 0,
    week2_avg_iron REAL DEFAULT 0,
    week2_avg_calcium REAL DEFAULT 0,
    week2_avg_potassium REAL DEFAULT 0,
    week2_avg_zinc REAL DEFAULT 0,
    -- Trends
    calories_trend TEXT DEFAULT 'stable',
    protein_trend TEXT DEFAULT 'stable',
    carbs_trend TEXT DEFAULT 'stable',
    fat_trend TEXT DEFAULT 'stable',
    iron_trend TEXT DEFAULT 'stable',
    calcium_trend TEXT DEFAULT 'stable',
    potassium_trend TEXT DEFAULT 'stable',
    zinc_trend TEXT DEFAULT 'stable',
    last_calculated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- pgvector: Nigerian Foods Vector Table (replaces ChromaDB)
-- ============================================================================

CREATE TABLE IF NOT EXISTS nigerian_foods (
    food_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    region TEXT DEFAULT 'Nigeria',
    price_tier TEXT DEFAULT 'mid',
    availability TEXT DEFAULT 'widely_available',
    confidence REAL DEFAULT 0.0,
    -- Nutrients per 100g (16 nutrients)
    calories REAL DEFAULT 0,
    protein REAL DEFAULT 0,
    carbohydrates REAL DEFAULT 0,
    fat REAL DEFAULT 0,
    fiber REAL DEFAULT 0,
    iron REAL DEFAULT 0,
    calcium REAL DEFAULT 0,
    zinc REAL DEFAULT 0,
    potassium REAL DEFAULT 0,
    sodium REAL DEFAULT 0,
    magnesium REAL DEFAULT 0,
    vitamin_a REAL DEFAULT 0,
    vitamin_c REAL DEFAULT 0,
    vitamin_d REAL DEFAULT 0,
    vitamin_b12 REAL DEFAULT 0,
    folate REAL DEFAULT 0,
    -- Metadata
    dietary_flags TEXT DEFAULT '',
    meal_types TEXT DEFAULT '',
    typical_portion_g REAL DEFAULT 150,
    min_reasonable_g REAL DEFAULT 50,
    max_reasonable_g REAL DEFAULT 300,
    -- Searchable text document
    document TEXT NOT NULL,
    -- pgvector embedding (3072 dimensions for text-embedding-3-large)
    embedding vector(3072)
);

-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_meals_user_date ON meals(user_id, meal_date);
CREATE INDEX IF NOT EXISTS idx_daily_nutrients_user_date ON daily_nutrients(user_id, date);
CREATE INDEX IF NOT EXISTS idx_chat_conversations ON chat_conversations(user_id, created_at DESC);

-- NOTE: pgvector index skipped for now.
-- With <100 foods, sequential scan is fast enough.
-- Add an index later if dataset grows to 1000+ rows:
--   CREATE INDEX idx_nigerian_foods_embedding ON nigerian_foods
--   USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- ============================================================================
-- RPC Functions for vector search
-- ============================================================================

-- Semantic search function for finding similar foods
CREATE OR REPLACE FUNCTION search_foods(
    query_embedding vector(3072),
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    food_id TEXT,
    name TEXT,
    category TEXT,
    similarity FLOAT,
    calories REAL,
    protein REAL,
    carbohydrates REAL,
    fat REAL,
    fiber REAL,
    iron REAL,
    calcium REAL,
    zinc REAL,
    potassium REAL,
    sodium REAL,
    magnesium REAL,
    vitamin_a REAL,
    vitamin_c REAL,
    vitamin_d REAL,
    vitamin_b12 REAL,
    folate REAL,
    dietary_flags TEXT,
    meal_types TEXT,
    typical_portion_g REAL,
    min_reasonable_g REAL,
    max_reasonable_g REAL,
    price_tier TEXT,
    document TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        nf.food_id,
        nf.name,
        nf.category,
        (1 - (nf.embedding <=> query_embedding))::FLOAT AS similarity,
        nf.calories,
        nf.protein,
        nf.carbohydrates,
        nf.fat,
        nf.fiber,
        nf.iron,
        nf.calcium,
        nf.zinc,
        nf.potassium,
        nf.sodium,
        nf.magnesium,
        nf.vitamin_a,
        nf.vitamin_c,
        nf.vitamin_d,
        nf.vitamin_b12,
        nf.folate,
        nf.dietary_flags,
        nf.meal_types,
        nf.typical_portion_g,
        nf.min_reasonable_g,
        nf.max_reasonable_g,
        nf.price_tier,
        nf.document
    FROM nigerian_foods nf
    ORDER BY nf.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function to get foods by nutrient value
CREATE OR REPLACE FUNCTION get_foods_by_nutrient(
    nutrient_name TEXT,
    min_value REAL,
    max_results INT DEFAULT 10
)
RETURNS TABLE (
    food_id TEXT,
    name TEXT,
    category TEXT,
    nutrient_value REAL
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT food_id, name, category, %I::REAL AS nutrient_value
         FROM nigerian_foods
         WHERE %I >= $1
         ORDER BY %I DESC
         LIMIT $2',
        nutrient_name, nutrient_name, nutrient_name
    ) USING min_value, max_results;
END;
$$;

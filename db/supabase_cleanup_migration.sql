-- ============================================================================
-- KAI Cleanup Migration: Remove Unused Tables
--
-- This migration removes 2 tables that were defined but never integrated:
-- 1. user_food_frequency (food tracking feature - never implemented)
-- 2. user_recommendation_responses (recommendation system - never implemented)
--
-- SAFETY CHECK: Verify these tables are empty before running this script
-- Run in Supabase SQL Editor
-- ============================================================================

-- Check row counts before deletion (INFORMATIONAL ONLY)
-- SELECT 'user_food_frequency' as table_name, COUNT(*) as row_count FROM user_food_frequency
-- UNION ALL
-- SELECT 'user_recommendation_responses', COUNT(*) FROM user_recommendation_responses;

-- ============================================================================
-- Drop Unused Tables
-- ============================================================================

-- Drop indexes first (safe if they don't exist)
DROP INDEX IF EXISTS idx_food_frequency_7d;
DROP INDEX IF EXISTS idx_recommendations;

-- Drop tables (CASCADE removes foreign key dependencies)
DROP TABLE IF EXISTS user_food_frequency CASCADE;
DROP TABLE IF EXISTS user_recommendation_responses CASCADE;

-- ============================================================================
-- Verification
-- ============================================================================

-- List remaining tables (should show 7 tables)
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Expected tables after cleanup:
-- 1. users
-- 2. user_health
-- 3. meals
-- 4. meal_foods
-- 5. daily_nutrients
-- 6. user_nutrition_stats
-- 7. nigerian_foods

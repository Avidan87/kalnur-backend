-- Kalnur public-deployment hardening
--
-- Run this after the schema and feature migrations in a Supabase project that
-- is connected to an untrusted client. The FastAPI server uses the service-role
-- key and therefore bypasses RLS. Do not expose that key to a client.

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_health ENABLE ROW LEVEL SECURITY;
ALTER TABLE meals ENABLE ROW LEVEL SECURITY;
ALTER TABLE meal_foods ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_nutrients ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_nutrition_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_coaching ENABLE ROW LEVEL SECURITY;
ALTER TABLE native_push_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE missing_foods ENABLE ROW LEVEL SECURITY;
ALTER TABLE nigerian_foods ENABLE ROW LEVEL SECURITY;

-- The public client calls the FastAPI API; it does not need direct Data API
-- access to these tables. Remove client-role grants as a second layer of
-- protection. The service_role used by the server is unaffected and bypasses
-- RLS, so it must remain server-only.
REVOKE ALL PRIVILEGES ON TABLE users, user_health, meals, meal_foods,
    daily_nutrients, chat_conversations, user_nutrition_stats, user_coaching,
    native_push_tokens, missing_foods, nigerian_foods FROM anon, authenticated;

-- A user may access only rows associated with their own Supabase Auth user id.
DROP POLICY IF EXISTS users_self ON users;
CREATE POLICY users_self ON users FOR ALL TO authenticated
    USING ((select auth.uid())::TEXT = user_id)
    WITH CHECK ((select auth.uid())::TEXT = user_id);

DROP POLICY IF EXISTS user_health_self ON user_health;
CREATE POLICY user_health_self ON user_health FOR ALL TO authenticated
    USING ((select auth.uid())::TEXT = user_id)
    WITH CHECK ((select auth.uid())::TEXT = user_id);

DROP POLICY IF EXISTS meals_self ON meals;
CREATE POLICY meals_self ON meals FOR ALL TO authenticated
    USING ((select auth.uid())::TEXT = user_id)
    WITH CHECK ((select auth.uid())::TEXT = user_id);

DROP POLICY IF EXISTS meal_foods_for_own_meals ON meal_foods;
CREATE POLICY meal_foods_for_own_meals ON meal_foods FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM meals WHERE meals.meal_id = meal_foods.meal_id
        AND meals.user_id = (select auth.uid())::TEXT
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM meals WHERE meals.meal_id = meal_foods.meal_id
        AND meals.user_id = (select auth.uid())::TEXT
    ));

DROP POLICY IF EXISTS daily_nutrients_self ON daily_nutrients;
CREATE POLICY daily_nutrients_self ON daily_nutrients FOR ALL TO authenticated
    USING ((select auth.uid())::TEXT = user_id)
    WITH CHECK ((select auth.uid())::TEXT = user_id);

DROP POLICY IF EXISTS chat_conversations_self ON chat_conversations;
CREATE POLICY chat_conversations_self ON chat_conversations FOR ALL TO authenticated
    USING ((select auth.uid())::TEXT = user_id)
    WITH CHECK ((select auth.uid())::TEXT = user_id);

DROP POLICY IF EXISTS user_nutrition_stats_self ON user_nutrition_stats;
CREATE POLICY user_nutrition_stats_self ON user_nutrition_stats FOR ALL TO authenticated
    USING ((select auth.uid())::TEXT = user_id)
    WITH CHECK ((select auth.uid())::TEXT = user_id);

DROP POLICY IF EXISTS user_coaching_self ON user_coaching;
CREATE POLICY user_coaching_self ON user_coaching FOR ALL TO authenticated
    USING ((select auth.uid())::TEXT = user_id)
    WITH CHECK ((select auth.uid())::TEXT = user_id);

DROP POLICY IF EXISTS "Users manage own native tokens" ON native_push_tokens;
DROP POLICY IF EXISTS native_push_tokens_self ON native_push_tokens;
CREATE POLICY native_push_tokens_self ON native_push_tokens FOR ALL TO authenticated
    USING ((select auth.uid())::TEXT = user_id)
    WITH CHECK ((select auth.uid())::TEXT = user_id);

-- The food knowledge base and missing-food queue are server-managed. With RLS
-- enabled and no client policy, only the server's service role can access them.
REVOKE ALL ON FUNCTION search_foods(vector, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION get_foods_by_nutrient(text, real, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION search_foods(vector, integer) TO service_role;
GRANT EXECUTE ON FUNCTION get_foods_by_nutrient(text, real, integer) TO service_role;

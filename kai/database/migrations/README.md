# KAI Database Migrations

This directory contains SQL migration scripts for database schema updates.

## How to Apply Migrations

### For Supabase Users (Production/Staging)

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Copy the contents of the migration file
4. Paste and execute in the SQL Editor

### For Local Development

```bash
# Connect to your local PostgreSQL
psql -U postgres -d kai_db

# Run the migration
\i kai/database/migrations/003_add_chat_conversations.sql
```

## Migration History

| Version | Date | Description | File |
|---------|------|-------------|------|
| 3.2.0 | Feb 2026 | Add conversation memory system | `003_add_chat_conversations.sql` |
| 3.1.0 | Feb 2026 | Database cleanup (removed unused tables) | - |
| 3.0.0 | Feb 2026 | Initial schema | `supabase_migration.sql` |

## Migration Order

Migrations should be applied in numerical order:
1. `supabase_migration.sql` (initial schema)
2. `003_add_chat_conversations.sql` (conversation memory)

## Verification

After applying a migration, verify it worked:

```sql
-- Check if chat_conversations table exists
SELECT * FROM chat_conversations LIMIT 1;

-- Check if index exists
SELECT indexname FROM pg_indexes WHERE tablename = 'chat_conversations';
```

## Rollback

To rollback the conversation memory migration:

```sql
DROP INDEX IF EXISTS idx_chat_conversations;
DROP TABLE IF EXISTS chat_conversations;
```

⚠️ **Warning:** This will permanently delete all conversation history!

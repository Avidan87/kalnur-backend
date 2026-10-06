"""
Seed Health Facts into Supabase pgvector

Usage:
  python seed_health_facts.py           # adds new facts only (safe to re-run)
  python seed_health_facts.py --reset   # wipes table and reinserts everything

Stable IDs in health_facts.jsonl mean user_seen_facts references survive resets.
"""

import sys
from kai.rag.health_facts_setup import HealthFactsVectorDB

JSONL_PATH = "knowledge-base/data/processed/health_facts.jsonl"

if __name__ == "__main__":
    reset = "--reset" in sys.argv

    print("\n" + "=" * 60)
    print("SEEDING HEALTH FACTS → SUPABASE PGVECTOR")
    print("=" * 60)

    db = HealthFactsVectorDB()

    if reset:
        print("\n⚠️  --reset flag detected — wiping existing health_facts...")
        db.reset()

    stats_before = db.get_stats()
    print(f"\n📊 Facts currently in DB: {stats_before['total_facts']}")

    if stats_before['total_facts'] > 0 and not reset:
        print("ℹ️  Table already populated. Running upsert (new facts only).")
        print("   Use --reset to wipe and reload everything.\n")

    count = db.load_facts_from_jsonl(JSONL_PATH)

    stats_after = db.get_stats()

    print("\n" + "=" * 60)
    print("✅ HEALTH FACTS SEED COMPLETE")
    print("=" * 60)
    print(f"📦 Total facts in DB: {stats_after['total_facts']}")
    print(f"🔢 Embedding dimensions: {stats_after['embedding_dimensions']}")
    print(f"💾 Storage: {stats_after['storage']}")
    print("=" * 60 + "\n")

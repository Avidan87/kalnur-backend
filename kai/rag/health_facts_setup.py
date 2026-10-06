"""
Health Facts Vector DB - Supabase pgvector

Mirrors NigerianFoodVectorDB pattern exactly.
Handles semantic search over health_facts table for Kally Notes chat memory.
"""

import json
import os
import sys
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
logger = logging.getLogger(__name__)


class HealthFactsVectorDB:
    """Vector database for health facts using Supabase pgvector"""

    def __init__(self, openai_api_key: Optional[str] = None):
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        self.openai_client = OpenAI(api_key=api_key)
        self.embedding_model = "text-embedding-3-large"

        from kai.database.db_setup import get_supabase
        self.supabase = get_supabase()

        logger.info("✓ HealthFactsVectorDB initialized with Supabase pgvector")

    def _get_embedding(self, text: str) -> List[float]:
        response = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding

    def _create_document_text(self, fact: Dict[str, Any]) -> str:
        parts = [
            f"Health fact: {fact['content']}",
            f"Category: {fact.get('category', '')}",
            f"Section: {fact.get('section', '')}",
            f"Relevant goals: {', '.join(fact.get('goal_tags', []))}",
            f"Trigger foods: {', '.join(fact.get('trigger_foods', []))}",
            f"Severity: {fact.get('severity', 'medium')}",
        ]
        return "\n".join(parts)

    def load_facts_from_jsonl(self, jsonl_path: str) -> int:
        facts_loaded = 0
        print(f"\n📂 Loading health facts from {jsonl_path}...")

        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    fact = json.loads(line)
                    doc_text = self._create_document_text(fact)
                    embedding = self._get_embedding(doc_text)

                    row = {
                        "id": fact["id"],
                        "content": fact["content"],
                        "section": fact["section"],
                        "category": fact.get("category", ""),
                        "goal_tags": fact.get("goal_tags", []),
                        "trigger_foods": fact.get("trigger_foods", []),
                        "severity": fact.get("severity", "medium"),
                        "document": doc_text,
                        "embedding": embedding,
                    }

                    self.supabase.table("health_facts").upsert(row).execute()
                    facts_loaded += 1
                    print(f"   ✓ [{facts_loaded}] {fact['id']}")

                except json.JSONDecodeError as e:
                    print(f"   ✗ Error parsing line {line_num}: {e}")
                except Exception as e:
                    print(f"   ✗ Error processing line {line_num} ({fact.get('id', '?')}): {e}")

        print(f"\n   ✓ Successfully loaded {facts_loaded} facts to Supabase pgvector")
        return facts_loaded

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_section: Optional[str] = None,
        filter_goal: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search over health_facts via the search_health_facts RPC."""
        query_embedding = self._get_embedding(query)

        result = self.supabase.rpc("search_health_facts", {
            "query_embedding": query_embedding,
            "match_count": n_results,
            "filter_section": filter_section,
            "filter_goal": filter_goal,
        }).execute()

        return result.data or []

    def get_stats(self) -> Dict[str, Any]:
        result = self.supabase.table("health_facts").select(
            "id", count="exact"
        ).limit(0).execute()
        return {
            "total_facts": result.count or 0,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": 3072,
            "storage": "Supabase pgvector",
        }

    def reset(self):
        self.supabase.table("health_facts").delete().neq(
            "id", "___impossible___"
        ).execute()
        print("✓ health_facts table reset")

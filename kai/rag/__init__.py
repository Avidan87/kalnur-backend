"""
RAG (Retrieval-Augmented Generation) module for KAI

This module provides vector database functionality using Supabase pgvector
with OpenAI embeddings for semantic search of Nigerian food data.
"""

from .chromadb_setup import NigerianFoodVectorDB, initialize_chromadb

__all__ = ["NigerianFoodVectorDB", "initialize_chromadb"]

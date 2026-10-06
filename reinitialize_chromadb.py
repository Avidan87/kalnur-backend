"""
Reinitialize Food Vector DB (Supabase pgvector)

This script resets the food vector database and loads nigerian_foods_v2_improved.jsonl
with high-quality, researched Nigerian food entries into Supabase pgvector.
"""

from kai.rag.chromadb_setup import initialize_chromadb

if __name__ == "__main__":
    print("\n" + "="*70)
    print("REINITIALIZING FOOD VECTOR DB (SUPABASE PGVECTOR)")
    print("="*70 + "\n")

    print("This will:")
    print("  1. Delete existing food vectors from Supabase")
    print("  2. Load nigerian_foods_v2_improved.jsonl into your Supabase project")
    print("  3. Create new OpenAI embeddings and store in pgvector\n")

    # Initialize with reset=True to reload data
    vector_db = initialize_chromadb(
        enriched_foods_path="knowledge-base/data/processed/nigerian_foods_v2_improved.jsonl",
        persist_directory="chromadb_data",
        reset=True  # Force reload
    )

    # Test the database
    print("\n" + "="*70)
    print("TESTING NEW DATABASE")
    print("="*70 + "\n")

    # Test 1: Search for a known food after the seed.
    print("Test 1: Searching for 'Egg Sauce'...")
    results = vector_db.search("egg sauce", n_results=1)
    if results:
        food = results[0]
        print(f"  ✓ Found: {food['name']}")
        print(f"  ✓ Protein per 100g: {food['metadata']['protein']}g")
        print(f"  ✓ Calories per 100g: {food['metadata']['calories']}")
        print(f"  ✓ Similarity: {food['similarity']:.3f}\n")
    else:
        print("  ✗ Not found\n")

    # Test 2: Search for a second known food.
    print("Test 2: Searching for 'Jollof Rice'...")
    results = vector_db.search("jollof rice", n_results=1)
    if results:
        food = results[0]
        print(f"  ✓ Found: {food['name']}")
        print(f"  ✓ Calories per 100g: {food['metadata']['calories']}")
        print(f"  ✓ Fat per 100g: {food['metadata']['fat']}g")
        print(f"  ✓ Similarity: {food['similarity']:.3f}\n")
    else:
        print("  ✗ Not found\n")

    # Test 3: Get collection stats
    print("Test 3: Collection Statistics...")
    stats = vector_db.get_collection_stats()
    print(f"  ✓ Total foods: {stats['total_foods']}")
    print(f"  ✓ Embedding model: {stats['embedding_model']}")
    print(f"  ✓ Persist directory: {stats['persist_directory']}\n")

    # Test 4: Find high-protein foods
    print("Test 4: Finding high-protein foods (>15g per 100g)...")
    results = vector_db.get_foods_by_nutrient("protein", min_value=15.0, n_results=5)
    if results:
        print(f"  ✓ Found {len(results)} high-protein foods:")
        for i, food in enumerate(results[:5], 1):
            print(f"    {i}. {food['name']}: {food['protein_per_100g']}g protein")
    else:
        print("  ✗ No high-protein foods found")

    # Test 5: Search for a third known food.
    print("\nTest 5: Searching for 'Yam Porridge'...")
    results = vector_db.search("yam porridge", n_results=1)
    if results:
        food = results[0]
        print(f"  ✓ Found: {food['name']}")
        print(f"  ✓ Calories per 100g: {food['metadata']['calories']}")
        print(f"  ✓ Fat per 100g: {food['metadata']['fat']}g")
        print(f"  ✓ Similarity: {food['similarity']:.3f}")
    else:
        print("  ✗ Yam Porridge not found - check database!")

    print("\n" + "="*70)
    print("✅ FOOD VECTOR DB REINITIALIZATION COMPLETE!")
    print("="*70)
    print("\nReview the seeded data and validate output against meals you are authorised to use.\n")

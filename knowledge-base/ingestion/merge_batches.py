"""
Merge Nigerian Foods Batches
Combines batch 1 and batch 2 JSONL files into a unified nigerian_llm_complete.jsonl
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

# Tracked nutrients for QA reporting
TRACKED_NUTRIENTS = [
    "protein",
    "fat",
    "carbohydrates",
    "iron",
    "calcium",
    "vitamin_a",
    "zinc",
]


def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """Load records from a JSONL file."""
    records = []
    if not file_path.exists():
        print(f"⚠️  File not found: {file_path}")
        return records
    
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"⚠️  Skipping invalid JSON line: {e}")
    
    return records


def save_jsonl(records: List[Dict[str, Any]], file_path: Path) -> None:
    """Save records to a JSONL file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with file_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def generate_qa_report(records: List[Dict[str, Any]], batch_name: str = "UNIFIED") -> str:
    """Generate QA summary report."""
    total = len(records)
    if total == 0:
        return "No records found."
    
    # Count missingness per nutrient
    missing_counts = {k: 0 for k in TRACKED_NUTRIENTS}
    confidence_sum = 0.0
    source_counts = 0
    
    for record in records:
        nutrients = record.get("nutrients", {})
        for key in TRACKED_NUTRIENTS:
            if nutrients.get(key) is None:
                missing_counts[key] += 1
        
        metadata = record.get("metadata", {})
        confidence_sum += metadata.get("confidence", 0.0)
        source_counts += len(metadata.get("sources", []))
    
    avg_confidence = confidence_sum / total
    avg_sources = source_counts / total
    
    report = [
        f"\n🔍 QA SUMMARY - {batch_name}",
        f"\n📊 Total Records: {total}",
        f"\n📈 Average Confidence: {avg_confidence:.2f}",
        f"\n📚 Average Sources per Dish: {avg_sources:.1f}",
        "\n🧪 Missingness per Nutrient (count, %):",
    ]
    
    for key in TRACKED_NUTRIENTS:
        count = missing_counts[key]
        pct = (count / total) * 100
        report.append(f"  - {key}: {count} ({pct:.1f}%)")
    
    return "\n".join(report)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data" / "processed"
    
    # File paths
    batch1_path = data_dir / "nigerian_llm_batch1.jsonl"
    batch2_path = data_dir / "nigerian_llm_batch2.jsonl"
    unified_path = data_dir / "nigerian_llm_complete.jsonl"
    backup_path = data_dir / "nigerian_llm_complete_backup.jsonl"
    qa_path = data_dir / "nigerian_llm_unified_qa.txt"
    
    print("🔄 Starting batch merge process...\n")
    
    # Backup existing unified file if it exists
    if unified_path.exists():
        print(f"📦 Backing up existing unified file to: {backup_path}")
        import shutil
        shutil.copy(unified_path, backup_path)
    
    # Load batch 1 (current nigerian_llm_complete.jsonl)
    print(f"📥 Loading Batch 1 from: {unified_path}")
    batch1_records = load_jsonl(unified_path)
    print(f"   ✅ Loaded {len(batch1_records)} records from Batch 1")
    
    # Load batch 2
    print(f"📥 Loading Batch 2 from: {batch2_path}")
    batch2_records = load_jsonl(batch2_path)
    print(f"   ✅ Loaded {len(batch2_records)} records from Batch 2")
    
    # Merge records
    all_records = batch1_records + batch2_records
    print(f"\n🔗 Merged {len(all_records)} total records")
    
    # Check for duplicate IDs
    ids = [r.get("id") for r in all_records]
    unique_ids = set(ids)
    if len(ids) != len(unique_ids):
        print(f"⚠️  Warning: Found {len(ids) - len(unique_ids)} duplicate IDs")
        # Remove duplicates (keep first occurrence)
        seen = set()
        deduplicated = []
        for record in all_records:
            record_id = record.get("id")
            if record_id not in seen:
                seen.add(record_id)
                deduplicated.append(record)
        all_records = deduplicated
        print(f"   ✅ Deduplicated to {len(all_records)} unique records")
    
    # Save unified file
    print(f"\n💾 Saving unified file to: {unified_path}")
    save_jsonl(all_records, unified_path)
    print(f"   ✅ Saved {len(all_records)} records")
    
    # Generate QA report
    qa_report = generate_qa_report(all_records, "UNIFIED")
    print(qa_report)
    
    # Save QA report
    with qa_path.open("w", encoding="utf-8") as f:
        f.write(qa_report)
    print(f"\n📄 QA report saved to: {qa_path}")
    
    # Summary by batch
    print("\n" + "="*60)
    print("📊 BATCH BREAKDOWN")
    print("="*60)
    print(f"Batch 1 (Original): {len(batch1_records)} records")
    print(f"Batch 2 (New):      {len(batch2_records)} records")
    print(f"Unified Total:      {len(all_records)} records")
    print("="*60)
    
    print("\n✅ Merge complete! 🎉")


if __name__ == "__main__":
    main()

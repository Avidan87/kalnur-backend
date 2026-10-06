"""
Run Batch 2 Extraction and Merge with Batch 1
Complete workflow: Extract batch 2 → Merge with batch 1 → Unified output
"""

import subprocess
import sys
from pathlib import Path


def run_script(script_path: Path) -> int:
    """Run a Python script and return exit code."""
    print(f"\n{'='*60}")
    print(f"🚀 Running: {script_path.name}")
    print(f"{'='*60}\n")
    
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=script_path.parent.parent,
    )
    
    return result.returncode


def main() -> None:
    root = Path(__file__).resolve().parent
    
    # Step 1: Run batch 2 extraction
    batch2_script = root / "nigerian_llm_ingest_batch2.py"
    print("📦 STEP 1: Extract Batch 2 Nigerian Foods")
    exit_code = run_script(batch2_script)
    
    if exit_code != 0:
        print(f"\n❌ Batch 2 extraction failed with exit code {exit_code}")
        print("⚠️  Skipping merge step. Please fix errors and try again.")
        sys.exit(1)
    
    print("\n✅ Batch 2 extraction complete!")
    
    # Step 2: Merge batches
    merge_script = root / "merge_batches.py"
    print("\n📦 STEP 2: Merge Batch 1 + Batch 2")
    exit_code = run_script(merge_script)
    
    if exit_code != 0:
        print(f"\n❌ Merge failed with exit code {exit_code}")
        sys.exit(1)
    
    print("\n✅ All steps complete! 🎉")
    print("\n📁 Output files:")
    print("   - nigerian_llm_batch2.jsonl (Batch 2 only)")
    print("   - nigerian_llm_complete.jsonl (Unified: Batch 1 + 2)")
    print("   - nigerian_llm_unified_qa.txt (QA report)")


if __name__ == "__main__":
    main()

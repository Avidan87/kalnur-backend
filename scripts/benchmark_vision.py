"""
Vision Benchmark CLI Runner

Runs side-by-side benchmark of Claude Sonnet 4.6 (AWS Bedrock) vs OpenAI GPT-4o
across the entire Kalnur food logging pipeline with Supabase database matching.

Usage:
  python scripts/benchmark_vision.py --image path/to/food.jpg --meal-type lunch
"""

import argparse
import asyncio
import json
import os
import sys

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kai.services.vision_benchmark_service import VisionBenchmarkService


def format_table_row(col1: str, col2: str, col3: str, width: int = 26) -> str:
    return f"{col1.ljust(width)} | {col2.ljust(width)} | {col3.ljust(width)}"


async def main():
    parser = argparse.ArgumentParser(description="Run Vision Benchmark (Claude Sonnet 4.6 vs GPT-4o)")
    parser.add_argument("--image", required=True, help="Path to local image file (JPEG, PNG, WebP)")
    parser.add_argument("--meal-type", default="lunch", help="Meal type (breakfast, lunch, dinner, snack)")
    parser.add_argument("--note", default=None, help="Optional user context note")
    parser.add_argument("--save-json", default=None, help="Path to save full JSON output")

    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"❌ Error: Image file not found: {args.image}")
        sys.exit(1)

    with open(args.image, "rb") as f:
        image_bytes = f.read()

    print("\n" + "=" * 84)
    print("🍲 KALNUR VISION BENCHMARK: CLAUDE SONNET 4.6 (BEDROCK) vs OPENAI GPT-4o")
    print("=" * 84)
    print(f"📁 Image: {args.image} ({len(image_bytes) / 1024:.1f} KB)")
    print(f"🍽️  Meal Type: {args.meal_type}")
    print("⚡ Executing concurrent multi-model analysis & Supabase food matching...")

    benchmark_svc = VisionBenchmarkService()
    report = await benchmark_svc.execute_benchmark(
        image_bytes=image_bytes,
        meal_type=args.meal_type,
        user_description=args.note,
    )

    claude = report.get("claude_sonnet_46", {})
    gpt4o = report.get("openai_gpt4o", {})
    analysis = report.get("benchmark_analysis", {})

    print("\n" + "-" * 84)
    print(format_table_row("METRIC", "CLAUDE SONNET 4.6 (BEDROCK)", "OPENAI GPT-4o"))
    print("-" * 84)

    # Latency & Cost
    c_lat = f"{claude.get('latency_ms', 0)} ms" if not claude.get("error") else "FAILED"
    g_lat = f"{gpt4o.get('latency_ms', 0)} ms" if not gpt4o.get("error") else "FAILED"
    print(format_table_row("Inference Latency", c_lat, g_lat))

    c_cost = f"${claude.get('estimated_cost_usd', 0.0):.6f}" if not claude.get("error") else "N/A"
    g_cost = f"${gpt4o.get('estimated_cost_usd', 0.0):.6f}" if not gpt4o.get("error") else "N/A"
    print(format_table_row("API Cost per Scan", c_cost, g_cost))

    c_tokens = f"In: {claude.get('input_tokens',0)} | Out: {claude.get('output_tokens',0)}" if not claude.get("error") else "N/A"
    g_tokens = f"In: {gpt4o.get('input_tokens',0)} | Out: {gpt4o.get('output_tokens',0)}" if not gpt4o.get("error") else "N/A"
    print(format_table_row("Token Usage", c_tokens, g_tokens))

    # Vessel
    c_vessel = f"{claude.get('vessel', {}).get('type', 'N/A')} (~{claude.get('vessel', {}).get('estimated_depth_cm', 0)}cm)" if not claude.get("error") else "N/A"
    g_vessel = f"{gpt4o.get('vessel', {}).get('type', 'N/A')} (~{gpt4o.get('vessel', {}).get('estimated_depth_cm', 0)}cm)" if not gpt4o.get("error") else "N/A"
    print(format_table_row("Vessel Type & Depth", c_vessel, g_vessel))

    # Nutrition Totals
    c_nut = claude.get("nutrients", {})
    g_nut = gpt4o.get("nutrients", {})
    print(format_table_row("Total Calories", f"{c_nut.get('calories', 0):.1f} kcal", f"{g_nut.get('calories', 0):.1f} kcal"))
    print(format_table_row("Protein", f"{c_nut.get('protein', 0):.1f} g", f"{g_nut.get('protein', 0):.1f} g"))
    print(format_table_row("Carbohydrates", f"{c_nut.get('carbohydrates', 0):.1f} g", f"{g_nut.get('carbohydrates', 0):.1f} g"))
    print(format_table_row("Fat", f"{c_nut.get('fat', 0):.1f} g", f"{g_nut.get('fat', 0):.1f} g"))
    print(format_table_row("Iron", f"{c_nut.get('iron', 0):.1f} mg", f"{g_nut.get('iron', 0):.1f} mg"))
    print("-" * 84)

    # Food item breakdown
    print("\n🍲 DETECTED DISHES & OCCLUSION REASONING:")
    print("\n--- CLAUDE SONNET 4.6 (BEDROCK) ---")
    if claude.get("error"):
        print(f"❌ Error: {claude.get('error')}")
    else:
        for f in claude.get("foods", []):
            sub_tag = f"[{f['occlusion_state'].upper()}]" if f.get("is_submerged") else "[SURFACE]"
            sb_tag = "✓ Supabase Matched" if f.get("supabase_matched") else "⚠️ Unmatched"
            print(f"  • {f['canonical_name']} ({f['portion_grams']:.0f}g) {sub_tag} — {sb_tag}")
            if f.get("submerged_reasoning"):
                print(f"    Reasoning: {f['submerged_reasoning']}")

    print("\n--- OPENAI GPT-4o ---")
    if gpt4o.get("error"):
        print(f"❌ Error: {gpt4o.get('error')}")
    else:
        for f in gpt4o.get("foods", []):
            sub_tag = f"[{f['occlusion_state'].upper()}]" if f.get("is_submerged") else "[SURFACE]"
            sb_tag = "✓ Supabase Matched" if f.get("supabase_matched") else "⚠️ Unmatched"
            print(f"  • {f['canonical_name']} ({f['portion_grams']:.0f}g) {sub_tag} — {sb_tag}")
            if f.get("submerged_reasoning"):
                print(f"    Reasoning: {f['submerged_reasoning']}")

    # Analysis
    if analysis.get("valid_comparison"):
        nut_imp = analysis.get("nutritional_impact", {})
        print("\n" + "=" * 84)
        print("📊 BENCHMARK ANALYSIS & OCCLUSION DELTA:")
        print(f"  • Caloric Delta: {nut_imp.get('calorie_delta_kcal', 0):+.1f} kcal ({nut_imp.get('calorie_discrepancy_pct', 0):+.1f}%)")
        print(f"  • Protein Delta: {nut_imp.get('protein_delta_g', 0):+.1f} g")
        print(f"  • Submerged Items Detected: Claude={len(analysis.get('occlusion_inference', {}).get('claude_submerged_detected', []))} vs GPT-4o={len(analysis.get('occlusion_inference', {}).get('gpt4o_submerged_detected', []))}")
        print(f"  • Latency Comparison: {analysis.get('latency', {}).get('faster_model')} was faster by {abs(analysis.get('latency', {}).get('delta_ms', 0))} ms")
        print(f"  • Cost Comparison: {analysis.get('cost', {}).get('cheaper_model')} was cheaper by ${abs(analysis.get('cost', {}).get('delta_usd', 0)):.6f}")
        print("=" * 84)

    if args.save_json:
        with open(args.save_json, "w") as out_f:
            json.dump(report, out_f, indent=2)
        print(f"\n💾 Full JSON report saved to: {args.save_json}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Vision Engine Benchmark Service with Modal SAM 2 & Depth Anything V2

Orchestrates a comprehensive, fair, side-by-side benchmark between:
1. Anthropic Claude Sonnet 4.6 on AWS Bedrock
2. OpenAI GPT-4o

Executes the ENTIRE Kalnur 3D food logging pipeline for both models:
- Identical spatial vision prompt with occlusion, submerged items, vessel depth & oil analysis
- Modal GPU SAM 2 (Segment Anything) pixel mask segmentation
- Modal GPU Depth Anything V2 3D volumetric depth portion calculation
- Supabase live database matching (134+ enriched Nigerian foods + pgvector)
- Complete 16-nutrient breakdown calculation
- Submerged food occlusion analysis and caloric discrepancy calculation
- Complete end-to-end latency breakdown: Vision (ms) + SAM 2 (ms) + Depth (ms)
"""

import asyncio
import base64
import io
import time
import logging
import os
import numpy as np
from PIL import Image
import httpx
from typing import Dict, Any, List, Optional, Tuple

from kai.agents.bedrock_vision import BedrockClaudeVisionClient
from kai.agents.openai_vision import OpenAIVisionClient
from kai.database.db_setup import get_supabase
from kai.rag.chromadb_setup import NigerianFoodVectorDB
from kai.mcp_servers.depth_estimation_client import get_depth_client

logger = logging.getLogger(__name__)

NUTRIENT_FIELDS = [
    "calories", "protein", "carbohydrates", "fat", "fiber",
    "iron", "calcium", "zinc", "potassium", "sodium",
    "magnesium", "vitamin_a", "vitamin_c", "vitamin_d",
    "vitamin_b12", "folate"
]


class VisionBenchmarkService:
    """End-to-End Benchmark Service for Vision Models with Modal GPU SAM 2 & Depth Anything."""

    def __init__(self):
        self.bedrock_client = BedrockClaudeVisionClient()
        self.openai_client = OpenAIVisionClient()
        self.supabase = get_supabase()
        self.vector_db = NigerianFoodVectorDB()
        self.sam_url = os.getenv("SAM_SEGMENTATION_URL")
        self.depth_client = get_depth_client()

    async def _run_sam_and_depth(
        self,
        image_base64: str,
        image_bytes: bytes,
        detected_foods_raw: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], int, int, Dict[str, Any]]:
        """
        Runs Modal GPU SAM 2 segmentation + Depth Anything V2 3D volume estimation.
        Returns:
            (updated_foods_list, sam_latency_ms, depth_latency_ms, debug_meta)
        """
        sam_latency_ms = 0
        depth_latency_ms = 0
        debug_meta = {
            "sam_used": False,
            "depth_used": False,
            "segmented_items": 0,
            "depth_items": 0,
        }

        if not detected_foods_raw:
            return detected_foods_raw, 0, 0, debug_meta

        food_names = [f.get("name") for f in detected_foods_raw if f.get("name")]

        # Step 1: Run SAM 2 on Modal GPU if 2+ foods
        food_masks = {}
        if len(food_names) >= 2 and self.sam_url:
            sam_start = time.perf_counter()
            try:
                logger.info("🔬 Calling Modal SAM 2 GPU for %d foods: %s", len(food_names), food_names)
                async with httpx.AsyncClient(timeout=35.0) as client:
                    resp = await client.post(
                        f"{self.sam_url.rstrip('/')}/segment",
                        json={"image_base64": image_base64, "food_names": food_names},
                    )
                    resp.raise_for_status()
                    sam_data = resp.json()
                    raw_masks = sam_data.get("masks", {})
                    food_masks = {name: np.array(mask, dtype=bool) for name, mask in raw_masks.items()}
                sam_latency_ms = int((time.perf_counter() - sam_start) * 1000)
                debug_meta["sam_used"] = True
                debug_meta["segmented_items"] = len(food_masks)
                logger.info("✅ SAM 2 finished in %d ms (masks: %d)", sam_latency_ms, len(food_masks))
            except Exception as e:
                sam_latency_ms = int((time.perf_counter() - sam_start) * 1000)
                logger.warning("⚠️ Modal SAM 2 call failed (%d ms): %s", sam_latency_ms, e)

        # Step 2: Build Bounding Boxes for Depth Anything V2
        img = Image.open(io.BytesIO(image_bytes))
        img_width, img_height = img.size

        bboxes = []
        depth_food_types = []
        food_idx_to_batch = {}

        if food_masks:
            for idx, item in enumerate(detected_foods_raw):
                name = item.get("name")
                mask = food_masks.get(name)
                if mask is not None and np.any(mask):
                    ys, xs = np.where(mask)
                    x1, x2 = int(np.min(xs)), int(np.max(xs))
                    y1, y2 = int(np.min(ys)), int(np.max(ys))
                    food_idx_to_batch[idx] = len(bboxes)
                    bboxes.append((x1, y1, x2, y2))
                    depth_food_types.append(name)
        else:
            # Fallback grid bboxes if SAM 2 skipped or failed
            for idx, item in enumerate(detected_foods_raw):
                food_idx_to_batch[idx] = len(bboxes)
                bboxes.append((0, 0, img_width, img_height))
                depth_food_types.append(item.get("name", "food"))

        # Step 3: Run Depth Anything V2 on Modal GPU
        depth_results = []
        if bboxes:
            depth_start = time.perf_counter()
            try:
                logger.info("📏 Calling Modal Depth Anything V2 GPU for %d items...", len(bboxes))
                depth_results = await self.depth_client.estimate_portions_batch(
                    image_base64=image_base64,
                    bboxes=bboxes,
                    food_types=depth_food_types,
                    reference_object="plate",
                )
                depth_latency_ms = int((time.perf_counter() - depth_start) * 1000)
                debug_meta["depth_used"] = True
                debug_meta["depth_items"] = len(depth_results)
                logger.info("✅ Depth Anything finished in %d ms (items: %d)", depth_latency_ms, len(depth_results))
            except Exception as e:
                depth_latency_ms = int((time.perf_counter() - depth_start) * 1000)
                logger.warning("⚠️ Modal Depth Anything call failed (%d ms): %s", depth_latency_ms, e)

        # Step 4: Merge 3D Depth portion estimates into foods
        updated_foods = []
        for idx, item in enumerate(detected_foods_raw):
            item_copy = dict(item)
            b_idx = food_idx_to_batch.get(idx)
            if b_idx is not None and b_idx < len(depth_results):
                depth_item = depth_results[b_idx]
                d_grams = depth_item.get("portion_grams")
                if d_grams and d_grams > 0:
                    item_copy["estimated_grams"] = float(d_grams)
                    item_copy["depth_volume_ml"] = depth_item.get("volume_ml")
                    item_copy["depth_confidence"] = depth_item.get("confidence")
            updated_foods.append(item_copy)

        return updated_foods, sam_latency_ms, depth_latency_ms, debug_meta

    async def _match_food_in_supabase(self, food_name: str) -> Tuple[Optional[Dict[str, Any]], float]:
        """Match detected food name against Supabase nigerian_foods table (text + alias + pgvector)."""
        from kai.food_registry import get_canonical_food_name
        cleaned_name = food_name.strip()
        alias_name = get_canonical_food_name(cleaned_name)

        # Step 1: Direct SQL text match on raw name and alias name
        names_to_try = [cleaned_name]
        if alias_name and alias_name.lower() != cleaned_name.lower():
            names_to_try.append(alias_name)

        for query_name in names_to_try:
            try:
                # 1a. Exact or case-insensitive match
                res = self.supabase.table("nigerian_foods").select("*").ilike("name", query_name).limit(1).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0], 1.0

                # 1b. Substring / contains match (e.g. "Bitterleaf Soup" -> "Bitterleaf Soup (Ofe Onugbu)")
                res = self.supabase.table("nigerian_foods").select("*").ilike("name", f"%{query_name}%").limit(1).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0], 0.95
            except Exception as e:
                logger.warning("Supabase text match query error for '%s': %s", query_name, e)

        # Step 2: Supabase pgvector semantic search
        try:
            matches = await asyncio.to_thread(self.vector_db.search, cleaned_name, 1)
            if matches and len(matches) > 0:
                top_match = matches[0]
                similarity = top_match.get("similarity", 0.85)
                food_id = top_match.get("id")
                row_res = self.supabase.table("nigerian_foods").select("*").eq("food_id", food_id).limit(1).execute()
                if row_res.data:
                    return row_res.data[0], float(similarity)
                return top_match.get("metadata", {}), float(similarity)
        except Exception as e:
            logger.warning("Supabase pgvector search error for '%s': %s", cleaned_name, e)

        return None, 0.0

    def _calculate_scaled_nutrients(self, supabase_food: Dict[str, Any], portion_grams: float) -> Dict[str, float]:
        """Scale 16 nutrients per 100g to the detected portion grams."""
        factor = portion_grams / 100.0
        scaled = {}
        for nut in NUTRIENT_FIELDS:
            raw_val = supabase_food.get(nut) or 0.0
            try:
                scaled[nut] = round(float(raw_val) * factor, 2)
            except (ValueError, TypeError):
                scaled[nut] = 0.0
        return scaled

    async def _process_detected_foods_through_pipeline(
        self,
        detected_foods_raw: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """Runs Supabase food matching and 16-nutrient computation."""
        processed_foods = []
        meal_totals = {nut: 0.0 for nut in NUTRIENT_FIELDS}

        for item in detected_foods_raw:
            raw_name = item.get("name", "Unknown Food")
            estimated_g = item.get("estimated_grams") or 150.0

            # Match in Supabase
            sb_food, match_conf = await self._match_food_in_supabase(raw_name)

            if sb_food:
                canonical_name = sb_food.get("name", raw_name)
                min_g = sb_food.get("min_reasonable_g", 30) or 30
                max_g = sb_food.get("max_reasonable_g", 500) or 500

                # Bounded portion estimate
                final_portion_g = float(max(min_g, min(estimated_g, max_g)))
                scaled_nutrients = self._calculate_scaled_nutrients(sb_food, final_portion_g)
                is_matched = True
            else:
                canonical_name = raw_name
                final_portion_g = float(estimated_g)
                scaled_nutrients = {nut: 0.0 for nut in NUTRIENT_FIELDS}
                is_matched = False

            for nut in NUTRIENT_FIELDS:
                meal_totals[nut] = round(meal_totals[nut] + scaled_nutrients[nut], 2)

            processed_foods.append({
                "raw_name": raw_name,
                "canonical_name": canonical_name,
                "supabase_matched": is_matched,
                "matching_confidence": round(match_conf, 2),
                "confidence": item.get("confidence", 0.8),
                "estimated_portion_desc": item.get("estimated_portion", ""),
                "portion_grams": final_portion_g,
                "depth_volume_ml": item.get("depth_volume_ml"),
                "occlusion_state": item.get("occlusion_state", "surface"),
                "is_submerged": item.get("occlusion_state") in ("partially_submerged", "fully_submerged"),
                "submerged_reasoning": item.get("submerged_reasoning", ""),
                "visible_ingredients": item.get("visible_ingredients", []),
                "oil_amount_estimate": item.get("oil_amount_estimate", "none"),
                "oil_sheen_visible": item.get("oil_sheen_visible", False),
                "nutrients": scaled_nutrients,
            })

        return processed_foods, meal_totals

    async def execute_benchmark(
        self,
        image_bytes: bytes,
        meal_type: Optional[str] = "lunch",
        user_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute concurrent side-by-side benchmark across both models
        with full Modal SAM 2 + Depth Anything V2 + Supabase pipeline.
        """
        pipeline_start = time.time()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Step 1: Run both vision models concurrently for fair comparison
        claude_task = self.bedrock_client.analyze_image_bytes(
            image_bytes=image_bytes,
            meal_type=meal_type,
            user_description=user_description,
        )
        gpt4o_task = self.openai_client.analyze_image_bytes(
            image_bytes=image_bytes,
            meal_type=meal_type,
            user_description=user_description,
        )

        results = await asyncio.gather(claude_task, gpt4o_task, return_exceptions=True)
        claude_raw_res = results[0]
        gpt4o_raw_res = results[1]

        # Step 2: Process Claude Sonnet 4.6 output through SAM 2 + Depth + Supabase
        if isinstance(claude_raw_res, Exception):
            claude_data = {
                "model_name": "Claude Sonnet 4.6 (AWS Bedrock)",
                "error": str(claude_raw_res),
                "latency_breakdown": {"total_ms": 0},
                "estimated_cost_usd": 0.0,
                "foods": [],
                "nutrients": {},
            }
        else:
            claude_parsed = claude_raw_res.get("parsed_result", {})
            claude_foods_initial = claude_parsed.get("detected_foods", [])

            # Run SAM 2 + Depth Anything V2 on Claude's detections
            claude_updated_foods, c_sam_ms, c_depth_ms, c_debug = await self._run_sam_and_depth(
                image_base64=image_base64,
                image_bytes=image_bytes,
                detected_foods_raw=claude_foods_initial,
            )

            # Supabase nutrition pipeline
            sb_start = time.perf_counter()
            claude_foods, claude_nutrients = await self._process_detected_foods_through_pipeline(claude_updated_foods)
            c_sb_ms = int((time.perf_counter() - sb_start) * 1000)

            c_total_ms = claude_raw_res["latency_ms"] + c_sam_ms + c_depth_ms + c_sb_ms

            claude_data = {
                "model_name": claude_raw_res["model_name"],
                "model_id": claude_raw_res["model_id"],
                "provider": claude_raw_res["provider"],
                "latency_breakdown": {
                    "vision_inference_ms": claude_raw_res["latency_ms"],
                    "sam2_segmentation_ms": c_sam_ms,
                    "depth_estimation_ms": c_depth_ms,
                    "supabase_nutrition_ms": c_sb_ms,
                    "total_end_to_end_ms": c_total_ms,
                },
                "latency_ms": c_total_ms,
                "input_tokens": claude_raw_res["input_tokens"],
                "output_tokens": claude_raw_res["output_tokens"],
                "estimated_cost_usd": claude_raw_res["estimated_cost_usd"],
                "vessel": claude_parsed.get("vessel", {}),
                "meal_context": claude_parsed.get("meal_context", ""),
                "spatial_depth_reasoning": claude_parsed.get("spatial_depth_reasoning", ""),
                "modal_pipeline_status": c_debug,
                "foods": claude_foods,
                "submerged_foods_count": sum(1 for f in claude_foods if f["is_submerged"]),
                "nutrients": claude_nutrients,
            }

        # Step 3: Process OpenAI GPT-4o output through SAM 2 + Depth + Supabase
        if isinstance(gpt4o_raw_res, Exception):
            gpt4o_data = {
                "model_name": "OpenAI GPT-4o",
                "error": str(gpt4o_raw_res),
                "latency_breakdown": {"total_ms": 0},
                "estimated_cost_usd": 0.0,
                "foods": [],
                "nutrients": {},
            }
        else:
            gpt4o_parsed = gpt4o_raw_res.get("parsed_result", {})
            gpt4o_foods_initial = gpt4o_parsed.get("detected_foods", [])

            # Run SAM 2 + Depth Anything V2 on GPT-4o's detections
            gpt4o_updated_foods, g_sam_ms, g_depth_ms, g_debug = await self._run_sam_and_depth(
                image_base64=image_base64,
                image_bytes=image_bytes,
                detected_foods_raw=gpt4o_foods_initial,
            )

            # Supabase nutrition pipeline
            sb_start = time.perf_counter()
            gpt4o_foods, gpt4o_nutrients = await self._process_detected_foods_through_pipeline(gpt4o_updated_foods)
            g_sb_ms = int((time.perf_counter() - sb_start) * 1000)

            g_total_ms = gpt4o_raw_res["latency_ms"] + g_sam_ms + g_depth_ms + g_sb_ms

            gpt4o_data = {
                "model_name": gpt4o_raw_res["model_name"],
                "model_id": gpt4o_raw_res["model_id"],
                "provider": gpt4o_raw_res["provider"],
                "latency_breakdown": {
                    "vision_inference_ms": gpt4o_raw_res["latency_ms"],
                    "sam2_segmentation_ms": g_sam_ms,
                    "depth_estimation_ms": g_depth_ms,
                    "supabase_nutrition_ms": g_sb_ms,
                    "total_end_to_end_ms": g_total_ms,
                },
                "latency_ms": g_total_ms,
                "input_tokens": gpt4o_raw_res["input_tokens"],
                "output_tokens": gpt4o_raw_res["output_tokens"],
                "estimated_cost_usd": gpt4o_raw_res["estimated_cost_usd"],
                "vessel": gpt4o_parsed.get("vessel", {}),
                "meal_context": gpt4o_parsed.get("meal_context", ""),
                "spatial_depth_reasoning": gpt4o_parsed.get("spatial_depth_reasoning", ""),
                "modal_pipeline_status": g_debug,
                "foods": gpt4o_foods,
                "submerged_foods_count": sum(1 for f in gpt4o_foods if f["is_submerged"]),
                "nutrients": gpt4o_nutrients,
            }

        total_pipeline_ms = int((time.time() - pipeline_start) * 1000)

        # Step 4: Compute Comparison Analysis
        comparison_analysis = self._compute_comparison_analysis(claude_data, gpt4o_data)

        return {
            "status": "success",
            "meal_type": meal_type,
            "total_pipeline_time_ms": total_pipeline_ms,
            "claude_sonnet_46": claude_data,
            "openai_gpt4o": gpt4o_data,
            "benchmark_analysis": comparison_analysis,
        }

    def _compute_comparison_analysis(self, claude: Dict[str, Any], gpt4o: Dict[str, Any]) -> Dict[str, Any]:
        """Compute comparative deltas on occlusion, nutrition, latency breakdown, and cost."""
        if claude.get("error") or gpt4o.get("error"):
            return {
                "valid_comparison": False,
                "notes": "One or both models encountered an error during execution."
            }

        c_cal = claude.get("nutrients", {}).get("calories", 0.0)
        g_cal = gpt4o.get("nutrients", {}).get("calories", 0.0)
        cal_diff = round(c_cal - g_cal, 2)
        cal_pct_diff = round((cal_diff / g_cal * 100.0), 1) if g_cal > 0 else 0.0

        c_prot = claude.get("nutrients", {}).get("protein", 0.0)
        g_prot = gpt4o.get("nutrients", {}).get("protein", 0.0)
        prot_diff = round(c_prot - g_prot, 2)

        c_latency = claude.get("latency_ms", 0)
        g_latency = gpt4o.get("latency_ms", 0)
        latency_delta_ms = c_latency - g_latency

        c_cost = claude.get("estimated_cost_usd", 0.0)
        g_cost = gpt4o.get("estimated_cost_usd", 0.0)
        cost_delta_usd = round(c_cost - g_cost, 6)

        c_submerged_foods = [f["canonical_name"] for f in claude.get("foods", []) if f.get("is_submerged")]
        g_submerged_foods = [f["canonical_name"] for f in gpt4o.get("foods", []) if f.get("is_submerged")]

        return {
            "valid_comparison": True,
            "latency": {
                "claude_total_end_to_end_ms": c_latency,
                "gpt4o_total_end_to_end_ms": g_latency,
                "delta_ms": latency_delta_ms,
                "faster_model": "Claude Sonnet 4.6" if c_latency < g_latency else "OpenAI GPT-4o",
                "claude_breakdown": claude.get("latency_breakdown"),
                "gpt4o_breakdown": gpt4o.get("latency_breakdown"),
            },
            "cost": {
                "claude_usd": c_cost,
                "gpt4o_usd": g_cost,
                "delta_usd": cost_delta_usd,
                "cheaper_model": "Claude Sonnet 4.6" if c_cost < g_cost else "OpenAI GPT-4o",
            },
            "occlusion_inference": {
                "claude_submerged_detected": c_submerged_foods,
                "gpt4o_submerged_detected": g_submerged_foods,
                "submerged_item_count_delta": len(c_submerged_foods) - len(g_submerged_foods),
            },
            "nutritional_impact": {
                "claude_calories_kcal": c_cal,
                "gpt4o_calories_kcal": g_cal,
                "calorie_delta_kcal": cal_diff,
                "calorie_discrepancy_pct": cal_pct_diff,
                "claude_protein_g": c_prot,
                "gpt4o_protein_g": g_prot,
                "protein_delta_g": prot_diff,
                "summary": (
                    f"Claude detected {cal_diff:+.1f} kcal ({cal_pct_diff:+.1f}%) and "
                    f"{prot_diff:+.1f}g protein compared to GPT-4o."
                ),
            }
        }

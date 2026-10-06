"""
OpenAI GPT-4o Vision Client for Benchmark Comparison

Invokes OpenAI GPT-4o using the exact same standardized prompt as Claude Sonnet 4.6
for strict apples-to-apples performance, occlusion, depth, latency, and cost benchmarking.
"""

import os
import json
import time
import logging
import re
import base64
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv

from kai.agents.food_vision_prompt import build_standardized_food_vision_prompt

load_dotenv()
logger = logging.getLogger(__name__)

# GPT-4o Pricing (USD per token)
GPT4O_INPUT_COST_PER_TOKEN = 2.50 / 1_000_000    # $2.50 per 1M tokens
GPT4O_OUTPUT_COST_PER_TOKEN = 10.00 / 1_000_000  # $10.00 per 1M tokens


class OpenAIVisionClient:
    """Multimodal Vision Client for OpenAI GPT-4o using identical benchmark parameters."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        self.client = AsyncOpenAI(api_key=key)
        self.model = model or os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
        logger.info("✓ OpenAIVisionClient initialized (model: %s)", self.model)

    def _detect_mime_type(self, image_bytes: bytes) -> str:
        """Infer mime type from image bytes."""
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        elif image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:12]:
            return "image/webp"
        elif image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
            return "image/gif"
        return "image/jpeg"

    def _clean_json_output(self, raw_text: str) -> Dict[str, Any]:
        """Strip markdown code fences and parse JSON."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx : end_idx + 1]

        return json.loads(cleaned)

    async def analyze_image_bytes(
        self,
        image_bytes: bytes,
        meal_type: Optional[str] = "lunch",
        user_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invoke OpenAI GPT-4o with multimodal payload and standardized prompt.

        Returns:
            Dict containing:
              - model_name: str
              - model_id: str
              - latency_ms: int
              - input_tokens: int
              - output_tokens: int
              - estimated_cost_usd: float
              - parsed_result: Dict (detected foods, occlusion, vessel, depth)
              - raw_response_text: str
        """
        prompt = build_standardized_food_vision_prompt(meal_type=meal_type, user_description=user_description)
        mime_type = self._detect_mime_type(image_bytes)
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64_image}"

        start_time = time.time()
        logger.info("🚀 Invoking OpenAI model: %s...", self.model)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=3000,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        raw_text = response.choices[0].message.content or "{}"
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        cost_usd = (
            (input_tokens * GPT4O_INPUT_COST_PER_TOKEN) +
            (output_tokens * GPT4O_OUTPUT_COST_PER_TOKEN)
        )

        parsed_json = self._clean_json_output(raw_text)

        logger.info(
            "✅ OpenAI GPT-4o completed in %d ms | Tokens: in=%d, out=%d | Cost: $%.6f",
            latency_ms, input_tokens, output_tokens, cost_usd
        )

        return {
            "model_name": "OpenAI GPT-4o",
            "model_id": self.model,
            "provider": "OpenAI",
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(cost_usd, 6),
            "parsed_result": parsed_json,
            "raw_response_text": raw_text,
        }

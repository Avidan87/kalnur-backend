"""
Claude Sonnet 4.6 Vision Client for AWS Bedrock

Invokes Anthropic Claude Sonnet 4.6 via the AWS Bedrock Converse API with multimodal image payload.
Measures:
- Precise inference latency (ms)
- Input & Output tokens from Bedrock response usage
- Exact API execution cost ($)
- Occlusion, submerged layer, and depth reasoning
"""

import os
import json
import time
import logging
import re
from typing import Dict, Any, Optional, Tuple
import boto3
from botocore.config import Config
from dotenv import load_dotenv

from kai.agents.food_vision_prompt import build_standardized_food_vision_prompt

load_dotenv()
logger = logging.getLogger(__name__)

# Claude Sonnet 4.6 on AWS Bedrock Pricing (USD per token)
CLAUDE_SONNET_46_INPUT_COST_PER_TOKEN = 3.00 / 1_000_000    # $3.00 per 1M tokens
CLAUDE_SONNET_46_OUTPUT_COST_PER_TOKEN = 15.00 / 1_000_000  # $15.00 per 1M tokens

DEFAULT_BEDROCK_MODEL_ID = os.getenv("BEDROCK_CLAUDE_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
FALLBACK_BEDROCK_MODEL_IDS = [
    "anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
]


class BedrockClaudeVisionClient:
    """Multimodal Vision Client for Anthropic Claude Sonnet 4.6 on AWS Bedrock."""

    def __init__(
        self,
        region_name: Optional[str] = None,
        model_id: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ):
        self.region_name = (
            region_name
            or os.getenv("BEDROCK_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self.model_id = model_id or DEFAULT_BEDROCK_MODEL_ID
        
        # Configure retry & timeout
        boto_config = Config(
            region_name=self.region_name,
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=15,
            read_timeout=90,
        )

        client_kwargs = {
            "service_name": "bedrock-runtime",
            "region_name": self.region_name,
            "config": boto_config,
        }

        # Use credentials from env if provided
        key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        if key_id and secret_key:
            client_kwargs["aws_access_key_id"] = key_id
            client_kwargs["aws_secret_access_key"] = secret_key

        self.bedrock = boto3.client(**client_kwargs)
        logger.info("✓ BedrockClaudeVisionClient initialized (model: %s, region: %s)", self.model_id, self.region_name)

    def _detect_image_format(self, image_bytes: bytes) -> str:
        """Infer format from magic bytes (default: jpeg)."""
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        elif image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:12]:
            return "webp"
        elif image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
            return "gif"
        return "jpeg"

    def _clean_json_output(self, raw_text: str) -> Dict[str, Any]:
        """Strip code fence wrappers or stray text and parse JSON."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        
        # Try finding the first '{' and last '}'
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
        Invoke Claude Sonnet 4.6 on AWS Bedrock via Converse API.

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
        img_format = self._detect_image_format(image_bytes)

        message = {
            "role": "user",
            "content": [
                {
                    "text": prompt
                },
                {
                    "image": {
                        "format": img_format,
                        "source": {"bytes": image_bytes}
                    }
                }
            ]
        }

        # Try designated model, fall back to alternatives if access restriction occurs
        models_to_try = [self.model_id] + [m for m in FALLBACK_BEDROCK_MODEL_IDS if m != self.model_id]
        last_exception = None

        for target_model in models_to_try:
            start_time = time.time()
            try:
                logger.info("🚀 Invoking Bedrock model: %s in %s...", target_model, self.region_name)
                response = self.bedrock.converse(
                    modelId=target_model,
                    messages=[message],
                    inferenceConfig={
                        "temperature": 0.1,
                        "maxTokens": 1500,
                    }
                )
                latency_ms = int((time.time() - start_time) * 1000)

                # Extract content
                content_blocks = response.get("output", {}).get("message", {}).get("content", [])
                raw_text = "".join([b.get("text", "") for b in content_blocks if "text" in b])

                # Extract token usage
                usage = response.get("usage", {})
                input_tokens = usage.get("inputTokens", 0)
                output_tokens = usage.get("outputTokens", 0)
                cost_usd = (
                    (input_tokens * CLAUDE_SONNET_46_INPUT_COST_PER_TOKEN) +
                    (output_tokens * CLAUDE_SONNET_46_OUTPUT_COST_PER_TOKEN)
                )

                # Parse JSON
                parsed_json = self._clean_json_output(raw_text)

                logger.info(
                    "✅ Bedrock Claude Sonnet 4.6 completed in %d ms | Tokens: in=%d, out=%d | Cost: $%.6f",
                    latency_ms, input_tokens, output_tokens, cost_usd
                )

                return {
                    "model_name": "Claude Sonnet 4.6 (AWS Bedrock)",
                    "model_id": target_model,
                    "provider": "Anthropic / AWS Bedrock",
                    "latency_ms": latency_ms,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "estimated_cost_usd": round(cost_usd, 6),
                    "parsed_result": parsed_json,
                    "raw_response_text": raw_text,
                }

            except Exception as exc:
                last_exception = exc
                logger.warning("⚠️ Bedrock model %s failed: %s. Trying fallback...", target_model, exc)

        # If all model IDs failed, re-raise the last exception with helpful diagnostic message
        raise RuntimeError(
            f"Failed to invoke Bedrock Claude models ({models_to_try}) in region '{self.region_name}'. "
            f"Error details: {last_exception}"
        )

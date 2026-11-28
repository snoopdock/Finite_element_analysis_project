"""Provider-independent cost estimation for the AE-32C Cloudflare profile.

Kept separate from live_evaluation so provider-free C3 preparation can build
its deterministic estimator without importing provider adapters or credentials.
"""
from __future__ import annotations

import math
import os
from typing import Any


def _positive_env_float(name: str, default: str) -> float:
    raw = os.environ.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive finite number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return value


def build_live_cost_estimator(provider_name: str, model_name: str):
    """Build the conservative Cloudflare Qwen3.8 estimator.

    Prompt characters are converted at four characters/token and padded by
    25%; output reserves two maximum completions to cover one possible stream
    recovery. Cached-input discounts are deliberately not assumed.
    """
    if (str(provider_name).strip().lower() != "cloudflare"
            or str(model_name).strip() != "@cf/qwen/qwen3.8-27b"):
        return None
    input_rate = _positive_env_float("FEA_AE32C_CLOUDFLARE_INPUT_USD_PER_M", "0.45")
    output_rate = _positive_env_float("FEA_AE32C_CLOUDFLARE_OUTPUT_USD_PER_M", "3.20")

    def estimate(_provider: str, _model: str, prompt_chars: int, output_tokens: int) -> float:
        if (isinstance(prompt_chars, bool) or not isinstance(prompt_chars, int) or prompt_chars < 0
                or isinstance(output_tokens, bool) or not isinstance(output_tokens, int) or output_tokens < 0):
            raise ValueError("invalid_cost_estimator_input")
        estimated_input_tokens = math.ceil((prompt_chars / 4.0) * 1.25)
        estimated_output_tokens = output_tokens * 2
        raw_cost = (
            estimated_input_tokens * input_rate
            + estimated_output_tokens * output_rate
        ) / 1_000_000.0
        return raw_cost * 1.15

    estimate.pricing_metadata = {
        "provider": "cloudflare",
        "model": "@cf/qwen/qwen3.8-27b",
        "input_usd_per_million_tokens": input_rate,
        "output_usd_per_million_tokens": output_rate,
        "cached_input_discount_assumed": False,
        "prompt_token_estimate": "ceil(prompt_chars / 4 * 1.25)",
        "output_reservation_multiplier": 2,
        "uncertainty_margin": 0.15,
        "scope": "baseline_and_graph_assisted_provider_calls",
    }
    return estimate


#!/usr/bin/env python3
"""Runtime selection for the FEA pipeline's LLM provider."""

from __future__ import annotations

import os
from typing import Mapping, Optional, Tuple

from providers.cloudflare import CloudflareProvider
from providers.openai_compatible import DEFAULT_MODELS, OpenAICompatibleProvider

SUPPORTED_PROVIDERS = ("cloudflare", "nararouter", "openrouter")


def _bounded_env_int(
    environ: Mapping[str, str],
    name: str,
    current: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = str(environ.get(name, "")).strip()
    if not raw:
        return int(current)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def apply_runtime_overrides(
    config: dict,
    environ: Optional[Mapping[str, str]] = None,
) -> Tuple[str, str]:
    """Apply explicit provider/model selection and benchmark-only budgets."""
    env = os.environ if environ is None else environ
    provider_name = str(env.get("FEA_LLM_PROVIDER", "cloudflare")).strip().lower()
    if provider_name not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"FEA_LLM_PROVIDER must be one of {', '.join(SUPPORTED_PROVIDERS)}"
        )

    model_override = str(env.get("FEA_LLM_MODEL", "")).strip()
    if provider_name != "cloudflare" and not model_override:
        model_override = DEFAULT_MODELS[provider_name]
    if model_override:
        # Existing writer components select from cloudflare_models. Keep that
        # legacy key as the model-selection interface while the provider factory
        # chooses the transport independently.
        config["cloudflare_models"] = [model_override]

    budget = config.setdefault("budget", {})
    if not isinstance(budget, dict):
        raise ValueError("config.budget must be a mapping")

    if str(env.get("FEA_BENCHMARK_MODE", "")) == "1":
        current_calls = int(budget.get("max_llm_calls_per_run", 20))
        current_tokens = int(budget.get("max_tokens_per_call", 2500))
        budget["max_llm_calls_per_run"] = _bounded_env_int(
            env, "FEA_MAX_LLM_CALLS", current_calls, 1, 100
        )
        budget["max_tokens_per_call"] = _bounded_env_int(
            env, "FEA_MAX_TOKENS_PER_CALL", current_tokens, 256, 12000
        )
        # Keep the provider's independent logical-call gate aligned with the
        # budget observed by pipeline components.
        if isinstance(env, dict):
            env["FEA_MAX_LLM_CALLS"] = str(budget["max_llm_calls_per_run"])

    config["llm_provider"] = provider_name
    return provider_name, model_override


def build_provider(
    config: dict,
    budget_config: dict,
    provider_name: str,
    model_override: str = "",
    environ: Optional[Mapping[str, str]] = None,
):
    """Build a provider, requiring only the selected provider's secret."""
    env = os.environ if environ is None else environ
    max_tokens = int(budget_config.get("max_tokens_per_call", 2500))
    max_calls = int(budget_config.get("max_llm_calls_per_run", 20))

    if provider_name == "cloudflare":
        account_id = str(env.get("CLOUDFLARE_ACCOUNT_ID", "")).strip()
        api_token = str(env.get("CLOUDFLARE_API_TOKEN", "")).strip()
        if not account_id:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not set for the selected provider.")
        if not api_token:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is not set for the selected provider.")
        models = [model_override] if model_override else config.get(
            "cloudflare_models", ["@cf/meta/llama-3.1-8b-instruct-fast"]
        )
        return CloudflareProvider(
            account_id,
            api_token,
            models,
            max_tokens,
            max_logical_calls=max_calls,
        )

    if provider_name == "nararouter":
        api_key = str(env.get("NARAROUTER_API_KEY", "")).strip()
    elif provider_name == "openrouter":
        api_key = str(env.get("OPENROUTER_TOKEN", "")).strip()
    else:
        raise ValueError(f"Unsupported provider: {provider_name!r}")

    if not api_key:
        secret_name = "NARAROUTER_API_KEY" if provider_name == "nararouter" else "OPENROUTER_TOKEN"
        raise RuntimeError(f"{secret_name} is not set for the selected provider.")

    model = model_override or DEFAULT_MODELS[provider_name]
    return OpenAICompatibleProvider(
        provider_name=provider_name,
        api_key=api_key,
        model=model,
        max_tokens_per_call=max_tokens,
        max_logical_calls=max_calls,
    )

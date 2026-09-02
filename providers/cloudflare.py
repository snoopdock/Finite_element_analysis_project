#!/usr/bin/env python3
"""Cloudflare Workers AI provider implementation."""

import os
import sys
import time

import requests

from processing.response_extractor import (
    LLMResponseExtractor,
    LLMResponseExtractionError,
)

CF_BASE = "https://api.cloudflare.com/client/v4"
DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"


class CloudflareProvider:
    def __init__(
        self,
        account_id,
        api_token,
        models,
        max_tokens_per_call=2500,
        max_logical_calls=20,
    ):
        self.account_id = account_id
        self.api_token = api_token
        self.models = models if models else [DEFAULT_MODEL]
        self.model_index = 0
        self.call_counts = {model: 0 for model in self.models}
        self.logical_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.http_attempts = 0
        self.total_calls = 0
        self.max_tokens_per_call = max_tokens_per_call

        env_limit = os.environ.get("FEA_MAX_LLM_CALLS")
        if env_limit:
            try:
                max_logical_calls = int(env_limit)
            except ValueError:
                pass

        self.max_logical_calls = max_logical_calls
        self.extractor = LLMResponseExtractor(verbose=False)

    def get_next_model(self):
        if not self.models:
            return None
        model = self.models[self.model_index]
        self.model_index = (self.model_index + 1) % len(self.models)
        return model

    def budget_exhausted(self) -> bool:
        return (
            self.max_logical_calls is not None
            and self.logical_calls >= self.max_logical_calls
        )

    def chat(self, messages, temperature=0.2, max_tokens=None, model=None):
        """Send one logical LLM call; HTTP retries do not count as new calls."""
        if self.budget_exhausted():
            return None, "Local logical-call budget exhausted"

        self.logical_calls += 1
        self.total_calls = self.logical_calls

        if max_tokens is None:
            max_tokens = self.max_tokens_per_call

        if model is None:
            model = self.get_next_model()
        if not model:
            self.failed_calls += 1
            return None, "No models available"

        url = f"{CF_BASE}/accounts/{self.account_id}/ai/run/{model}"
        headers = {"Authorization": "Bearer " + self.api_token}
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        for attempt in range(3):
            self.http_attempts += 1
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=180,
                )

                if resp.status_code == 429:
                    wait = min(120, 30 * (2 ** attempt))
                    print(
                        f"  [Cloudflare] Rate limited, waiting {wait}s...",
                        file=sys.stderr,
                    )
                    if attempt < 2:
                        time.sleep(wait)
                        continue
                    self.failed_calls += 1
                    return None, "HTTP 429: rate limit after retries"

                if resp.status_code == 402:
                    self.failed_calls += 1
                    return None, "HTTP 402: Budget exhausted"

                if resp.status_code >= 400:
                    self.failed_calls += 1
                    return None, f"HTTP {resp.status_code}: {resp.text[:300]}"

                data = resp.json()

                try:
                    text = self.extractor.extract(
                        data,
                        provider="cloudflare",
                        model=model,
                        raise_on_failure=True,
                    )
                except LLMResponseExtractionError as exc:
                    self.failed_calls += 1
                    return None, f"Extraction failed: {exc.message}"

                self.call_counts[model] = self.call_counts.get(model, 0) + 1
                self.successful_calls += 1
                return text, None

            except requests.exceptions.RequestException as exc:
                if attempt == 2:
                    self.failed_calls += 1
                    return None, str(exc)
                time.sleep(10 * (attempt + 1))

            except ValueError as exc:
                self.failed_calls += 1
                return None, f"Invalid JSON response: {exc}"

        self.failed_calls += 1
        return None, "Max retries exceeded"

    def get_stats(self):
        return {
            "total_calls": self.logical_calls,
            "logical_calls": self.logical_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "http_attempts": self.http_attempts,
            "per_model": dict(self.call_counts),
            "max_logical_calls": self.max_logical_calls,
            "extraction_stats": self.extractor.get_stats(),
            "learned_paths": self.extractor.get_learned_paths(),
        }

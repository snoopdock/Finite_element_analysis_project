#!/usr/bin/env python3
"""Cloudflare Workers AI provider implementation."""

import sys
import time
import requests

from processing.response_extractor import LLMResponseExtractor, LLMResponseExtractionError

CF_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareProvider:
    def __init__(self, account_id, api_token, models, max_tokens_per_call=2500):
        self.account_id = account_id
        self.api_token = api_token
        self.models = models if models else ["@cf/meta/llama-3.1-8b-instruct"]
        self.model_index = 0
        self.call_counts = {m: 0 for m in self.models}
        self.total_calls = 0
        self.max_tokens_per_call = max_tokens_per_call
        self.extractor = LLMResponseExtractor(verbose=False)

    def get_next_model(self):
        if not self.models:
            return None
        model = self.models[self.model_index]
        self.model_index = (self.model_index + 1) % len(self.models)
        return model

    def chat(self, messages, temperature=0.2, max_tokens=None, model=None):
        """
        Send chat completion request.
        If model is specified, use that model directly.
        If model is None, use round-robin selection.
        """
        self.total_calls += 1  # Count attempt immediately

        if max_tokens is None:
            max_tokens = self.max_tokens_per_call

        # Use specified model or round-robin
        if model is None:
            model = self.get_next_model()
        if not model:
            return None, "No models available"

        url = f"{CF_BASE}/accounts/{self.account_id}/ai/run/{model}"
        headers = {"Authorization": "Bearer " + self.api_token}
        payload = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}

        for attempt in range(3):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=180)
                if resp.status_code == 429:
                    wait = min(120, 30 * (2 ** attempt))
                    print(f"  [Cloudflare] Rate limited, waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                if resp.status_code == 402:
                    return None, "HTTP 402: Budget exhausted"
                if resp.status_code >= 400:
                    return None, f"HTTP {resp.status_code}: {resp.text[:300]}"

                data = resp.json()
                self.call_counts[model] = self.call_counts.get(model, 0) + 1

                try:
                    text = self.extractor.extract(data, provider="cloudflare", model=model, raise_on_failure=True)
                    return text, None
                except LLMResponseExtractionError as e:
                    return None, f"Extraction failed: {e.message}"

            except requests.exceptions.RequestException as exc:
                if attempt == 2:
                    return None, str(exc)
                time.sleep(10 * (attempt + 1))

        return None, "Max retries exceeded"

    def get_stats(self):
        return {
            "total_calls": self.total_calls,
            "per_model": dict(self.call_counts),
            "extraction_stats": self.extractor.get_stats(),
            "learned_paths": self.extractor.get_learned_paths(),
        }

#!/usr/bin/env python3
"""Budget management."""

import sys


def check_budget(config):
    """Check and report budget constraints."""
    budget_config = config.get("budget", {})
    max_calls = budget_config.get("max_llm_calls_per_run", 6)
    max_tokens = budget_config.get("max_tokens_per_call", 2500)
    daily_limit = budget_config.get("daily_neuron_limit", 10000)
    estimated_cost = max_calls * 500

    print(f"  [Budget] Local limit: {max_calls} calls x {max_tokens} tokens/call", file=sys.stderr)
    print(f"  [Budget] Estimated cost: ~{estimated_cost} neurons", file=sys.stderr)
    print(f"  [Budget] Free tier: {daily_limit} neurons/day (resets 00:00 UTC)", file=sys.stderr)
    return budget_config

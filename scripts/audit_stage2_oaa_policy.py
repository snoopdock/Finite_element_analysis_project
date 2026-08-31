#!/usr/bin/env python3
"""Runtime audit for Stage 2 OAA policy configuration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.oaa_policy import OAAActionPolicy
from analysis.policy_oaa_loop import PolicyAwareOAALoop


class _Splitter:
    pass


class _Merger:
    pass


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        config = {
            "oaa": {
                "severity_weights": {"repetition": 0.42},
                "cost_weights": {"repetition": 0.25},
                "persistence_weight": 0.20,
                "severity_weight": 0.60,
                "cost_weight": 0.20,
            }
        }
        loop = PolicyAwareOAALoop(config, _Splitter(), _Merger())
        _assert(isinstance(loop.action_policy, OAAActionPolicy), "OAA policy was not initialized.")
        _assert(abs(loop.action_policy.severity_weights["repetition"] - 0.42) < 1e-12, "Top-level OAA severity weights were ignored.")
        _assert(abs(loop.action_policy.cost_weights["repetition"] - 0.25) < 1e-12, "Top-level OAA cost weights were ignored.")

        explicit = dict(config)
        explicit["writing"] = {
            "oaa_action_policy": {
                "severity_weights": {"repetition": 0.80},
            }
        }
        explicit_loop = PolicyAwareOAALoop(explicit, _Splitter(), _Merger())
        _assert(abs(explicit_loop.action_policy.severity_weights["repetition"] - 0.80) < 1e-12, "Explicit writing.oaa_action_policy did not take precedence.")

        print("Stage 2 OAA policy runtime audit")
        print("================================")
        print("PASS: top-level fallback and explicit-policy precedence passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 2 OAA AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

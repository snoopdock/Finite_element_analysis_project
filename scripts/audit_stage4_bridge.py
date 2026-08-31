#!/usr/bin/env python3
"""Read-only audit for Stage 4 context preservation through the graph bridge."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.knowledge_graph_builder import sync_legacy_knowledge_base


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        state = {
            "knowledge_base": {
                "rules": [{
                    "rule": "A formulation is conditionally stable.",
                    "source_ids": ["paper-a"],
                    "framework": "linear elasticity",
                    "assumptions": ["small strain"],
                    "conditions": ["quasi-static"],
                    "domain_of_validity": ["small deformation"],
                    "scope": "one-dimensional example",
                }],
            },
            "knowledge_graph": {
                "concepts": {},
                "propositions": {},
                "relationships": {},
                "concept_history": [],
            },
        }
        sync_legacy_knowledge_base(state)
        propositions = state["knowledge_graph"]["propositions"]
        _assert(len(propositions) == 1, "Expected one bridged proposition.")
        proposition = next(iter(propositions.values()))
        context = proposition.get("context", {})
        _assert(context.get("framework") == "linear elasticity", "Framework was lost in bridge.")
        _assert(context.get("assumptions") == ["small strain"], "Assumptions were lost in bridge.")
        _assert(context.get("conditions") == ["quasi-static"], "Conditions were lost in bridge.")
        _assert(context.get("scope") == "one-dimensional example", "Scope was lost in bridge.")
        _assert(proposition.get("source_ids") == ["paper-a"], "Provenance was lost in bridge.")

        print("Stage 4 graph-bridge runtime audit")
        print("===================================")
        print("PASS: legacy-to-proposition context and provenance preservation passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 4 BRIDGE AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

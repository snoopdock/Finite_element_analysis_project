#!/usr/bin/env python3
"""Read-only Stage 6D audit for proposition evolution history."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.graph_state import ensure_graph_state


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        proposition_id = "11111111-1111-4111-8111-111111111111"
        state = {
            "knowledge_base": {
                "concepts": [],
                "rules": [{
                    "rule": "A stable FEM formulation under small deformation.",
                    "source_ids": ["source-a"],
                    "framework": "linear formulation",
                    "assumptions": ["small deformation"],
                }],
                "equations": [],
                "procedures": [],
            },
            "knowledge_graph": {
                "concepts": {},
                "propositions": {
                    proposition_id: {
                        "proposition_id": proposition_id,
                        "statement": "Existing proposition",
                        "source_ids": ["source-a"],
                        "framework": "framework-a",
                    }
                },
                "relationships": {},
                "concept_history": [],
                "proposition_history": [],
            },
        }

        ensure_graph_state(state)
        history = state["knowledge_graph"]["proposition_history"]
        check(len(history) >= 2, "Expected history records for graph and bridged propositions.")

        before_ids = set(state["knowledge_graph"]["propositions"])
        before_history = list(history)
        ensure_graph_state(state)
        check(set(state["knowledge_graph"]["propositions"]) == before_ids, "Proposition IDs changed on repeated synchronization.")
        check(state["knowledge_graph"]["proposition_history"] == before_history, "Repeated synchronization changed proposition history.")

        proposition = state["knowledge_graph"]["propositions"][proposition_id]
        proposition["framework"] = "framework-b"
        ensure_graph_state(state)
        updated_history = state["knowledge_graph"]["proposition_history"]
        matching = [item for item in updated_history if item.get("proposition_id") == proposition_id]
        check(len(matching) >= 2, "Proposition update was not recorded.")
        check(len({item.get("fingerprint") for item in matching}) >= 2, "Proposition fingerprint did not change after context update.")
        check(state["knowledge_graph"]["propositions"][proposition_id]["proposition_id"] == proposition_id, "Proposition identity changed during history tracking.")

        print("Stage 6D proposition-history audit")
        print("====================================")
        print("PASS: discovery history, idempotence, identity preservation, and context evolution tracking passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 6D PROPOSITION HISTORY AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Combined read-only Stage 6 audit.

Run from the repository root:
    python scripts/audit_stage6.py

Uses only in-memory data and does not call external services.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.graph_state import ensure_graph_state
from core.knowledge_graph import normalize_uuid, validate_graph_references


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        concept_id = "11111111-1111-4111-8111-111111111111"
        proposition_id = "22222222-2222-4222-8222-222222222222"

        state = {
            "knowledge_base": {
                "concepts": [{
                    "name": "Galerkin method",
                    "source_ids": ["source-a"],
                }],
                "rules": [{
                    "rule": "Galerkin method is stable under condition X.",
                    "source_ids": ["source-a"],
                    "framework": "framework A",
                    "assumptions": ["condition X"],
                    "concept_names": ["Galerkin method"],
                }],
                "equations": [],
                "procedures": [],
            },
            "knowledge_graph": {
                "concepts": {
                    concept_id: {
                        "concept_id": concept_id,
                        "name": "Galerkin method",
                        "type": "method",
                    }
                },
                "propositions": {
                    proposition_id: {
                        "proposition_id": proposition_id,
                        "statement": "Existing proposition",
                        "source_ids": ["source-b"],
                        "framework": "framework B",
                    }
                },
                "relationships": {},
                "concept_history": [],
                "proposition_history": [],
            },
        }

        ensure_graph_state(state)
        graph = state["knowledge_graph"]

        check(graph["concepts"], "No concepts populated.")
        check(graph["propositions"], "No propositions populated.")
        check(not graph["relationships"], "Stage 6 population created relationships unexpectedly.")
        check(not validate_graph_references(graph), "Graph references are invalid.")

        for record in graph["concepts"].values():
            check(normalize_uuid(record.get("concept_id")) is not None, "Invalid concept UUID.")
        for record in graph["propositions"].values():
            check(normalize_uuid(record.get("proposition_id")) is not None, "Invalid proposition UUID.")
            check(isinstance(record.get("context"), dict), "Proposition context is not normalized.")

        bridged = [p for p in graph["propositions"].values() if p.get("source_ids") == ["source-a"]]
        check(len(bridged) == 1, "Legacy proposition was not bridged exactly once.")
        check(bridged[0].get("concept_ids"), "Explicit concept membership was not preserved.")
        check(bridged[0].get("candidate_concept_ids"), "Candidate concept links were not produced.")

        before_ids = set(graph["propositions"])
        before_history = list(graph["proposition_history"])
        ensure_graph_state(state)
        graph2 = state["knowledge_graph"]
        check(set(graph2["propositions"]) == before_ids, "Proposition identity changed on repeat synchronization.")
        check(graph2["proposition_history"] == before_history, "Proposition history changed on idempotent synchronization.")

        existing = graph2["propositions"][proposition_id]
        history_count_before = len(graph2["proposition_history"])
        existing["framework"] = "framework C"
        ensure_graph_state(state)
        check(len(state["knowledge_graph"]["proposition_history"]) == history_count_before + 1, "Proposition context evolution was not recorded.")

        print("Stage 6 combined audit")
        print("======================")
        print("PASS: legacy population, identity, provenance/context, candidate membership, idempotence, and proposition history passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 6 AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

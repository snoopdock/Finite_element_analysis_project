#!/usr/bin/env python3
"""Runtime audit for Stage 1 graph identity and provenance semantics.

Run from the repository root:
    python scripts/audit_stage1_identity.py

The audit uses an in-memory graph only and does not modify repository state.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.graph_repository import upsert_concept, upsert_proposition, upsert_relationship
from core.knowledge_graph import new_graph_id, validate_graph_references


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        graph = {
            "concepts": {},
            "propositions": {},
            "relationships": {},
            "concept_history": [],
        }

        concept_id = upsert_concept(
            graph,
            {
                "concept_id": new_graph_id(),
                "name": "Galerkin method",
                "type": "method",
                "source_ids": ["paper-a"],
            },
        )

        first_id = upsert_proposition(
            graph,
            {
                "proposition_id": new_graph_id(),
                "statement": "The method is stable under condition X.",
                "concept_ids": [concept_id],
                "source_ids": ["paper-a"],
                "framework": "framework-a",
                "status": "proposed",
            },
        )
        second_id = upsert_proposition(
            graph,
            {
                "proposition_id": new_graph_id(),
                "statement": "The method is stable under condition X.",
                "concept_ids": [concept_id],
                "source_ids": ["paper-b"],
                "framework": "framework-b",
                "status": "proposed",
            },
        )

        _assert(first_id != second_id, "Distinct provenance/framework propositions were collapsed.")

        relationship_id = upsert_relationship(
            graph,
            source_id=first_id,
            target_id=second_id,
            relation_type="appears_to_contradict",
            proposition_ids=[first_id, second_id],
            source_ids=["paper-a", "paper-b"],
            confidence=0.8,
            framework="framework-a; framework-b",
            assumptions=["condition X"],
            reason="The source reports appear inconsistent; context comparison is required.",
        )
        _assert(relationship_id is not None, "Valid proposition relationship was rejected.")
        _assert(not validate_graph_references(graph), "Identity audit produced reference violations.")

        print("Stage 1 identity runtime audit")
        print("==============================")
        print(f"concepts: {len(graph['concepts'])}")
        print(f"propositions: {len(graph['propositions'])}")
        print(f"relationships: {len(graph['relationships'])}")
        print("PASS: identity separation, provenance separation, and reference validation passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 1 IDENTITY AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

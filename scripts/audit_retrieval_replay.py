#!/usr/bin/env python3
"""Audit read-only replay of persisted retrieval acquisition events."""

from __future__ import annotations

from copy import deepcopy

from analysis.retrieval_replay import replay_retrieval_event


def main() -> int:
    event = {
        "event_id": "retrieval-replay-001",
        "cycle": 14,
        "retrieved_at": "2026-09-03T00:00:00+00:00",
        "query_scope": ["weak form Galerkin FEM"],
        "report": {
            "status": "partial_failure",
            "query_count": 1,
            "providers": {
                "arxiv": {
                    "status": "success",
                    "attempts": 1,
                    "queries": ["weak form Galerkin FEM"],
                    "returned_records": 3,
                },
                "semantic_scholar": {
                    "status": "rate_limited",
                    "attempts": 1,
                    "queries": ["weak form Galerkin FEM"],
                    "returned_records": 0,
                },
            },
            "returned_records": 3,
            "selected_records": 2,
        },
        "acquisition_assessment": {
            "status": "partial_provider_availability",
            "operational_status": "partial_failure",
            "available_provider_count": 1,
            "unavailable_provider_count": 1,
            "returned_records": 3,
            "selected_records": 2,
        },
        "schema_version": 1,
    }

    original = deepcopy(event)
    replay = replay_retrieval_event(event)

    assert replay["event_id"] == event["event_id"]
    assert replay["cycle"] == event["cycle"]
    assert replay["retrieved_at"] == event["retrieved_at"]
    assert replay["query_scope"] == event["query_scope"]
    assert replay["operational_status"] == "partial_failure"
    assert replay["returned_records"] == 3
    assert replay["selected_records"] == 2
    assert replay["schema_version"] == 1

    assert replay["provider_operations"]["arxiv"]["status"] == "success"
    assert replay["provider_operations"]["semantic_scholar"]["status"] == "rate_limited"
    assert replay["acquisition_assessment"] == event["acquisition_assessment"]

    # Replay must not mutate the persisted event.
    assert event == original

    # Replay outputs are defensive copies.
    replay["query_scope"].append("tamper")
    assert event["query_scope"] == ["weak form Galerkin FEM"]

    # Replay is structural only: the module exposes no network operation.
    forbidden = {
        "propositions",
        "epistemic_state",
        "evidence_relations",
        "ranking",
        "convergence",
        "writing_decisions",
        "literature_coverage_status",
    }
    assert not forbidden.intersection(replay)

    print("R6 retrieval replay audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

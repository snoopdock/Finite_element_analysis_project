#!/usr/bin/env python3
"""Audit retrieval event construction without calling external providers."""

from __future__ import annotations

from analysis.retrieval_event import create_retrieval_event


def main() -> int:
    report = {
        "status": "partial_failure",
        "query_count": 2,
        "providers": {
            "arxiv": {
                "status": "success",
                "queries": [
                    "weak form Galerkin FEM",
                    "finite element stability",
                ],
            },
            "semantic_scholar": {
                "status": "rate_limited",
                "queries": [
                    "weak form Galerkin FEM",
                ],
            },
        },
        "returned_records": 3,
        "selected_records": 2,
    }

    event = create_retrieval_event(
        cycle=14,
        queries=None,
        report=report,
    )

    assert event["event_id"].startswith("retrieval-")
    assert event["cycle"] == 14
    assert event["schema_version"] == 1
    assert event["query_scope"] == [
        "weak form Galerkin FEM",
        "finite element stability",
    ]
    assert event["report"] == report
    assert event["acquisition_assessment"]["status"] == "partial_provider_availability"

    # Event snapshots must not share mutable report data with the caller.
    report["providers"]["arxiv"]["status"] = "tampered"
    assert event["report"]["providers"]["arxiv"]["status"] == "success"

    # A later event gets a distinct identity even when its scope is identical.
    later = create_retrieval_event(
        cycle=15,
        queries=None,
        report=event["report"],
    )
    assert later["event_id"] != event["event_id"]
    assert later["cycle"] == 15

    # Construction carries operational/acquisition metadata only.
    forbidden = {
        "propositions",
        "epistemic_state",
        "evidence_relations",
        "ranking",
        "convergence",
        "writing_decisions",
        "literature_coverage_status",
    }
    assert not forbidden.intersection(event)

    print("R6 retrieval event construction audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

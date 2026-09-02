#!/usr/bin/env python3
"""Audit the R7A read-only retrieval attention context layer."""

from __future__ import annotations

from copy import deepcopy

from analysis.retrieval_attention_context import build_retrieval_attention_context


def _event(event_id, cycle, status, queries, provider="semantic_scholar"):
    return {
        "event_id": event_id,
        "cycle": cycle,
        "retrieved_at": f"2026-09-03T00:{cycle:02d}:00+00:00",
        "query_scope": list(queries),
        "report": {
            "status": status,
            "query_count": len(queries),
            "providers": {
                provider: {
                    "status": status,
                    "attempts": 1,
                    "queries": list(queries),
                    "returned_records": 1 if status == "success" else 0,
                }
            },
            "returned_records": 1 if status == "success" else 0,
            "selected_records": 1 if status == "success" else 0,
        },
        "acquisition_assessment": {
            "status": (
                "not_defined_yet"
                if status == "success"
                else "partial_provider_availability"
            ),
            "operational_status": status,
        },
        "schema_version": 1,
    }


def main() -> int:
    query_a = "weak form Galerkin FEM"
    query_b = "finite element stability"

    event_10 = _event("retrieval-10", 10, "rate_limited", [query_a])
    event_11 = _event("retrieval-11", 11, "rate_limited", [query_a])
    event_12 = _event("retrieval-12", 12, "success", [query_a])
    event_13 = _event("retrieval-13", 13, "success", [query_b])

    history = {"events": [event_13, event_10, event_12, event_11]}
    original = deepcopy(history)

    context = build_retrieval_attention_context(history)

    assert context["schema_version"] == 1
    assert context["event_count"] == 4

    contexts = context["query_provider_contexts"]
    assert len(contexts) == 2

    by_query = {
        item["query_scope"]: item
        for item in contexts
    }

    query_a_context = by_query[query_a]
    assert query_a_context["provider"] == "semantic_scholar"
    assert query_a_context["supporting_event_ids"] == [
        "retrieval-10",
        "retrieval-11",
        "retrieval-12",
    ]
    assert [
        item["provider_status"]
        for item in query_a_context["observations"]
    ] == [
        "rate_limited",
        "rate_limited",
        "success",
    ]
    assert query_a_context["latest_observation"]["provider_status"] == "success"

    # R7A reports the latest observation but does not interpret it as resolved,
    # open, closed, or requiring an action.
    forbidden_keys = {
        "attention_reason",
        "attention_status",
        "lifecycle_status",
        "recommended_acquisition_action",
        "candidate_action",
        "policy_version",
        "confidence",
        "truth_status",
        "epistemic_status",
        "evidence_strength",
        "ranking_score",
        "convergence_status",
        "writer_decision",
    }
    serialized = str(context)
    for key in forbidden_keys:
        assert key not in context
        assert key not in serialized

    # Query normalization is case-insensitive and whitespace-tolerant.
    normalized_event = _event(
        "retrieval-14",
        14,
        "success",
        ["  Weak Form Galerkin FEM  ", "WEAK FORM GALERKIN FEM"],
    )
    normalized = build_retrieval_attention_context({"events": [normalized_event]})
    assert len(normalized["query_provider_contexts"]) == 1
    assert normalized["query_provider_contexts"][0]["query_scope"] == query_a

    # Missing provider-level queries must not be falsely attributed to an
    # event-level query scope.
    unscoped_event = deepcopy(event_10)
    unscoped_event["event_id"] = "retrieval-unscoped"
    del unscoped_event["report"]["providers"]["semantic_scholar"]["queries"]
    unscoped = build_retrieval_attention_context({"events": [unscoped_event]})
    assert not unscoped["query_provider_contexts"]
    assert len(unscoped["unscoped_provider_operations"]) == 1

    # R7A must be read-only and outputs must be defensive copies.
    assert history == original
    context["query_provider_contexts"][0]["observations"].clear()
    rebuilt = build_retrieval_attention_context(history)
    assert len(rebuilt["query_provider_contexts"][0]["observations"]) == 3

    print("R7A retrieval attention context audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

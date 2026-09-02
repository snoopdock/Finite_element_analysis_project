#!/usr/bin/env python3
"""Offline audit of the R7B retrieval-attention policy evaluator."""

from __future__ import annotations

from copy import deepcopy

from analysis.retrieval_attention_policy import evaluate_retrieval_attention


POLICY = {
    "policy_version": "r7b-test-v1",
    "history_window_events": 3,
    "repeated_non_success_threshold": 2,
    "repeated_empty_result_threshold": 2,
}


def _observation(event_id, cycle, status, records, assessment="not_defined_yet"):
    return {
        "event_id": event_id,
        "cycle": cycle,
        "retrieved_at": f"2026-09-03T00:{cycle:02d}:00+00:00",
        "provider_status": status,
        "attempts": 1,
        "returned_records": records,
        "acquisition_assessment": {
            "status": assessment,
            "operational_status": status,
        },
    }


def _context(query, provider, observations):
    return {
        "query_scope": query,
        "provider": provider,
        "observations": deepcopy(observations),
        "supporting_event_ids": [item["event_id"] for item in observations],
        "latest_observation": deepcopy(observations[-1]),
    }


def main() -> int:
    repeated_failure = _context(
        "weak form Galerkin FEM",
        "semantic_scholar",
        [
            _observation("e1", 1, "invalid_response", 0),
            _observation("e2", 2, "client_error", 0),
        ],
    )
    stable_success = _context(
        "finite element stability",
        "semantic_scholar",
        [
            _observation("e3", 3, "success", 4),
        ],
    )
    successful_empty = _context(
        "boundary element method",
        "semantic_scholar",
        [
            _observation("e4", 4, "success", 0),
        ],
    )
    repeated_empty = _context(
        "finite element conditioning",
        "semantic_scholar",
        [
            _observation("e5", 5, "success", 0),
            _observation("e6", 6, "success", 0),
        ],
    )
    recovered = _context(
        "weak form convergence",
        "semantic_scholar",
        [
            _observation("e7", 7, "rate_limited", 0, "partial_provider_availability"),
            _observation("e8", 8, "rate_limited", 0, "partial_provider_availability"),
            _observation("e9", 9, "success", 2),
        ],
    )
    partial = _context(
        "mesh stability",
        "synthetic_provider",
        [
            _observation("e10", 10, "partial_failure", 1, "partial_provider_availability"),
        ],
    )

    contexts = [
        repeated_failure,
        stable_success,
        successful_empty,
        repeated_empty,
        recovered,
        partial,
    ]
    context = {
        "schema_version": 1,
        "event_count": 10,
        "query_provider_contexts": contexts,
        "unscoped_provider_operations": [
            {"event_id": "e11", "provider": "semantic_scholar"}
        ],
        "unscoped_events": [{"event_id": "e12"}],
    }
    original_context = deepcopy(context)

    result = evaluate_retrieval_attention(context, POLICY)
    assert result["schema_version"] == 1
    assert result["policy_version"] == POLICY["policy_version"]

    by_query = {item["query_scope"]: item for item in result["attention_items"]}

    assert by_query["weak form Galerkin FEM"]["observed_condition"] == (
        "repeated_query_provider_non_success"
    )
    assert by_query["weak form Galerkin FEM"]["supporting_event_ids"] == [
        "e1",
        "e2",
    ]

    assert by_query["boundary element method"]["observed_condition"] == (
        "query_returned_empty_result"
    )
    assert by_query["finite element conditioning"]["observed_condition"] == (
        "repeated_query_provider_empty_result"
    )
    assert "finite element stability" not in by_query
    assert "weak form convergence" not in by_query
    assert by_query["mesh stability"]["observed_condition"] == "provider_partially_available"

    allowed_actions = {
        "retry_provider",
        "retry_query",
        "reformulate_query",
        "expand_query_scope",
        "use_alternate_provider",
        "defer_until_provider_recovery",
    }
    for item in result["attention_items"]:
        assert item["lifecycle_status"] == "open"
        assert item["policy_version"] == POLICY["policy_version"]
        assert item["recommended_acquisition_action"] in allowed_actions
        assert item["supporting_event_ids"]

    forbidden = {
        "confidence",
        "truth_status",
        "epistemic_status",
        "support_strength",
        "scientific_relevance",
        "scientific_importance",
        "evidence_strength",
        "ranking_score",
        "convergence_status",
        "writer_decision",
        "proposition",
    }
    serialized = str(result)
    for key in forbidden:
        assert key not in serialized

    # Deterministic replay: identical inputs yield identical output.
    assert evaluate_retrieval_attention(context, POLICY) == result

    # Reordering independent query/provider contexts must not change output order.
    reordered = deepcopy(context)
    reordered["query_provider_contexts"] = list(reversed(reordered["query_provider_contexts"]))
    assert evaluate_retrieval_attention(reordered, POLICY) == result

    # Input context is read-only and outputs are defensive.
    assert context == original_context
    result["attention_items"][0]["supporting_event_ids"].clear()
    rebuilt = evaluate_retrieval_attention(context, POLICY)
    assert rebuilt["attention_items"]
    assert rebuilt["attention_items"][0]["supporting_event_ids"]

    # Unscoped provider operations/events must not become query-specific attention.
    assert all(
        item["query_scope"] not in {"", None}
        for item in result["attention_items"]
    )

    # Threshold change is explicit policy behavior.
    stricter = dict(POLICY)
    stricter["repeated_non_success_threshold"] = 3
    stricter_result = evaluate_retrieval_attention(context, stricter)
    stricter_by_query = {
        item["query_scope"]: item for item in stricter_result["attention_items"]
    }
    assert "weak form Galerkin FEM" not in stricter_by_query

    # Policy version is provenance; changing it affects new interpretations only.
    versioned = dict(POLICY)
    versioned["policy_version"] = "r7b-test-v2"
    versioned_result = evaluate_retrieval_attention(context, versioned)
    assert versioned_result["attention_items"]
    assert all(
        item["policy_version"] == "r7b-test-v2"
        for item in versioned_result["attention_items"]
    )

    print("R7B retrieval attention policy audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline audit of R7C.5 retrieval-attention pipeline composition."""

from __future__ import annotations

from copy import deepcopy

from analysis.retrieval_attention_pipeline import generate_and_persist_retrieval_attention
from core.retrieval_attention_persistence import get_retrieval_attention_history


POLICY = {
    "policy_version": "r7c5-test-v1",
    "history_window_events": 3,
    "repeated_non_success_threshold": 2,
    "repeated_empty_result_threshold": 2,
}


def _event(event_id: str, cycle: int, status: str, records: int) -> dict:
    return {
        "event_id": event_id,
        "cycle": cycle,
        "retrieved_at": f"2026-09-03T00:{cycle:02d}:00Z",
        "query_scope": ["weak form Galerkin FEM"],
        "report": {
            "status": "success",
            "providers": {
                "semantic_scholar": {
                    "status": status,
                    "attempts": 1,
                    "returned_records": records,
                    "queries": ["weak form Galerkin FEM"],
                }
            },
            "returned_records": records,
            "selected_records": records,
        },
        "acquisition_assessment": {
            "status": "not_defined_yet",
            "operational_status": status,
        },
    }


def main() -> int:
    state = {
        "cycle": 2,
        "retrieval_history": {
            "events": [
                _event("r1", 1, "invalid_response", 0),
                _event("r2", 2, "client_error", 0),
            ]
        },
        "propositions": [
            {"id": "p1", "text": "existing proposition"}
        ],
        "evidence_relations": [
            {"source_id": "s1", "relation": "supports", "target": "p1"}
        ],
        "epistemic_state": {
            "p1": {"status": "undetermined"}
        },
    }
    original_state = deepcopy(state)
    original_retrieval_history = deepcopy(state["retrieval_history"])
    original_scientific = {
        "propositions": deepcopy(state["propositions"]),
        "evidence_relations": deepcopy(state["evidence_relations"]),
        "epistemic_state": deepcopy(state["epistemic_state"]),
    }

    first = generate_and_persist_retrieval_attention(state, POLICY)

    assert first["evaluation"]["attention_items"]
    assert first["persisted_count"] == 1
    assert first["duplicate_count"] == 0
    assert len(get_retrieval_attention_history(state)) == 1

    proposal = get_retrieval_attention_history(state)[0]
    assert proposal["observed_condition"] == "repeated_query_provider_non_success"
    assert proposal["supporting_event_ids"] == ["r1", "r2"]
    assert proposal["lifecycle_status"] == "open"
    assert proposal["policy_version"] == POLICY["policy_version"]
    assert proposal["recommended_acquisition_action"] == "use_alternate_provider"
    assert proposal["generated_at"]

    # R7C persistence is not allowed to alter retrieval acquisition history.
    assert state["retrieval_history"] == original_retrieval_history

    # Scientific state is outside the adapter boundary.
    for key, value in original_scientific.items():
        assert state[key] == value

    # Re-running against unchanged history/policy regenerates the same proposal
    # identity, but R7C prevents duplicate storage.
    before_second = deepcopy(get_retrieval_attention_history(state))
    second = generate_and_persist_retrieval_attention(state, POLICY)
    after_second = get_retrieval_attention_history(state)
    assert second["evaluation"] == first["evaluation"]
    assert second["persisted_count"] == 0
    assert second["duplicate_count"] == 1
    assert after_second == before_second

    # No-attention case performs no append.
    no_attention_state = {
        "retrieval_history": {
            "events": [
                _event("r3", 3, "success", 4),
            ]
        },
        "propositions": [],
        "evidence_relations": [],
        "epistemic_state": {},
    }
    no_attention_original = deepcopy(no_attention_state)
    empty_result = generate_and_persist_retrieval_attention(
        no_attention_state,
        POLICY,
    )
    assert empty_result["evaluation"]["attention_items"] == []
    assert empty_result["persisted_count"] == 0
    assert empty_result["duplicate_count"] == 0
    assert no_attention_state == no_attention_original

    # Adapter output must be defensive with respect to its stored objects.
    result_copy = first["evaluation"]
    result_copy["attention_items"][0]["supporting_event_ids"].clear()
    rebuilt = generate_and_persist_retrieval_attention(state, POLICY)
    assert rebuilt["evaluation"]["attention_items"][0]["supporting_event_ids"] == [
        "r1",
        "r2",
    ]

    print("R7C.5 retrieval attention pipeline integration audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

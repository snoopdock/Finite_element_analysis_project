#!/usr/bin/env python3
"""Offline audit of the R7C.7 live runtime connector."""

from __future__ import annotations

from copy import deepcopy

import analysis.retrieval_attention_runtime as runtime
from core.retrieval_attention_persistence import get_retrieval_attention_history


POLICY = {
    "policy_version": "r7c7-test-v1",
    "history_window_events": 3,
    "repeated_non_success_threshold": 2,
    "repeated_empty_result_threshold": 2,
}


def _event(event_id, cycle, query, provider, status, records):
    return {
        "event_id": event_id,
        "cycle": cycle,
        "retrieved_at": f"2026-09-03T01:{cycle:02d}:00Z",
        "query_scope": [query],
        "report": {
            "status": "success",
            "query_count": 1,
            "providers": {
                provider: {
                    "status": status,
                    "queries": [query],
                    "attempts": 1,
                    "returned_records": records,
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


def _scientific_state():
    return {
        "propositions": [{"id": "p1"}],
        "evidence_relations": [{"source": "s1", "target": "p1"}],
        "epistemic_state": {"p1": {"status": "unassessed"}},
        "evidence_strength": {"p1": None},
        "truth_status": {"p1": "unknown"},
        "ranking": {"p1": 0.0},
        "convergence": {"status": "not_evaluated"},
        "writing_content": {"section": "unchanged"},
        "knowledge_base": {"concepts": ["FEM"]},
        "sections": [{"title": "Introduction", "content": "unchanged"}],
    }


def main() -> int:
    query = "weak form Galerkin FEM"
    provider = "semantic_scholar"
    scientific = _scientific_state()

    state = {
        "retrieval_history": {
            "events": [
                _event("r1", 1, query, provider, "invalid_response", 0),
                _event("r2", 2, query, provider, "client_error", 0),
            ]
        },
        "retrieval_report": {"status": "success"},
        "retrieval_attention_history": {"proposals": []},
        **deepcopy(scientific),
    }
    config = {"retrieval_attention": dict(POLICY)}
    before_history = deepcopy(state["retrieval_history"])
    before_scientific = deepcopy(scientific)

    result = runtime.process_live_retrieval_attention(state, config)
    assert result["status"] == "success"
    assert result["policy_version"] == POLICY["policy_version"]
    assert result["persisted_count"] == 1
    assert result["duplicate_count"] == 0

    proposals = get_retrieval_attention_history(state)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["observed_condition"] == "repeated_query_provider_non_success"
    assert proposal["recommended_acquisition_action"] == "use_alternate_provider"
    assert proposal["lifecycle_status"] == "open"
    assert proposal["supporting_event_ids"] == ["r1", "r2"]
    assert proposal["generated_at"]

    assert state["retrieval_history"] == before_history
    for key, expected in before_scientific.items():
        assert state[key] == expected, f"Protected state changed: {key}"

    # Same history + same policy: deterministic evaluation, duplicate-safe persistence.
    first_proposal = deepcopy(proposal)
    repeated = runtime.process_live_retrieval_attention(state, config)
    assert repeated["evaluation"] == result["evaluation"]
    assert repeated["persisted_count"] == 0
    assert repeated["duplicate_count"] == 1
    assert get_retrieval_attention_history(state) == [first_proposal]

    # No-attention live cycle must not create or mutate attention history.
    quiet_state = {
        "retrieval_history": {
            "events": [
                _event("r3", 3, query, provider, "invalid_response", 0),
                _event("r4", 4, query, provider, "success", 3),
            ]
        },
        **deepcopy(scientific),
    }
    quiet_before = deepcopy(quiet_state)
    quiet = runtime.process_live_retrieval_attention(quiet_state, config)
    assert quiet["evaluation"]["attention_items"] == []
    assert quiet["persisted_count"] == 0
    assert quiet["duplicate_count"] == 0
    assert quiet_state == quiet_before

    # Missing policy is an operational configuration error.
    try:
        runtime.process_live_retrieval_attention(
            {"retrieval_history": {"events": []}},
            {},
        )
    except ValueError as exc:
        assert "retrieval_attention configuration is required" in str(exc)
    else:
        raise AssertionError("Missing policy configuration must fail explicitly.")

    # Failure containment: a downstream attention failure is observable and does not
    # itself mutate scientific state when the caller catches it.
    failure_state = {
        "retrieval_history": {
            "events": [_event("r5", 5, query, provider, "client_error", 0)]
        },
        **deepcopy(scientific),
    }
    failure_before = deepcopy(failure_state)

    original_generate = runtime.generate_and_persist_retrieval_attention
    try:
        def fail_generation(*_args, **_kwargs):
            raise RuntimeError("synthetic attention failure")

        runtime.generate_and_persist_retrieval_attention = fail_generation
        try:
            runtime.process_live_retrieval_attention(failure_state, config)
        except RuntimeError as exc:
            assert str(exc) == "synthetic attention failure"
        else:
            raise AssertionError("Synthetic attention failure must propagate to the caller.")
    finally:
        runtime.generate_and_persist_retrieval_attention = original_generate

    assert failure_state == failure_before

    # No execution authority exposed by the runtime result.
    serialized = str(result)
    for forbidden in {
        "executed_action",
        "action_result",
        "lifecycle_transition",
        "scientific_decision",
    }:
        assert forbidden not in serialized

    print("R7C.7 retrieval attention runtime connector audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

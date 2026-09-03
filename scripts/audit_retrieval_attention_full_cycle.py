#!/usr/bin/env python3
"""Offline audit of the complete R6-R7C retrieval-attention cycle."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from analysis.retrieval_attention_pipeline import (
    generate_and_persist_retrieval_attention,
)
from core.retrieval_attention_persistence import get_retrieval_attention_history
from core.retrieval_history_state import get_retrieval_history


POLICY = {
    "policy_version": "r7c6-test-v1",
    "history_window_events": 3,
    "repeated_non_success_threshold": 2,
    "repeated_empty_result_threshold": 2,
}


def _retrieval_event(
    event_id: str,
    cycle: int,
    query: str,
    provider: str,
    status: str,
    records: int,
) -> Dict[str, Any]:
    return {
        "event_id": event_id,
        "cycle": cycle,
        "retrieved_at": f"2026-09-03T00:{cycle:02d}:00Z",
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


def _scientific_state() -> Dict[str, Any]:
    return {
        "propositions": [{"id": "p1", "text": "placeholder proposition"}],
        "evidence_relations": [{"source": "s1", "target": "p1"}],
        "epistemic_state": {"p1": {"status": "unassessed"}},
        "evidence_strength": {"p1": None},
        "truth_status": {"p1": "unknown"},
        "ranking": {"p1": 0.0},
        "convergence": {"status": "not_evaluated"},
        "writing_content": {"section": "unchanged"},
        "knowledge_base": {"concepts": ["finite element method"]},
        "sections": [{"title": "Introduction", "content": "unchanged"}],
    }


def main() -> int:
    query = "weak form Galerkin FEM"
    provider = "semantic_scholar"

    state: Dict[str, Any] = {
        "retrieval_history": {
            "events": [
                _retrieval_event("r1", 1, query, provider, "invalid_response", 0),
                _retrieval_event("r2", 2, query, provider, "client_error", 0),
            ]
        },
        "retrieval_report": {"status": "success"},
        "retrieval_attention_history": {"proposals": []},
    }
    scientific = _scientific_state()
    state.update(deepcopy(scientific))
    original_state = deepcopy(state)
    original_retrieval_events = get_retrieval_history(state)

    result = generate_and_persist_retrieval_attention(state, POLICY)
    evaluation = result["evaluation"]
    proposals = evaluation["attention_items"]

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["query_scope"] == query
    assert proposal["provider"] == provider
    assert proposal["observed_condition"] == "repeated_query_provider_non_success"
    assert proposal["recommended_acquisition_action"] == "use_alternate_provider"
    assert proposal["lifecycle_status"] == "open"
    assert proposal["supporting_event_ids"] == ["r1", "r2"]
    assert result["persisted_count"] == 1
    assert result["duplicate_count"] == 0

    persisted = get_retrieval_attention_history(state)
    assert len(persisted) == 1
    assert persisted[0]["attention_id"] == proposal["attention_id"]
    assert persisted[0]["generated_at"]

    # Retrieval history and protected scientific state must remain unchanged.
    assert get_retrieval_history(state) == original_retrieval_events
    for key, expected in scientific.items():
        assert state[key] == expected, f"Protected state changed: {key}"

    # Repeat the same cycle input. Existing proposal must be recognized as a duplicate.
    first_persisted = deepcopy(persisted[0])
    second = generate_and_persist_retrieval_attention(state, POLICY)
    assert second["evaluation"] == evaluation
    assert second["persisted_count"] == 0
    assert second["duplicate_count"] == 1
    persisted_after_repeat = get_retrieval_attention_history(state)
    assert persisted_after_repeat == [first_persisted]

    # No-attention case: a current successful retrieval with records suppresses
    # historical repetition attention and must not create the history container.
    quiet_state: Dict[str, Any] = {
        "retrieval_history": {
            "events": [
                _retrieval_event("r3", 3, query, provider, "invalid_response", 0),
                _retrieval_event("r4", 4, query, provider, "success", 3),
            ]
        },
        **deepcopy(scientific),
    }
    quiet_before = deepcopy(quiet_state)
    quiet_result = generate_and_persist_retrieval_attention(quiet_state, POLICY)
    assert quiet_result["evaluation"]["attention_items"] == []
    assert quiet_result["persisted_count"] == 0
    assert quiet_result["duplicate_count"] == 0
    assert quiet_state == quiet_before

    # Deterministic proposal core: persistence timestamps are excluded from the
    # R7B result and therefore cannot alter evaluation identity.
    assert second["evaluation"] == evaluation
    deterministic_keys = {
        "attention_id",
        "policy_version",
        "query_scope",
        "provider",
        "attention_reason",
        "observed_condition",
        "lifecycle_status",
        "supporting_event_ids",
        "recommended_acquisition_action",
    }
    assert set(proposal) == deterministic_keys
    assert "generated_at" not in proposal

    # Replay the persisted proposal without re-running R7B.
    replayed = persisted_after_repeat[0]
    assert replayed["attention_id"] == proposal["attention_id"]
    assert replayed["policy_version"] == proposal["policy_version"]
    assert replayed["query_scope"] == proposal["query_scope"]
    assert replayed["provider"] == proposal["provider"]
    assert replayed["attention_reason"] == proposal["attention_reason"]
    assert replayed["observed_condition"] == proposal["observed_condition"]
    assert replayed["lifecycle_status"] == proposal["lifecycle_status"]
    assert replayed["supporting_event_ids"] == proposal["supporting_event_ids"]
    assert replayed["recommended_acquisition_action"] == proposal["recommended_acquisition_action"]

    # Defensive copies: mutating returned history must not mutate state.
    detached = get_retrieval_attention_history(state)
    detached[0]["supporting_event_ids"].clear()
    detached[0]["attention_reason"] = "mutated"
    assert get_retrieval_attention_history(state) == persisted_after_repeat

    # The integration layer exposes no action execution or lifecycle transition state.
    forbidden = {
        "executed_action",
        "action_result",
        "lifecycle_transition",
        "scientific_decision",
    }
    serialized = str(result)
    for key in forbidden:
        assert key not in serialized

    # Retrieval history reader remains unchanged after the full cycle.
    assert get_retrieval_history(state) == original_retrieval_events

    # The complete top-level state may differ only by the intended persisted
    # attention proposal history and its persistence metadata.
    expected_state = deepcopy(original_state)
    expected_state["retrieval_attention_history"]["proposals"] = persisted_after_repeat
    assert state == expected_state

    print("R7C.6 retrieval attention full-cycle integration audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

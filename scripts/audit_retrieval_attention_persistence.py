#!/usr/bin/env python3
"""Offline audit of the R7C attention-proposal persistence adapter."""

from __future__ import annotations

from copy import deepcopy

from core.retrieval_attention_persistence import (
    append_retrieval_attention_proposal,
    get_retrieval_attention_history,
    get_retrieval_attention_proposal,
    has_retrieval_attention_proposal,
    initialize_retrieval_attention_history,
)


PROPOSAL = {
    "attention_id": "attention-test-001",
    "policy_version": "r7b5-test-v1",
    "query_scope": "weak form Galerkin FEM",
    "provider": "semantic_scholar",
    "attention_reason": "Repeated non-success retrieval observations.",
    "observed_condition": "repeated_query_provider_non_success",
    "lifecycle_status": "open",
    "supporting_event_ids": ["e1", "e2"],
    "recommended_acquisition_action": "use_alternate_provider",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    state = {
        "retrieval_history": {"events": [{"event_id": "e1"}]},
        "propositions": {"p1": {"status": "unchanged"}},
        "evidence_relations": [{"source": "p1", "target": "p2"}],
    }
    original_state = deepcopy(state)

    initialize_retrieval_attention_history(state)
    check(
        state["retrieval_attention_history"] == {"proposals": []},
        "Attention history initialization is incorrect.",
    )
    check(state["retrieval_history"] == original_state["retrieval_history"], "Retrieval history was modified.")
    check(state["propositions"] == original_state["propositions"], "Scientific propositions were modified.")
    check(state["evidence_relations"] == original_state["evidence_relations"], "Evidence relations were modified.")

    result = append_retrieval_attention_proposal(
        state,
        PROPOSAL,
        generated_at="2026-09-03T00:00:00Z",
    )
    check(result is True, "First proposal must be appended.")

    stored = get_retrieval_attention_proposal(state, PROPOSAL["attention_id"])
    check(stored is not None, "Persisted proposal cannot be retrieved.")
    check(set(stored) == set(PROPOSAL) | {"generated_at"}, "Stored proposal fields are incorrect.")
    for field, value in PROPOSAL.items():
        check(stored[field] == value, f"Canonical proposal field changed: {field}")
    check(stored["generated_at"] == "2026-09-03T00:00:00Z", "Persistence timestamp was not stored correctly.")

    check(has_retrieval_attention_proposal(state, PROPOSAL["attention_id"]), "Persisted proposal was not detected by attention_id.")
    history = get_retrieval_attention_history(state)
    check(len(history) == 1, "Expected exactly one persisted proposal.")
    check(history[0]["generated_at"] == "2026-09-03T00:00:00Z", "History did not preserve persistence metadata.")

    # Duplicate persistence is idempotent and must not replace the original record.
    duplicate = deepcopy(PROPOSAL)
    duplicate["attention_reason"] = "This changed duplicate must be ignored."
    duplicate["generated_at"] = "2026-09-03T01:00:00Z"
    duplicate_result = append_retrieval_attention_proposal(
        state,
        duplicate,
        generated_at="2026-09-03T01:00:00Z",
    )
    check(duplicate_result is False, "Duplicate proposal must be a no-op.")
    preserved = get_retrieval_attention_proposal(state, PROPOSAL["attention_id"])
    check(preserved == stored, "Duplicate persistence rewrote the existing proposal.")

    # A distinct attention_id is a distinct historical proposal.
    second = deepcopy(PROPOSAL)
    second["attention_id"] = "attention-test-002"
    second["generated_at"] = "must-not-be-used-directly"
    second_result = append_retrieval_attention_proposal(
        state,
        second,
        generated_at="2026-09-03T02:00:00Z",
    )
    check(second_result is True, "Distinct attention_id must append a new proposal.")
    check(len(get_retrieval_attention_history(state)) == 2, "Expected two distinct persisted proposals.")

    # Readers and writers must use defensive copies.
    history_copy = get_retrieval_attention_history(state)
    history_copy[0]["supporting_event_ids"].clear()
    history_copy[0]["generated_at"] = "changed"
    reread = get_retrieval_attention_proposal(state, PROPOSAL["attention_id"])
    check(reread["supporting_event_ids"] == ["e1", "e2"], "Reader did not return a defensive copy.")
    check(reread["generated_at"] == "2026-09-03T00:00:00Z", "Reader exposed mutable persistence metadata.")

    proposal_copy = deepcopy(PROPOSAL)
    proposal_copy["supporting_event_ids"].clear()
    check(
        state["retrieval_attention_history"]["proposals"][0]["supporting_event_ids"] == ["e1", "e2"],
        "Writer storage was aliased to caller-owned proposal data.",
    )

    # R7C must not silently cross into scientific or retrieval state.
    check(state["retrieval_history"] == original_state["retrieval_history"], "Retrieval history changed during persistence.")
    check(state["propositions"] == original_state["propositions"], "Propositions changed during persistence.")
    check(state["evidence_relations"] == original_state["evidence_relations"], "Evidence relations changed during persistence.")

    # New proposals must enter only as open.
    invalid = deepcopy(PROPOSAL)
    invalid["attention_id"] = "attention-invalid"
    invalid["lifecycle_status"] = "closed"
    try:
        append_retrieval_attention_proposal(state, invalid, generated_at="2026-09-03T03:00:00Z")
    except ValueError:
        pass
    else:
        raise AssertionError("Non-open proposal must be rejected by R7C persistence.")

    # Required fields must be enforced.
    incomplete = deepcopy(PROPOSAL)
    incomplete["attention_id"] = "attention-incomplete"
    del incomplete["supporting_event_ids"]
    try:
        append_retrieval_attention_proposal(state, incomplete)
    except ValueError:
        pass
    else:
        raise AssertionError("Incomplete proposal must be rejected by R7C persistence.")

    print("R7C retrieval attention proposal persistence audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

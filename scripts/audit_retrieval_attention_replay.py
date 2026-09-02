#!/usr/bin/env python3
"""Audit R7C persisted attention-proposal replay and fidelity semantics."""

from __future__ import annotations

from copy import deepcopy

from analysis.retrieval_attention_replay import (
    DETERMINISTIC_FIELDS,
    replay_persisted_proposal,
    validate_persisted_proposal,
    validate_provenance,
)
from core.retrieval_attention_persistence import (
    append_retrieval_attention_proposal,
    get_retrieval_attention_proposal,
)


PROPOSAL = {
    "attention_id": "attention-test-001",
    "policy_version": "r7b5-test-v1",
    "query_scope": "weak form Galerkin FEM",
    "provider": "semantic_scholar",
    "attention_reason": "Query has repeated non-success retrieval observations.",
    "observed_condition": "repeated_query_provider_non_success",
    "lifecycle_status": "open",
    "supporting_event_ids": ["e1", "e2"],
    "recommended_acquisition_action": "use_alternate_provider",
}

HISTORY = [
    {"event_id": "e1", "cycle": 1, "provider_status": "invalid_response"},
    {"event_id": "e2", "cycle": 2, "provider_status": "client_error"},
]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    validate_persisted_proposal(PROPOSAL)
    validate_provenance(PROPOSAL, HISTORY)

    replayed = replay_persisted_proposal(PROPOSAL, HISTORY)
    check(set(replayed) == set(DETERMINISTIC_FIELDS), "Replay output shape is not canonical.")
    check(replayed == PROPOSAL, "Replay changed a deterministic proposal field.")

    # Repeated reconstruction must be byte-for-byte equivalent at the object level.
    assert replay_persisted_proposal(PROPOSAL, HISTORY) == replayed

    # Persistence → reload → replay fidelity.
    state = {"retrieval_attention_history": {"proposals": []}}
    stored = append_retrieval_attention_proposal(state, PROPOSAL, generated_at="2026-09-03T00:00:00+00:00")
    check(stored is True, "Initial proposal append should succeed.")
    loaded = get_retrieval_attention_proposal(state, PROPOSAL["attention_id"])
    check(loaded is not None, "Persisted proposal could not be reloaded.")
    check(loaded["generated_at"] == "2026-09-03T00:00:00+00:00", "Persistence timestamp was not retained.")
    reloaded_core = replay_persisted_proposal(loaded, HISTORY)
    check(reloaded_core == PROPOSAL, "Save/reload/replay changed proposal semantics.")

    # A different persistence timestamp must not change replayed meaning.
    state2 = {"retrieval_attention_history": {"proposals": []}}
    append_retrieval_attention_proposal(state2, PROPOSAL, generated_at="2026-09-04T00:00:00+00:00")
    loaded2 = get_retrieval_attention_proposal(state2, PROPOSAL["attention_id"])
    check(replay_persisted_proposal(loaded2, HISTORY) == PROPOSAL, "Persistence timestamp affected proposal replay.")

    # Duplicate IDs are idempotent and cannot overwrite the original proposal.
    changed = dict(PROPOSAL)
    changed["attention_reason"] = "attempted replacement"
    changed["policy_version"] = "r7b5-test-v2"
    second_append = append_retrieval_attention_proposal(
        state,
        changed,
        generated_at="2026-09-05T00:00:00+00:00",
    )
    check(second_append is False, "Duplicate attention_id must be idempotent.")
    preserved = get_retrieval_attention_proposal(state, PROPOSAL["attention_id"])
    check(preserved["attention_reason"] == PROPOSAL["attention_reason"], "Duplicate append overwrote proposal.")
    check(preserved["policy_version"] == PROPOSAL["policy_version"], "Duplicate append changed policy provenance.")
    check(preserved["generated_at"] == "2026-09-03T00:00:00+00:00", "Duplicate append changed persistence timestamp.")

    # Replay must not depend on generated_at.
    no_timestamp = deepcopy(PROPOSAL)
    check(replay_persisted_proposal(no_timestamp, HISTORY) == PROPOSAL, "Replay improperly requires generated_at.")

    # Missing provenance is an integrity error, not a silent omission.
    missing_history = [HISTORY[0]]
    try:
        validate_provenance(PROPOSAL, missing_history)
    except ValueError as exc:
        check("missing supporting retrieval events" in str(exc), "Missing provenance failed with the wrong error.")
    else:
        raise AssertionError("Missing supporting event was silently accepted.")

    # Defensive output: caller mutation must not alter persisted input.
    replayed["supporting_event_ids"].clear()
    check(PROPOSAL["supporting_event_ids"] == ["e1", "e2"], "Replay output is not defensive.")
    check(replay_persisted_proposal(PROPOSAL, HISTORY)["supporting_event_ids"] == ["e1", "e2"], "Replay became unstable after caller mutation.")

    # Scientific fields must not be introduced by persistence/replay.
    scientific_forbidden = {
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
    check(not (scientific_forbidden & set(loaded)), "Scientific fields leaked into persisted proposal.")
    check(not (scientific_forbidden & set(reloaded_core)), "Scientific fields leaked into replay output.")

    print("R7C retrieval attention replay fidelity audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

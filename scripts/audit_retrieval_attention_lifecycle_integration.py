#!/usr/bin/env python3
"""Offline R7D.6 composition audit for retrieval attention lifecycle handling."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

import yaml

from analysis.retrieval_attention_lifecycle import create_lifecycle_event
from analysis.retrieval_attention_lifecycle_replay import (
    LifecycleReplayError,
    replay_retrieval_attention_lifecycle,
)
from core.retrieval_attention_lifecycle_persistence import (
    LifecycleEventIntegrityError,
    append_lifecycle_event,
    get_lifecycle_history,
)
from core.retrieval_attention_persistence import get_retrieval_attention_history
from core.retrieval_history_state import get_retrieval_history


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "specs" / "contracts" / "retrieval_attention_lifecycle_integration_contract.yaml"


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
        "schema_version": 1,
    }


def _proposal() -> Dict[str, Any]:
    return {
        "attention_id": "attention-integration-1",
        "policy_version": "r7b-test-v1",
        "query_scope": "weak form Galerkin FEM",
        "provider": "semantic_scholar",
        "attention_reason": "Repeated non-success retrieval observations.",
        "observed_condition": "repeated_query_provider_non_success",
        "lifecycle_status": "open",
        "supporting_event_ids": ["r1", "r2"],
        "recommended_acquisition_action": "use_alternate_provider",
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


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    check(contract["version"] == 1, "R7D.6 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_lifecycle_integration_contract",
        "Unexpected R7D.6 contract name.",
    )

    query = "weak form Galerkin FEM"
    provider = "semantic_scholar"
    proposal = _proposal()
    scientific = _scientific_state()
    retrieval_events = [
        _retrieval_event("r1", 1, query, provider, "invalid_response", 0),
        _retrieval_event("r2", 2, query, provider, "client_error", 0),
    ]

    state: Dict[str, Any] = {
        "retrieval_history": {"events": deepcopy(retrieval_events)},
        "retrieval_report": {"status": "success", "returned_records": 0},
        "retrieval_attention_history": {"proposals": [deepcopy(proposal)]},
        "retrieval_attention_lifecycle_history": {"events": []},
        **deepcopy(scientific),
    }
    before = deepcopy(state)

    # Record lifecycle events only; lifecycle handling must not rewrite the proposal.
    open_event = create_lifecycle_event(
        proposal["attention_id"],
        None,
        "open",
        "Initial lifecycle creation.",
        "system",
        lifecycle_event_id="le1",
        created_at="2026-09-03T00:00:01Z",
    )
    addressed_event = create_lifecycle_event(
        proposal["attention_id"],
        "open",
        "addressed",
        "Bounded acquisition response recorded.",
        "system",
        lifecycle_event_id="le2",
        created_at="2026-09-03T00:00:02Z",
    )
    closed_event = create_lifecycle_event(
        proposal["attention_id"],
        "addressed",
        "closed",
        "No further process action is currently required.",
        "system",
        lifecycle_event_id="le3",
        created_at="2026-09-03T00:00:03Z",
    )

    for event in (open_event, addressed_event, closed_event):
        append_lifecycle_event(state, event)

    check(
        get_retrieval_attention_history(state)
        == before["retrieval_attention_history"]["proposals"],
        "Lifecycle handling changed the persisted proposal.",
    )
    check(
        get_retrieval_history(state) == retrieval_events,
        "Lifecycle handling changed retrieval history.",
    )
    for key, expected in scientific.items():
        check(state[key] == expected, f"Protected scientific state changed: {key}")

    lifecycle_history = get_lifecycle_history(state)
    check(len(lifecycle_history) == 3, "Expected three lifecycle events.")
    check(
        lifecycle_history == [open_event, addressed_event, closed_event],
        "Lifecycle history order/payload was not preserved.",
    )

    replay = replay_retrieval_attention_lifecycle(lifecycle_history)
    check(len(replay["trajectories"]) == 1, "Expected one lifecycle trajectory.")
    trajectory = replay["trajectories"][0]
    check(
        trajectory["attention_id"] == proposal["attention_id"],
        "Replay targeted the wrong attention proposal.",
    )
    expected_transitions = [
        {
            "lifecycle_event_id": "le1",
            "previous_status": None,
            "new_status": "open",
            "transition_reason": "Initial lifecycle creation.",
            "created_at": "2026-09-03T00:00:01Z",
            "actor": "system",
        },
        {
            "lifecycle_event_id": "le2",
            "previous_status": "open",
            "new_status": "addressed",
            "transition_reason": "Bounded acquisition response recorded.",
            "created_at": "2026-09-03T00:00:02Z",
            "actor": "system",
        },
        {
            "lifecycle_event_id": "le3",
            "previous_status": "addressed",
            "new_status": "closed",
            "transition_reason": "No further process action is currently required.",
            "created_at": "2026-09-03T00:00:03Z",
            "actor": "system",
        },
    ]
    check(
        trajectory["transitions"] == expected_transitions,
        "Replay transition sequence is incorrect.",
    )
    check(trajectory["final_status"] == "closed", "Replay final status is incorrect.")

    # Replay and history reads must be defensive.
    detached = get_lifecycle_history(state)
    detached[0]["transition_reason"] = "mutated"
    check(
        get_lifecycle_history(state) == lifecycle_history,
        "Lifecycle history is not defensively copied.",
    )
    check(
        state["retrieval_attention_history"]["proposals"] == [proposal],
        "Proposal changed after lifecycle-history copy mutation.",
    )

    # Conflicting reuse of an event ID must fail and preserve the original event.
    conflicting = deepcopy(addressed_event)
    conflicting["transition_reason"] = "conflicting reuse"
    try:
        append_lifecycle_event(state, conflicting)
    except LifecycleEventIntegrityError:
        pass
    else:
        raise AssertionError("Conflicting lifecycle-event ID was silently accepted.")
    check(
        get_lifecycle_history(state) == lifecycle_history,
        "Integrity failure changed lifecycle history.",
    )

    # Invalid replay sequence must fail rather than repair history.
    broken = deepcopy(lifecycle_history)
    broken[2]["previous_status"] = "open"
    try:
        replay_retrieval_attention_lifecycle(broken)
    except LifecycleReplayError:
        pass
    else:
        raise AssertionError("Broken lifecycle history was silently accepted.")

    # Lifecycle composition must not synthesize scientific or execution state.
    serialized = str({
        "proposal": proposal,
        "events": lifecycle_history,
        "replay": replay,
    })
    for forbidden in (
        "confidence",
        "truth_status",
        "evidence_strength",
        "epistemic_state",
        "ranking",
        "convergence",
        "writer_instruction",
        "executed_action",
    ):
        check(
            forbidden not in serialized,
            f"Forbidden field leaked into lifecycle composition output: {forbidden}",
        )

    # The only intended state mutation is lifecycle-history storage.
    expected = deepcopy(before)
    expected["retrieval_attention_lifecycle_history"] = {"events": lifecycle_history}
    check(
        state == expected,
        "R7D.6 composition modified state outside lifecycle history.",
    )

    execution_boundary = contract["execution_boundary"]
    check(
        "R7D.6 is an offline composition audit only." in execution_boundary["rules"],
        "R7D.6 must remain an offline composition audit.",
    )
    check(
        "automatic_action_execution" in execution_boundary["prohibited_operations"],
        "Automatic action execution must remain prohibited.",
    )
    check(
        "retrieval_network_access" in execution_boundary["prohibited_operations"],
        "Network retrieval must remain prohibited.",
    )
    check(
        "scientific_state_mutation" in execution_boundary["prohibited_operations"],
        "Scientific mutation must remain prohibited.",
    )

    print("R7D.6 retrieval attention lifecycle integration audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

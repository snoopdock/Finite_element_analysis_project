#!/usr/bin/env python3
"""Audit the R7D.5 retrieval-attention lifecycle replay layer."""

from __future__ import annotations

from copy import deepcopy

from analysis.retrieval_attention_lifecycle import create_lifecycle_event
from analysis.retrieval_attention_lifecycle_replay import (
    LifecycleReplayError,
    replay_retrieval_attention_lifecycle,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _event(
    event_id: str,
    attention_id: str,
    previous: str | None,
    new: str,
    created_at: str,
) -> dict:
    return {
        "lifecycle_event_id": event_id,
        "attention_id": attention_id,
        "previous_status": previous,
        "new_status": new,
        "transition_reason": f"process transition to {new}",
        "created_at": created_at,
        "actor": "audit",
        "schema_version": 1,
    }


def main() -> int:
    events = [
        _event("evt-3", "attention-1", "addressed", "closed", "2026-09-03T00:02:00Z"),
        _event("evt-1", "attention-1", None, "open", "2026-09-03T00:00:00Z"),
        _event("evt-2", "attention-1", "open", "addressed", "2026-09-03T00:01:00Z"),
    ]
    original = deepcopy(events)

    replayed = replay_retrieval_attention_lifecycle(events)
    check(replayed["event_count"] == 3, "Replay must retain all lifecycle events.")
    check(len(replayed["trajectories"]) == 1, "Expected one attention trajectory.")
    trajectory = replayed["trajectories"][0]
    check(trajectory["initial_status"] is None, "Initial status must be null for creation event.")
    check(trajectory["final_status"] == "closed", "Valid lifecycle must replay to closed.")
    check(
        [item["lifecycle_event_id"] for item in trajectory["transitions"]]
        == ["evt-1", "evt-2", "evt-3"],
        "Replay must order events by recorded metadata.",
    )
    check(events == original, "Replay must not mutate supplied lifecycle history.")

    deterministic = replay_retrieval_attention_lifecycle(list(reversed(events)))
    check(replayed == deterministic, "Replay must be deterministic for equivalent event sets.")

    # Verify the production event-model output can be replayed structurally.
    proposal = {"attention_id": "attention-production-test"}
    created = create_lifecycle_event(
        attention_id=proposal["attention_id"],
        previous_status=None,
        new_status="open",
        transition_reason="attention proposal created",
        actor="audit",
    )
    model_replay = replay_retrieval_attention_lifecycle([created])
    check(model_replay["event_count"] == 1, "Production lifecycle event must be replayable.")
    check(
        model_replay["trajectories"][0]["final_status"] == "open",
        "Production lifecycle event must replay to open.",
    )

    invalid = events[:2] + [
        _event("evt-invalid", "attention-1", "closed", "open", "2026-09-03T00:03:00Z")
    ]
    try:
        replay_retrieval_attention_lifecycle(invalid)
    except LifecycleReplayError:
        pass
    else:
        raise AssertionError("Invalid lifecycle history must fail replay.")

    duplicate_ids = [events[1], deepcopy(events[1])]
    try:
        replay_retrieval_attention_lifecycle(duplicate_ids)
    except LifecycleReplayError:
        pass
    else:
        raise AssertionError("Duplicate lifecycle event IDs must fail replay.")

    malformed = deepcopy(events[1])
    del malformed["transition_reason"]
    try:
        replay_retrieval_attention_lifecycle([malformed])
    except LifecycleReplayError:
        pass
    else:
        raise AssertionError("Malformed lifecycle events must fail replay.")

    scientific_fields = deepcopy(events[1])
    scientific_fields["confidence"] = 0.9
    replay = replay_retrieval_attention_lifecycle([scientific_fields])
    returned = replay["trajectories"][0]["transitions"][0]
    check("confidence" not in returned, "Scientific fields must not enter replay output.")

    print("R7D.5 retrieval attention lifecycle replay audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

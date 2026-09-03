#!/usr/bin/env python3
"""Audit the R7D.4 lifecycle persistence adapter against its contract."""

from __future__ import annotations

from copy import deepcopy

from core.retrieval_attention_lifecycle_persistence import (
    HISTORY_FIELD,
    LifecycleEventIntegrityError,
    LifecycleEventValidationError,
    append_lifecycle_event,
    get_lifecycle_event,
    get_lifecycle_history,
    has_lifecycle_event,
    initialize_lifecycle_history,
)


REQUIRED_FIELDS = {
    "lifecycle_event_id",
    "attention_id",
    "previous_status",
    "new_status",
    "transition_reason",
    "created_at",
    "actor",
    "schema_version",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _event(
    event_id: str = "lifecycle-1",
    *,
    previous_status: str | None = None,
    new_status: str = "open",
    reason: str = "proposal created",
    actor: str = "system",
    created_at: str = "2026-09-03T00:00:00Z",
) -> dict:
    return {
        "lifecycle_event_id": event_id,
        "attention_id": "attention-abc",
        "previous_status": previous_status,
        "new_status": new_status,
        "transition_reason": reason,
        "created_at": created_at,
        "actor": actor,
        "schema_version": 1,
    }


def _three_events() -> list[dict]:
    return [
        _event("lifecycle-1"),
        _event(
            "lifecycle-2",
            previous_status="open",
            new_status="addressed",
            reason="bounded acquisition response recorded",
            created_at="2026-09-03T00:01:00Z",
        ),
        _event(
            "lifecycle-3",
            previous_status="addressed",
            new_status="closed",
            reason="no further lifecycle action is currently required",
            created_at="2026-09-03T00:02:00Z",
        ),
    ]


def main() -> int:
    state = {"scientific_marker": {"unchanged": True}}
    initialize_lifecycle_history(state)
    check(state[HISTORY_FIELD] == {"events": []}, "History initialization is incorrect.")

    first = _event()
    original = deepcopy(first)
    check(append_lifecycle_event(state, first) is True, "First lifecycle event must append.")
    check(first == original, "Appending must not mutate the supplied event.")
    check(has_lifecycle_event(state, "lifecycle-1"), "Persisted lifecycle event must be discoverable.")

    retrieved = get_lifecycle_event(state, "lifecycle-1")
    check(retrieved == first, "Retrieved lifecycle event differs from stored event.")
    retrieved["actor"] = "mutated"
    check(
        get_lifecycle_event(state, "lifecycle-1")["actor"] == "system",
        "get_lifecycle_event must return a defensive copy.",
    )

    history = get_lifecycle_history(state)
    history[0]["actor"] = "mutated"
    check(
        get_lifecycle_history(state)[0]["actor"] == "system",
        "get_lifecycle_history must return defensive copies.",
    )

    identical = deepcopy(first)
    check(
        append_lifecycle_event(state, identical) is False,
        "Identical duplicate lifecycle event must be an idempotent no-op.",
    )
    check(len(get_lifecycle_history(state)) == 1, "Identical duplicate must not append a second event.")

    conflicting = deepcopy(first)
    conflicting["transition_reason"] = "different meaning"
    try:
        append_lifecycle_event(state, conflicting)
    except LifecycleEventIntegrityError:
        pass
    else:
        raise AssertionError("Conflicting duplicate lifecycle ID must raise integrity error.")
    check(
        get_lifecycle_event(state, "lifecycle-1") == first,
        "Conflicting duplicate must leave the original event unchanged.",
    )

    for event in _three_events()[1:]:
        check(append_lifecycle_event(state, event) is True, "Valid lifecycle event must append.")
    check(
        [event["new_status"] for event in get_lifecycle_history(state)] == [
            "open",
            "addressed",
            "closed",
        ],
        "Lifecycle history sequence was not preserved.",
    )

    invalid_events = [
        _event("bad-1", previous_status="open", new_status="open"),
        _event("bad-2", previous_status="addressed", new_status="addressed"),
        _event("bad-3", previous_status="closed", new_status="closed"),
        _event("bad-4", previous_status="closed", new_status="open"),
        _event("bad-5", previous_status="closed", new_status="addressed"),
        _event("bad-6", previous_status="addressed", new_status="open"),
        _event("bad-7", previous_status=None, new_status="addressed"),
        _event("bad-8", previous_status=None, new_status="closed"),
    ]
    for invalid in invalid_events:
        try:
            append_lifecycle_event(state, invalid)
        except LifecycleEventValidationError:
            continue
        raise AssertionError(
            f"Invalid transition unexpectedly persisted: {invalid['previous_status']!r} -> {invalid['new_status']!r}"
        )

    malformed = deepcopy(first)
    del malformed["actor"]
    try:
        append_lifecycle_event(state, malformed)
    except LifecycleEventValidationError:
        pass
    else:
        raise AssertionError("Malformed event must fail validation.")

    for field, value in [
        ("attention_id", ""),
        ("lifecycle_event_id", ""),
        ("transition_reason", ""),
        ("created_at", ""),
        ("actor", ""),
    ]:
        invalid = deepcopy(first)
        invalid[field] = value
        try:
            append_lifecycle_event(state, invalid)
        except LifecycleEventValidationError:
            continue
        raise AssertionError(f"Invalid empty {field} must fail validation.")

    wrong_schema = deepcopy(first)
    wrong_schema["schema_version"] = 2
    try:
        append_lifecycle_event(state, wrong_schema)
    except LifecycleEventValidationError:
        pass
    else:
        raise AssertionError("Unsupported schema version must fail validation.")

    check(
        set(get_lifecycle_event(state, "lifecycle-1")) == REQUIRED_FIELDS,
        "Persisted lifecycle event contains unexpected or missing fields.",
    )
    check(
        "scientific_marker" in state and state["scientific_marker"] == {"unchanged": True},
        "Adapter must not modify unrelated state.",
    )
    check(
        "confidence" not in get_lifecycle_event(state, "lifecycle-1")
        and "truth_status" not in get_lifecycle_event(state, "lifecycle-1")
        and "evidence_strength" not in get_lifecycle_event(state, "lifecycle-1")
        and "epistemic_state" not in get_lifecycle_event(state, "lifecycle-1")
        and "ranking" not in get_lifecycle_event(state, "lifecycle-1")
        and "convergence" not in get_lifecycle_event(state, "lifecycle-1"),
        "Scientific fields must not enter persisted lifecycle events.",
    )

    # Stored ordering is append order; event identity is independently retrievable.
    fetched = get_lifecycle_event(state, "lifecycle-3")
    check(fetched["created_at"] == "2026-09-03T00:02:00Z", "Stored timestamps must remain unchanged.")
    check(fetched["lifecycle_event_id"] == "lifecycle-3", "Stored lifecycle event ID must remain unchanged.")

    print("R7D.4 retrieval attention lifecycle persistence audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

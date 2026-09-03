#!/usr/bin/env python3
"""Audit the R7D.2 pure retrieval-attention lifecycle event model."""

from __future__ import annotations

from copy import deepcopy

from analysis.retrieval_attention_lifecycle import (
    ALLOWED_STATUSES,
    ALLOWED_TRANSITIONS,
    INITIAL_TRANSITION,
    LIFECYCLE_EVENT_SCHEMA_VERSION,
    LifecycleTransitionError,
    create_lifecycle_event,
    validate_lifecycle_event,
    validate_lifecycle_transition,
)


REQUIRED_EVENT_FIELDS = {
    "lifecycle_event_id",
    "attention_id",
    "previous_status",
    "new_status",
    "transition_reason",
    "created_at",
    "actor",
    "schema_version",
}
FORBIDDEN_SCIENTIFIC_FIELDS = {
    "confidence",
    "truth",
    "truth_status",
    "evidence_strength",
    "epistemic_state",
    "ranking",
    "convergence",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_transition_error(previous: str | None, new: str) -> None:
    try:
        validate_lifecycle_transition(previous, new)
    except LifecycleTransitionError:
        return
    raise AssertionError(f"Expected forbidden transition to fail: {previous!r} -> {new!r}")


def main() -> int:
    check(ALLOWED_STATUSES == {"open", "addressed", "closed"}, "Unexpected lifecycle states.")
    check(
        ALLOWED_TRANSITIONS == {
            ("open", "addressed"),
            ("open", "closed"),
            ("addressed", "closed"),
        },
        "Unexpected allowed lifecycle transitions.",
    )
    check(INITIAL_TRANSITION == (None, "open"), "Initial lifecycle transition must be null -> open.")

    # Valid transitions, including initial creation.
    for previous, new in (
        (None, "open"),
        ("open", "addressed"),
        ("open", "closed"),
        ("addressed", "closed"),
    ):
        validate_lifecycle_transition(previous, new)

    # Every same-state transition and every backwards transition must fail explicitly.
    for previous, new in (
        ("open", "open"),
        ("addressed", "addressed"),
        ("closed", "closed"),
        ("closed", "open"),
        ("closed", "addressed"),
        ("addressed", "open"),
        (None, "addressed"),
        (None, "closed"),
    ):
        expect_transition_error(previous, new)

    # Unknown states fail explicitly rather than being normalized into a valid state.
    expect_transition_error("future", "closed")
    expect_transition_error("open", "future")

    event = create_lifecycle_event(
        "attention-test-001",
        "open",
        "addressed",
        "bounded retrieval response recorded",
        "system",
        lifecycle_event_id="lifecycle-test-001",
        created_at="2026-09-03T00:00:00+00:00",
    )
    check(set(event) == REQUIRED_EVENT_FIELDS, "Lifecycle event fields are incomplete or unexpected.")
    check(event["schema_version"] == LIFECYCLE_EVENT_SCHEMA_VERSION, "Unexpected lifecycle event schema version.")
    check(event["attention_id"] == "attention-test-001", "Attention ID was not preserved.")
    check(event["previous_status"] == "open", "Previous status was not preserved.")
    check(event["new_status"] == "addressed", "New status was not preserved.")
    check(event["created_at"] == "2026-09-03T00:00:00+00:00", "Created-at metadata was not preserved.")
    check(event["lifecycle_event_id"] == "lifecycle-test-001", "Explicit event ID was not preserved.")
    check(not (FORBIDDEN_SCIENTIFIC_FIELDS & set(event)), "Scientific fields leaked into lifecycle event.")

    # Creation with omitted timestamp still produces timestamp metadata without affecting identity.
    event_without_explicit_timestamp = create_lifecycle_event(
        "attention-test-002",
        None,
        "open",
        "initial lifecycle tracking",
        "system",
        lifecycle_event_id="lifecycle-test-002",
    )
    check(event_without_explicit_timestamp["previous_status"] is None, "Initial previous status must be null.")
    check(event_without_explicit_timestamp["new_status"] == "open", "Initial new status must be open.")
    check(event_without_explicit_timestamp["created_at"], "Default created_at must be populated.")

    # Inputs are not mutated.
    attention_proposal = {
        "attention_id": "attention-test-003",
        "lifecycle_status": "open",
        "observed_condition": "provider_unavailable",
    }
    retrieval_event = {
        "event_id": "retrieval-test-003",
        "query_scope": ["example query"],
        "report": {"providers": {}},
    }
    history = {"events": [deepcopy(retrieval_event)]}
    attention_before = deepcopy(attention_proposal)
    retrieval_before = deepcopy(retrieval_event)
    history_before = deepcopy(history)

    created = create_lifecycle_event(
        attention_proposal["attention_id"],
        attention_proposal["lifecycle_status"],
        "addressed",
        "response recorded",
        "system",
        lifecycle_event_id="lifecycle-test-003",
        created_at="2026-09-03T00:00:00+00:00",
    )
    check(attention_proposal == attention_before, "Lifecycle creation mutated the attention proposal.")
    check(retrieval_event == retrieval_before, "Lifecycle creation mutated the retrieval event.")
    check(history == history_before, "Lifecycle creation mutated retrieval history.")

    # Validation returns a defensive copy.
    source = deepcopy(created)
    validated = validate_lifecycle_event(source)
    check(validated == source, "Validated event content changed unexpectedly.")
    check(validated is not source, "Validation must return a defensive copy.")
    validated["transition_reason"] = "mutated copy"
    check(source["transition_reason"] == "response recorded", "Validation returned a shallow/shared structure.")

    # Validation rejects malformed events and invalid transitions explicitly.
    missing_field = deepcopy(created)
    missing_field.pop("actor")
    try:
        validate_lifecycle_event(missing_field)
    except ValueError:
        pass
    else:
        raise AssertionError("Missing lifecycle event fields must fail explicitly.")

    invalid_event = deepcopy(created)
    invalid_event["previous_status"] = "closed"
    invalid_event["new_status"] = "open"
    try:
        validate_lifecycle_event(invalid_event)
    except LifecycleTransitionError:
        pass
    else:
        raise AssertionError("Invalid lifecycle event transitions must fail explicitly.")

    # Timestamp is metadata, not a required component of explicit transition identity.
    same_identity_a = create_lifecycle_event(
        "attention-test-004",
        "open",
        "addressed",
        "same transition",
        "system",
        lifecycle_event_id="lifecycle-test-004",
        created_at="2026-09-03T00:00:00+00:00",
    )
    same_identity_b = create_lifecycle_event(
        "attention-test-004",
        "open",
        "addressed",
        "same transition",
        "system",
        lifecycle_event_id="lifecycle-test-004",
        created_at="2026-09-03T01:00:00+00:00",
    )
    check(
        same_identity_a["lifecycle_event_id"] == same_identity_b["lifecycle_event_id"],
        "Lifecycle event identity must remain independent of created_at.",
    )
    check(
        same_identity_a["created_at"] != same_identity_b["created_at"],
        "Audit fixture must demonstrate that timestamps are independent metadata.",
    )

    # No persistence/import integration is exercised here: this audit is strictly model-level.
    print("R7D.2 retrieval attention lifecycle event model audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

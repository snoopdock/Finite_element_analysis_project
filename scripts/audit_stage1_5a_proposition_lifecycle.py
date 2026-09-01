#!/usr/bin/env python3
"""Audit proposition lifecycle semantics."""

from analysis.proposition_lifecycle import (
    CHANGE_TYPES,
    PropositionLifecycleEvent,
    normalize_lifecycle_event,
)


def main() -> int:
    assert {"clarification", "restriction", "generalization", "correction", "replacement", "contradiction"}.issubset(CHANGE_TYPES)

    event = PropositionLifecycleEvent(
        event_id="EV1",
        proposition_id="P1",
        change_type="restriction",
        previous_statement="Method A is stable.",
        new_statement="Method A is stable under coercivity.",
        reason="Added an explicit condition.",
        related_proposition_ids=["P2", "P2"],
        source_ids=["S1", "S1"],
    )
    assert event.change_type == "restriction"
    assert event.related_proposition_ids == ["P2", "P2"]
    assert event.source_ids == ["S1", "S1"]
    assert normalize_lifecycle_event(event.to_dict()) == event.to_dict()

    assert normalize_lifecycle_event({
        "event_id": "EV2",
        "proposition_id": "P1",
        "change_type": "not-a-change",
    }) is None

    # Lifecycle metadata must not become scientific verification.
    payload = event.to_dict()
    assert "verified" not in payload
    assert "truth" not in payload

    print("Stage 1.5A proposition lifecycle audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

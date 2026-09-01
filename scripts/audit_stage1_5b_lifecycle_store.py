#!/usr/bin/env python3
"""Audit proposition lifecycle persistence and deterministic event identity."""

from analysis.proposition_lifecycle_store import lifecycle_event_id, record_lifecycle_event


def main() -> int:
    state = {"knowledge_graph": {}}
    event = {
        "event_id": "ignored-by-store",
        "proposition_id": "P1",
        "change_type": "restriction",
        "previous_statement": "Method A is stable.",
        "new_statement": "Method A is stable under coercivity.",
        "reason": "Added a validity condition.",
        "source_ids": ["S1"],
    }
    expected = lifecycle_event_id("P1", "restriction", event["previous_statement"], event["new_statement"])
    assert record_lifecycle_event(state, event)
    stored = state["knowledge_graph"]["proposition_lifecycle"][0]
    assert stored["event_id"] == expected
    assert stored["change_type"] == "restriction"

    duplicate = dict(event)
    assert not record_lifecycle_event(state, duplicate)
    assert len(state["knowledge_graph"]["proposition_lifecycle"]) == 1

    correction = dict(event, change_type="correction")
    assert record_lifecycle_event(state, correction)
    assert len(state["knowledge_graph"]["proposition_lifecycle"]) == 2

    print("Stage 1.5B lifecycle-store audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

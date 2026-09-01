#!/usr/bin/env python3
"""Combined Stage 1.5 audit for proposition lifecycle semantics."""

from analysis.proposition_lifecycle import PropositionLifecycleEvent
from analysis.proposition_lifecycle_store import lifecycle_event_id, record_lifecycle_event


def main() -> int:
    state = {"knowledge_graph": {}}
    event = PropositionLifecycleEvent(
        event_id="EV1",
        proposition_id="P1",
        change_type="restriction",
        previous_statement="Method A is stable.",
        new_statement="Method A is stable under coercivity.",
        reason="Added missing validity condition.",
        source_ids=["S1"],
    )
    payload = event.to_dict()
    expected_id = lifecycle_event_id(
        "P1", "restriction", payload["previous_statement"], payload["new_statement"]
    )
    assert record_lifecycle_event(state, payload)
    stored = state["knowledge_graph"]["proposition_lifecycle"][0]
    assert stored["event_id"] == expected_id
    assert stored["change_type"] == "restriction"
    assert stored["proposition_id"] == "P1"
    assert not record_lifecycle_event(state, payload)

    # Different scientific change types remain distinguishable.
    correction = dict(payload, change_type="correction")
    assert record_lifecycle_event(state, correction)
    assert len(state["knowledge_graph"]["proposition_lifecycle"]) == 2

    print("Stage 1.5 combined audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

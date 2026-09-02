#!/usr/bin/env python3
"""Audit the R6 retrieval history state adapter in isolation."""

from __future__ import annotations

from copy import deepcopy

from core.retrieval_history_state import (
    append_retrieval_event,
    get_retrieval_event,
    get_retrieval_history,
    has_retrieval_event,
    initialize_retrieval_history,
)


def _event(event_id: str, cycle: int):
    return {
        "event_id": event_id,
        "cycle": cycle,
        "retrieved_at": f"2026-09-03T00:00:0{cycle}Z",
        "report": {
            "status": "partial_failure",
            "query_count": 1,
            "providers": {
                "semantic_scholar": {
                    "status": "rate_limited",
                    "attempts": 1,
                    "queries": ["weak form Galerkin FEM"],
                }
            },
            "returned_records": 0,
            "selected_records": 0,
        },
        "acquisition_assessment": {
            "status": "partial_provider_availability",
            "operational_status": "partial_failure",
            "available_provider_count": 0,
            "unavailable_provider_count": 1,
            "returned_records": 0,
            "selected_records": 0,
        },
    }


def main() -> int:
    state = {
        "cycle": 7,
        "knowledge_graph": {
            "propositions": {"p1": {"text": "example"}},
        },
        "epistemic_state": {"p1": {"status": "uncertain"}},
    }

    initialize_retrieval_history(state)
    assert state["retrieval_history"] == {"events": []}

    event1 = _event("retrieval-001", 1)
    event2 = _event("retrieval-002", 2)
    before_scientific = deepcopy(
        (state["knowledge_graph"], state["epistemic_state"])
    )

    assert append_retrieval_event(state, event1) is True
    assert append_retrieval_event(state, event2) is True
    assert append_retrieval_event(state, event1) is False

    history = get_retrieval_history(state)
    assert [event["event_id"] for event in history] == [
        "retrieval-001",
        "retrieval-002",
    ]
    assert has_retrieval_event(state, "retrieval-001") is True
    assert has_retrieval_event(state, "missing") is False
    assert get_retrieval_event(state, "retrieval-002")["cycle"] == 2

    # Returned history must be defensive: mutating it must not mutate state.
    history[0]["cycle"] = 99
    assert state["retrieval_history"]["events"][0]["cycle"] == 1

    assert (
        state["knowledge_graph"],
        state["epistemic_state"],
    ) == before_scientific

    print("R6 retrieval history state adapter audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""End-to-end offline audit of the R6 retrieval-history subsystem."""

from __future__ import annotations

from copy import deepcopy
import tempfile
from pathlib import Path

from analysis.retrieval_event import create_retrieval_event
from analysis.retrieval_replay import replay_retrieval_event
from core.retrieval_history_state import append_retrieval_event
from core.state_manager import initialize_state, save_state, SCHEMA_VERSION


def _report(status: str = "partial_failure"):
    return {
        "status": status,
        "query_count": 2,
        "providers": {
            "arxiv": {
                "status": "success",
                "attempts": 1,
                "queries": [
                    "weak form Galerkin FEM",
                    "finite element stability",
                ],
                "returned_records": 3,
            },
            "semantic_scholar": {
                "status": "rate_limited",
                "attempts": 1,
                "queries": ["weak form Galerkin FEM"],
                "returned_records": 0,
            },
        },
        "returned_records": 3,
        "selected_records": 2,
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state" / "current_state.json"
        paths = {"state": state_path}
        config = {"topic": "FEM", "objective": "integration audit"}

        state = initialize_state(paths, config)
        state["knowledge_graph"]["propositions"] = {
            "p1": {"text": "example proposition"}
        }
        scientific_before = deepcopy(state["knowledge_graph"])

        event_a = create_retrieval_event(
            cycle=0,
            queries=None,
            report=_report(),
        )
        assert append_retrieval_event(state, event_a) is True
        assert len(state["retrieval_history"]["events"]) == 1

        # Persist and restart the process.
        save_state(paths, state)
        restarted = initialize_state(paths, config)
        assert len(restarted["retrieval_history"]["events"]) == 1
        assert restarted["retrieval_history"]["events"][0] == event_a

        # Re-persisting the same logical event is idempotent across reloads.
        assert append_retrieval_event(restarted, event_a) is False
        save_state(paths, restarted)
        after_duplicate = initialize_state(paths, config)
        assert len(after_duplicate["retrieval_history"]["events"]) == 1

        # A genuinely new retrieval operation creates a new event.
        event_b = create_retrieval_event(
            cycle=1,
            queries=None,
            report=_report("success"),
        )
        assert event_b["event_id"] != event_a["event_id"]
        assert append_retrieval_event(after_duplicate, event_b) is True
        save_state(paths, after_duplicate)

        final_state = initialize_state(paths, config)
        events = final_state["retrieval_history"]["events"]
        assert [event["cycle"] for event in events] == [0, 1]
        assert final_state["schema_version"] == SCHEMA_VERSION

        # Replay must reconstruct process facts without network access or mutation.
        replayed = replay_retrieval_event(events[0])
        assert replayed["event_id"] == event_a["event_id"]
        assert replayed["cycle"] == event_a["cycle"]
        assert replayed["query_scope"] == event_a["query_scope"]
        assert replayed["operational_status"] == event_a["report"]["status"]
        assert replayed["acquisition_assessment"] == event_a["acquisition_assessment"]

        # Scientific state remains untouched by retrieval-history operations.
        assert final_state["knowledge_graph"] == scientific_before

        # Historical failure remains historical after a later successful event.
        assert events[0]["report"]["status"] == "partial_failure"
        assert events[1]["report"]["status"] == "success"
        assert events[0]["acquisition_assessment"]["status"] == "partial_provider_availability"

    print("R6 retrieval history integration audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

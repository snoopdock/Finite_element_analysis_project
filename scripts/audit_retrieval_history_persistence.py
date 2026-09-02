#!/usr/bin/env python3
"""Audit retrieval-history initialization and JSON round-trip persistence."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.retrieval_history_state import append_retrieval_event
from core.state_manager import initialize_state, save_state, SCHEMA_VERSION
from utils.text import utcnow


def _event(event_id: str, cycle: int):
    return {
        "event_id": event_id,
        "cycle": cycle,
        "retrieved_at": utcnow(),
        "query_scope": ["weak form Galerkin FEM"],
        "report": {
            "status": "partial_failure",
            "query_count": 1,
            "providers": {
                "arxiv": {"status": "success", "records": 2},
                "semantic_scholar": {
                    "status": "rate_limited",
                    "records": 0,
                },
            },
            "returned_records": 2,
            "selected_records": 2,
        },
        "acquisition_assessment": {
            "status": "partial_provider_availability",
            "operational_status": "partial_failure",
            "available_provider_count": 1,
            "unavailable_provider_count": 1,
            "returned_records": 2,
            "selected_records": 2,
        },
        "schema_version": 1,
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_path = root / "state" / "current_state.json"
        paths = {"state": state_path}
        config = {"topic": "FEM", "objective": "test"}

        state = initialize_state(paths, config)
        assert state["schema_version"] == SCHEMA_VERSION
        assert state["retrieval_history"] == {"events": []}

        event_a = _event("retrieval-a", 0)
        event_b = _event("retrieval-b", 1)
        assert append_retrieval_event(state, event_a) is True
        assert append_retrieval_event(state, event_b) is True

        save_state(paths, state)

        raw = json.loads(state_path.read_text(encoding="utf-8"))
        assert raw["retrieval_history"]["events"] == [event_a, event_b]
        assert raw["schema_version"] == SCHEMA_VERSION

        reloaded = initialize_state(paths, config)
        assert reloaded["retrieval_history"]["events"] == [event_a, event_b]
        assert reloaded["retrieval_report"]["status"] == "not_run"

        # A repeated save must preserve exactly the same history.
        save_state(paths, reloaded)
        reloaded_again = initialize_state(paths, config)
        assert reloaded_again["retrieval_history"]["events"] == [
            event_a,
            event_b,
        ]

        # A later event is appended after a restart, without overwriting A/B.
        event_c = _event("retrieval-c", 2)
        assert append_retrieval_event(reloaded_again, event_c) is True
        save_state(paths, reloaded_again)
        restarted = initialize_state(paths, config)
        assert [
            event["event_id"]
            for event in restarted["retrieval_history"]["events"]
        ] == ["retrieval-a", "retrieval-b", "retrieval-c"]

        # Legacy/malformed history is normalized into the canonical container.
        malformed_path = root / "state" / "malformed.json"
        malformed_path.write_text(
            json.dumps({
                "schema_version": SCHEMA_VERSION,
                "retrieval_history": ["bad", 123],
            }),
            encoding="utf-8",
        )
        malformed = initialize_state(
            {"state": malformed_path},
            config,
        )
        assert malformed["retrieval_history"] == {"events": []}
        assert malformed["schema_version"] == SCHEMA_VERSION

    print("R6 retrieval history persistence audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit the retrieval-report state field and round-trip persistence."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.state_manager import initialize_state, save_state


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        paths = {"state": state_path}
        config = {}

        state = initialize_state(paths, config)
        report = state.get("retrieval_report")
        if not isinstance(report, dict):
            raise AssertionError("retrieval_report must be a dictionary")
        if report.get("status") != "not_run":
            raise AssertionError("new state must initialize retrieval_report to not_run")

        state["retrieval_report"] = {
            "status": "partial_failure",
            "query_count": 2,
            "providers": {
                "arxiv": {"status": "success"},
                "semantic_scholar": {"status": "rate_limited"},
            },
            "returned_records": 2,
            "selected_records": 2,
        }
        save_state(paths, state)

        round_tripped = json.loads(state_path.read_text(encoding="utf-8"))
        persisted = round_tripped.get("retrieval_report")
        if persisted != state["retrieval_report"]:
            raise AssertionError("retrieval_report did not survive persistence")

        reloaded = initialize_state(paths, config)
        if reloaded.get("retrieval_report") != state["retrieval_report"]:
            raise AssertionError("retrieval_report did not survive reload")
        if reloaded.get("schema_version") != 5:
            raise AssertionError("retrieval report must not require a schema-version bump")

    print("retrieval report state audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

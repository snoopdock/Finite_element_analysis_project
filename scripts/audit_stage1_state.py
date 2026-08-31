#!/usr/bin/env python3
"""Runtime audit for Stage 1 state initialization and migration.

This audit uses a temporary directory and never writes to the repository's
real state/current_state.json.

Run from the repository root:
    python scripts/audit_stage1_state.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.state_manager import SCHEMA_VERSION, initialize_state, save_state
from core.knowledge_graph import validate_graph_references
from core.graph_state import graph_summary



def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)



def _paths(directory: Path) -> dict[str, str]:
    return {"state": str(directory / "state.json")}



def _audit_new_state() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        config = {"topic": "Stage 1 audit", "objective": "Runtime state check"}
        state = initialize_state(_paths(directory), config)

        graph = state.get("knowledge_graph", {})
        _assert(state.get("schema_version") == SCHEMA_VERSION, "Unexpected schema version.")
        _assert(set(graph) >= {"concepts", "propositions", "relationships", "concept_history"}, "Incomplete graph container.")
        _assert(not validate_graph_references(graph), "Fresh graph contains reference violations.")

        save_state(_paths(directory), state)
        restored = initialize_state(_paths(directory), config)
        _assert(restored.get("schema_version") == SCHEMA_VERSION, "Round-trip changed schema version.")
        _assert(graph_summary(restored)["violations"] == 0, "Round-trip produced graph violations.")
        return graph_summary(restored)



def _audit_v4_migration() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        paths = _paths(directory)
        legacy = {
            "schema_version": 4,
            "topic": "Migration audit",
            "objective": "Preserve legacy knowledge",
            "knowledge_base": {
                "concepts": [
                    {"name": "Galerkin method", "source_ids": ["paper-1"]},
                ],
                "rules": [
                    {"rule": "A test proposition", "source_ids": ["paper-2"]},
                ],
            },
            "knowledge_graph": {},
            "sections": [],
            "iteration_history_data": {},
        }
        with open(paths["state"], "w", encoding="utf-8") as handle:
            json.dump(legacy, handle)

        state = initialize_state(paths, {})
        kb = state.get("knowledge_base", {})
        graph = state.get("knowledge_graph", {})
        concepts = graph.get("concepts", {})
        propositions = graph.get("propositions", {})

        _assert(state.get("schema_version") == SCHEMA_VERSION, "v4 state did not migrate.")
        _assert(len(kb.get("concepts", [])) == 1, "Legacy concept was lost during migration.")
        _assert(any(c.get("name") == "Galerkin method" for c in concepts.values()), "Concept was not bridged.")
        _assert(any(p.get("statement") == "A test proposition" for p in propositions.values()), "Proposition was not bridged.")
        _assert(not validate_graph_references(graph), "Migrated graph contains violations.")
        return graph_summary(state)



def main() -> int:
    try:
        new_state_summary = _audit_new_state()
        migration_summary = _audit_v4_migration()
    except Exception as exc:
        print(f"STAGE 1 STATE AUDIT: ERROR: {exc}")
        return 2

    print("Stage 1 state runtime audit")
    print("===========================")
    print(f"schema_version: {SCHEMA_VERSION}")
    print(f"new-state summary: {new_state_summary}")
    print(f"migration summary: {migration_summary}")
    print("\nPASS: initialization, atomic round-trip, and v4→v5 graph migration checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

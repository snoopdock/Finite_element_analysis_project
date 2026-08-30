#!/usr/bin/env python3
"""State management with schema versioning."""

import json
import pathlib
from typing import Dict

from core.section_identity import normalize_sections

SCHEMA_VERSION = 4


def initialize_state(paths: Dict, config: Dict) -> Dict:
    """Load state and migrate it to the current schema."""
    state_path = pathlib.Path(paths["state"])

    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = _default_state(config)
    else:
        state = _default_state(config)

    if not isinstance(state, dict):
        state = _default_state(config)

    stored_version = state.get("schema_version", 1)
    try:
        stored_version = int(stored_version)
    except (TypeError, ValueError):
        stored_version = 1

    if stored_version < SCHEMA_VERSION:
        state = _migrate_state(state, stored_version, SCHEMA_VERSION)

    # Also normalize current state. This makes the migration robust when a
    # state file was manually edited or produced by an older writer.
    state["sections"] = normalize_sections(state.get("sections", []))
    state["schema_version"] = SCHEMA_VERSION
    return state


def _default_state(config: Dict) -> Dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "topic": config.get("topic", ""),
        "objective": config.get("objective", ""),
        "cycle": 0,
        "iteration": 0,
        "last_run": None,
        "last_run_status": None,
        "knowledge_base": {},
        "sections": [],
        "processed_sources": [],
        "processed_sources_extracted": [],
        "iteration_history_data": {},
        "convergence_diagnostics": {},
    }


def _migrate_state(state: Dict, from_version: int, to_version: int) -> Dict:
    """Apply sequential state migrations."""
    if from_version < 2:
        state = _migrate_v1_to_v2(state)
        from_version = 2

    if from_version < 3:
        state = _migrate_v2_to_v3(state)
        from_version = 3

    if from_version < 4:
        state = _migrate_v3_to_v4(state)
        from_version = 4

    state["schema_version"] = to_version
    return state


def _migrate_v1_to_v2(state: Dict) -> Dict:
    """Migration: v1 -> v2. Added reading state tracking."""
    if "reading_state" not in state:
        state["reading_state"] = {}
    return state


def _migrate_v2_to_v3(state: Dict) -> Dict:
    """Migration: v2 -> v3. Added section status tracking."""
    for section in state.get("sections", []):
        if not isinstance(section, dict):
            continue
        if "status" not in section:
            content = section.get("content", "")
            if content and len(str(content).split()) >= 100:
                section["status"] = "complete"
            elif content:
                section["status"] = "incomplete"
            else:
                section["status"] = "needs_generation"
    return state


def _migrate_v3_to_v4(state: Dict) -> Dict:
    """Migration: v3 -> v4. Added stable UUID section identity."""
    state["sections"] = normalize_sections(state.get("sections", []))
    return state


def save_state(paths: Dict, state: Dict):
    """Normalize and save state to disk."""
    state_path = pathlib.Path(paths["state"])
    state_path.parent.mkdir(parents=True, exist_ok=True)

    state["sections"] = normalize_sections(state.get("sections", []))
    state["schema_version"] = SCHEMA_VERSION

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

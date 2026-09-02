#!/usr/bin/env python3
"""State management with schema versioning and stable section/graph identity."""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Dict

from core.section_identity import normalize_sections
from core.knowledge_graph import normalize_graph, validate_graph_references
from core.graph_state import ensure_graph_state, empty_graph
from core.retrieval_history_state import initialize_retrieval_history

SCHEMA_VERSION = 5


def initialize_state(paths: Dict, config: Dict) -> Dict:
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

    state["sections"] = normalize_sections(state.get("sections", []))
    _normalize_iteration_history(state)
    ensure_graph_state(state)
    state["knowledge_graph"] = normalize_graph(state["knowledge_graph"])
    state["knowledge_graph_violations"] = validate_graph_references(
        state["knowledge_graph"]
    )
    state.setdefault("retrieval_report", _empty_retrieval_report())
    initialize_retrieval_history(state)
    state["schema_version"] = SCHEMA_VERSION
    return state


def _empty_retrieval_report() -> Dict:
    return {
        "status": "not_run",
        "query_count": 0,
        "providers": {},
        "returned_records": 0,
        "selected_records": 0,
    }


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
        "knowledge_graph": empty_graph(),
        "knowledge_graph_violations": [],
        "sections": [],
        "processed_sources": [],
        "processed_sources_extracted": [],
        "iteration_history_data": {},
        "convergence_diagnostics": {},
        "retrieval_report": _empty_retrieval_report(),
        "retrieval_history": {"events": []},
    }


def _migrate_state(state: Dict, from_version: int, to_version: int) -> Dict:
    if from_version < 2:
        state = _migrate_v1_to_v2(state)
        from_version = 2
    if from_version < 3:
        state = _migrate_v2_to_v3(state)
        from_version = 3
    if from_version < 4:
        state = _migrate_v3_to_v4(state)
        from_version = 4
    if from_version < 5:
        state = _migrate_v4_to_v5(state)
    state["schema_version"] = to_version
    return state


def _migrate_v1_to_v2(state: Dict) -> Dict:
    if "reading_state" not in state:
        state["reading_state"] = {}
    return state


def _migrate_v2_to_v3(state: Dict) -> Dict:
    for section in state.get("sections", []):
        if not isinstance(section, dict):
            continue
        if "status" not in section:
            content = section.get("content", "")
            word_count = len(str(content).split()) if content else 0
            if word_count >= 100:
                section["status"] = "complete"
            elif content:
                section["status"] = "incomplete"
            else:
                section["status"] = "needs_generation"
    return state


def _migrate_v3_to_v4(state: Dict) -> Dict:
    state["sections"] = normalize_sections(state.get("sections", []))
    _normalize_iteration_history(state)
    return state


def _migrate_v4_to_v5(state: Dict) -> Dict:
    graph = state.get("knowledge_graph", {})
    if not isinstance(graph, dict):
        graph = {}
    graph.setdefault("concepts", {})
    graph.setdefault("propositions", {})
    graph.setdefault("relationships", {})
    graph.setdefault("concept_history", [])
    state["knowledge_graph"] = graph
    state["knowledge_graph_violations"] = []
    return state


def _title_to_id(state: Dict) -> Dict[str, str]:
    mapping = {}
    for section in state.get("sections", []):
        if not isinstance(section, dict):
            continue
        title = str(section.get("title", "")).strip()
        section_id = section.get("section_id")
        if title and section_id:
            mapping[title] = section_id
    return mapping


def _replace_title_tokens(key: str, title_to_id: Dict[str, str]) -> str:
    if not isinstance(key, str):
        return key
    for title in sorted(title_to_id, key=len, reverse=True):
        if title in key:
            key = key.replace(title, title_to_id[title])
    return key


def _normalize_iteration_history(state: Dict) -> None:
    history = state.get("iteration_history_data")
    if not isinstance(history, dict):
        return

    title_to_id = _title_to_id(state)
    section_titles = history.get("section_titles", {})
    if not isinstance(section_titles, dict):
        section_titles = {}
    for title, section_id in title_to_id.items():
        section_titles[title] = section_id
    history["section_titles"] = section_titles

    if not title_to_id:
        return

    audits = history.get("audits", {})
    if isinstance(audits, dict):
        migrated_audits = {}
        for key, values in audits.items():
            new_key = title_to_id.get(key, key)
            if not isinstance(values, list):
                values = []
            migrated_audits.setdefault(new_key, []).extend(values)
        history["audits"] = migrated_audits

    for field in ("anomalies", "anomaly_counts"):
        data = history.get(field, {})
        if not isinstance(data, dict):
            history[field] = {}
            continue
        migrated = {}
        for key, value in data.items():
            new_key = _replace_title_tokens(str(key), title_to_id)
            try:
                numeric = int(value)
            except (TypeError, ValueError):
                numeric = 0
            migrated[new_key] = migrated.get(new_key, 0) + numeric
        history[field] = migrated


def save_state(paths: Dict, state: Dict):
    """Normalize and atomically save state."""
    state_path = pathlib.Path(paths["state"])
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["sections"] = normalize_sections(state.get("sections", []))
    _normalize_iteration_history(state)
    ensure_graph_state(state)
    state["knowledge_graph"] = normalize_graph(state["knowledge_graph"])
    state["knowledge_graph_violations"] = validate_graph_references(
        state["knowledge_graph"]
    )
    state.setdefault("retrieval_report", _empty_retrieval_report())
    initialize_retrieval_history(state)
    state["schema_version"] = SCHEMA_VERSION

    fd, tmp_path = tempfile.mkstemp(
        dir=state_path.parent,
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, state_path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise

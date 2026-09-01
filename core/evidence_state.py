#!/usr/bin/env python3
"""Persistent state helpers for scientific evidence characterization."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from analysis.evidence_characterization import (
    normalize_evidence_characterization,
    normalize_evidence_scope,
)


def _clean_ids(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def upsert_evidence_characterization(
    state: Dict[str, Any],
    source_id: str,
    characterization: Optional[Dict[str, Any]],
) -> bool:
    """Persist characterization keyed by source_id without changing source metadata."""
    if not isinstance(state, dict):
        return False
    source_key = str(source_id).strip()
    if not source_key:
        return False

    evidence_state = state.setdefault("evidence_characterization", {})
    if not isinstance(evidence_state, dict):
        evidence_state = {}
        state["evidence_characterization"] = evidence_state

    normalized = normalize_evidence_characterization(characterization)
    current = evidence_state.get(source_key)
    if current == normalized:
        return False
    evidence_state[source_key] = normalized
    return True


def upsert_evidence_scope(
    state: Dict[str, Any],
    source_id: str,
    *,
    proposition_ids: Optional[Iterable[str]] = None,
    relationships: Optional[Dict[str, str]] = None,
) -> bool:
    """Persist proposition-level evidence relevance separately from source metadata."""
    if not isinstance(state, dict):
        return False
    source_key = str(source_id).strip()
    if not source_key:
        return False

    scope_state = state.setdefault("evidence_scope", {})
    if not isinstance(scope_state, dict):
        scope_state = {}
        state["evidence_scope"] = scope_state

    normalized = normalize_evidence_scope({
        "proposition_ids": list(proposition_ids or []),
        "relationships": relationships or {},
    })
    current = scope_state.get(source_key)
    if current == normalized:
        return False
    scope_state[source_key] = normalized
    return True

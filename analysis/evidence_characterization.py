#!/usr/bin/env python3
"""Structured scientific characterization of literature evidence.

This module deliberately separates scientific evidence characterization from
retrieval ranking. It describes the role and nature of a source without
collapsing those properties into a single quality score.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


PUBLICATION_STATUSES = {
    "peer_reviewed",
    "preprint",
    "published",
    "conference",
    "book",
    "thesis",
    "unknown",
}

STUDY_TYPES = {
    "theoretical",
    "experimental",
    "observational",
    "simulation",
    "computational",
    "review",
    "survey",
    "methodological",
    "mixed",
    "unknown",
}

EVIDENCE_ROLES = {
    "primary",
    "secondary",
    "background",
    "methodological",
    "replication",
    "critique",
    "review",
    "unknown",
}

REPLICATION_STATUSES = {
    "replicated",
    "partially_replicated",
    "not_replicated",
    "unknown",
}

CLAIM_RELATIONSHIPS = {
    "supports",
    "challenges",
    "qualifies",
    "provides_context_for",
    "does_not_address",
    "unknown",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_list(values: Any) -> List[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    result: List[str] = []
    seen = set()
    for value in values:
        text = _clean(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def normalize_evidence_characterization(
    value: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Normalize structured evidence metadata without inventing missing facts."""
    raw = value if isinstance(value, dict) else {}

    publication_status = _clean(raw.get("publication_status")).lower()
    if publication_status not in PUBLICATION_STATUSES:
        publication_status = "unknown"

    study_type = _clean(raw.get("study_type")).lower()
    if study_type not in STUDY_TYPES:
        study_type = "unknown"

    evidence_role = _clean(raw.get("evidence_role")).lower()
    if evidence_role not in EVIDENCE_ROLES:
        evidence_role = "unknown"

    replication_status = _clean(raw.get("replication_status")).lower()
    if replication_status not in REPLICATION_STATUSES:
        replication_status = "unknown"

    primary_or_secondary = _clean(raw.get("primary_or_secondary")).lower()
    if primary_or_secondary not in {"primary", "secondary", "mixed", "unknown"}:
        primary_or_secondary = "unknown"

    return {
        "publication_status": publication_status,
        "study_type": study_type,
        "evidence_role": evidence_role,
        "primary_or_secondary": primary_or_secondary,
        "replication_status": replication_status,
        "methodological_description": _clean(raw.get("methodological_description")),
        "limitations": _clean_list(raw.get("limitations", [])),
        "notes": _clean_list(raw.get("notes", [])),
    }


def characterize_source(
    source: Dict[str, Any],
    *,
    characterization: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a source record with a separate scientific characterization.

    Existing retrieval/provenance fields are copied unchanged. This helper
    does not assign scientific properties from provider names or URLs.
    """
    record = dict(source) if isinstance(source, dict) else {}
    record["evidence_characterization"] = normalize_evidence_characterization(
        characterization if characterization is not None else record.get("evidence_characterization")
    )
    return record


def normalize_evidence_scope(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize which proposition(s) a source item is relevant to."""
    raw = value if isinstance(value, dict) else {}
    proposition_ids = _clean_list(raw.get("proposition_ids", []))
    relationships = raw.get("relationships", {})
    if not isinstance(relationships, dict):
        relationships = {}

    normalized_relationships: Dict[str, str] = {}
    for proposition_id, relationship in relationships.items():
        relation = _clean(relationship).lower()
        if relation not in CLAIM_RELATIONSHIPS:
            relation = "unknown"
        proposition_key = _clean(proposition_id)
        if proposition_key:
            normalized_relationships[proposition_key] = relation

    return {
        "proposition_ids": proposition_ids,
        "relationships": normalized_relationships,
    }


def attach_evidence_scope(
    source: Dict[str, Any],
    *,
    proposition_ids: Optional[Iterable[str]] = None,
    relationships: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Attach proposition-level evidence relevance without changing source identity."""
    record = dict(source) if isinstance(source, dict) else {}
    record["evidence_scope"] = normalize_evidence_scope(
        {
            "proposition_ids": list(proposition_ids or []),
            "relationships": relationships or {},
        }
    )
    return record

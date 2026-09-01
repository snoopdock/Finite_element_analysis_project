#!/usr/bin/env python3
"""Deterministic identity helpers for evidence-to-proposition relations."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, List


_ALLOWED_RELATIONS = {
    "supports",
    "challenges",
    "qualifies",
    "provides_context_for",
    "reproduces",
    "does_not_address",
    "unknown",
}


def _clean_ids(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def evidence_relation_id(
    source_id: Any,
    proposition_id: Any,
    relationship: Any,
    passage_ids: Iterable[Any] = (),
) -> str:
    """Return a deterministic identity for one source/proposition evidence relation."""
    source = str(source_id or "").strip()
    proposition = str(proposition_id or "").strip()
    relation = str(relationship or "unknown").strip().lower()
    passages = sorted(_clean_ids(passage_ids))
    payload = "|".join([source, proposition, relation, *passages])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return "evidrel-" + digest


def normalize_evidence_relation_identity(relation: dict) -> dict:
    """Return a copy with canonical relationship and deterministic relation ID."""
    normalized = dict(relation) if isinstance(relation, dict) else {}
    relationship = str(normalized.get("relationship", "unknown")).strip().lower()
    if relationship not in _ALLOWED_RELATIONS:
        relationship = "unknown"
    normalized["relationship"] = relationship
    normalized["passage_ids"] = sorted(_clean_ids(normalized.get("passage_ids", [])))
    normalized["evidence_relation_id"] = evidence_relation_id(
        normalized.get("source_id"),
        normalized.get("proposition_id"),
        relationship,
        normalized["passage_ids"],
    )
    return normalized


def deduplicate_evidence_relations(relations: Iterable[dict]) -> List[dict]:
    """Keep the latest occurrence for each deterministic evidence-relation identity."""
    deduplicated = {}
    for relation in relations or []:
        if not isinstance(relation, dict):
            continue
        normalized = normalize_evidence_relation_identity(relation)
        key = normalized["evidence_relation_id"]
        deduplicated[key] = normalized
    return [deduplicated[key] for key in sorted(deduplicated)]

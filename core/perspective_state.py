#!/usr/bin/env python3
"""State helpers for provenance-aware proposition comparisons."""

from __future__ import annotations

from typing import Any, Dict, List


def normalize_comparison_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one persisted comparison without inventing scientific content."""
    if not isinstance(record, dict):
        return {}

    proposition_ids = record.get("proposition_ids", [])
    if isinstance(proposition_ids, str):
        proposition_ids = [proposition_ids]
    if not isinstance(proposition_ids, list):
        proposition_ids = []

    proposition_ids = [str(value) for value in proposition_ids if str(value).strip()]
    proposition_ids = sorted(set(proposition_ids))

    source_ids = record.get("source_ids", [])
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    if not isinstance(source_ids, list):
        source_ids = []
    source_ids = sorted(set(str(value) for value in source_ids if str(value).strip()))

    comparison = record.get("comparison", {})
    if not isinstance(comparison, dict):
        comparison = {}

    relationship = str(comparison.get("relationship", "insufficient_evidence")).strip().lower()
    try:
        confidence = max(0.0, min(1.0, float(comparison.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "comparison_id": str(record.get("comparison_id", "")).strip(),
        "proposition_ids": proposition_ids,
        "source_ids": source_ids,
        "comparison": {
            "relationship": relationship or "insufficient_evidence",
            "confidence": round(confidence, 4),
            "shared_context": list(comparison.get("shared_context", [])) if isinstance(comparison.get("shared_context", []), list) else [],
            "different_context": list(comparison.get("different_context", [])) if isinstance(comparison.get("different_context", []), list) else [],
            "reason": str(comparison.get("reason", "")).strip(),
        },
        "context_basis": record.get("context_basis", {}) if isinstance(record.get("context_basis", {}), dict) else {},
        "skipped": bool(record.get("skipped", False)),
        "reason": str(record.get("reason", "")).strip(),
    }


def upsert_comparison(history: List[Dict[str, Any]], record: Dict[str, Any], max_records: int = 200) -> List[Dict[str, Any]]:
    """Upsert by comparison ID while retaining bounded history."""
    normalized = normalize_comparison_record(record)
    comparison_id = normalized.get("comparison_id")
    if not comparison_id:
        return list(history or [])[-max(0, int(max_records)):]

    current = [item for item in (history or []) if isinstance(item, dict) and item.get("comparison_id") != comparison_id]
    current.append(normalized)
    return current[-max(0, int(max_records)):]


def find_comparison(history: List[Dict[str, Any]], comparison_id: str) -> Dict[str, Any] | None:
    target = str(comparison_id or "").strip()
    for record in history or []:
        if isinstance(record, dict) and str(record.get("comparison_id", "")) == target:
            return record
    return None

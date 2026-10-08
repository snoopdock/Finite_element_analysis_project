"""Shared helpers for graph analyzers."""

from __future__ import annotations

from typing import Any, Iterable

from .identity import deterministic_id
from .models import AnalysisType, TraversalDirection
from .observations import SemanticObservation
from .traversal import TraversalResult


def parse_direction(value: Any) -> TraversalDirection:
    try:
        return TraversalDirection(str(value or TraversalDirection.OUTGOING.value))
    except ValueError as exc:
        raise ValueError(f"Unsupported traversal direction: {value!r}") from exc


def parse_max_depth(value: Any, default: int | None) -> int | None:
    if value is None:
        return default
    if value == "unbounded":
        return None
    try:
        depth = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid max_depth: {value!r}") from exc
    if depth < 0:
        raise ValueError("max_depth must be non-negative.")
    return depth


def parse_relation_types(value: Any, default: Iterable[str] | None = None) -> tuple[str, ...] | None:
    if value is None:
        if default is None:
            return None
        return tuple(dict.fromkeys(str(item) for item in default))
    if isinstance(value, str):
        value = [value]
    normalized = tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item).strip()
        )
    )
    return normalized


def observations_from_traversal(result: TraversalResult) -> tuple[SemanticObservation, ...]:
    evidence_by_id = {record.evidence_id: record for record in result.evidence}
    observations: dict[str, SemanticObservation] = {}

    for step in result.steps:
        evidence = evidence_by_id[step.evidence_id]
        observation = SemanticObservation.create(
            subject_id=evidence.subject_id,
            predicate=evidence.predicate,
            object_id=evidence.object_id,
            evidence_ids=(evidence.evidence_id,),
            depth=step.depth,
            metadata={
                "traversed_from": step.traversed_from,
                "traversed_to": step.traversed_to,
            },
        )
        observations[observation.observation_id] = observation

    return tuple(observations[key] for key in sorted(observations))


def make_analysis_id(
    *,
    analysis_type: AnalysisType,
    query_id: str,
    graph_fingerprint: str,
    parameters: dict[str, Any],
) -> str:
    return deterministic_id(
        "analysis",
        {
            "analysis_type": analysis_type.value,
            "query_id": query_id,
            "graph_fingerprint": graph_fingerprint,
            "parameters": parameters,
        },
        length=24,
    )

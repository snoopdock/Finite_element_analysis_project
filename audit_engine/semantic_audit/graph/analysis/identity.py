"""Deterministic identities and fingerprints for graph analysis artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge,
    SemanticGraph,
)


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def deterministic_id(namespace: str, payload: Any, length: int = 20) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"{namespace}:{digest[:length]}"


def edge_payload(edge: SemanticEdge) -> dict[str, Any]:
    return {
        "source": edge.source_id,
        "target": edge.target_id,
        "relation": edge.relation_type,
        "attributes": edge.attributes,
        "metadata": edge.metadata,
    }


def edge_fingerprint(edge: SemanticEdge) -> str:
    return deterministic_id("edge", edge_payload(edge), length=24)


def graph_fingerprint(graph: SemanticGraph) -> str:
    """Return a content fingerprint independent of insertion ordering."""

    payload = graph.to_dict()
    payload["nodes"] = sorted(
        payload["nodes"],
        key=lambda value: (
            value["id"],
            value["type"],
            _canonical_json(value),
        ),
    )
    payload["edges"] = sorted(
        payload["edges"],
        key=lambda value: (
            value["source"],
            value["target"],
            value["relation"],
            _canonical_json(value),
        ),
    )
    return deterministic_id("graph", payload, length=32)

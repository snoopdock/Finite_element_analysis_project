"""Adapter between retrieval evidence objects and LaTeX reference IR.

Retrieval layers may contain rich metadata.
The LaTeX IR requires a strict reference schema.

This module transforms structure only.
"""

from typing import Any


def adapt_evidence_item_to_reference(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise TypeError("Evidence item must be a dictionary.")

    required = ["source_id", "title"]

    for field in required:
        if field not in evidence:
            raise ValueError(f"Missing required evidence field: {field}")

    source_id = str(evidence.get("source_id", "")).strip()
    title = str(evidence.get("title", "")).strip()

    if not source_id:
        raise ValueError("source_id cannot be empty")

    if not title:
        title = "Unknown Title"

    return {
        "source_id": source_id,
        "title": title,
        "url": str(evidence.get("url", "")),
        "retriever_module": str(
            evidence.get(
                "retriever_module",
                evidence.get("provider", "unknown"),
            )
        ),
        "retrieved_at": str(
            evidence.get(
                "retrieved_at",
                "N/A",
            )
        ),
    }


def adapt_evidence_to_references(
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(evidence, list):
        raise TypeError("Evidence must be a list.")

    return [
        adapt_evidence_item_to_reference(item)
        for item in evidence
    ]

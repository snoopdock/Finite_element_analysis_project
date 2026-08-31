#!/usr/bin/env python3
"""Deterministic diversity controls for evidence selection."""

from __future__ import annotations

from typing import Dict, List, Sequence


def _labels(item: Dict) -> List[str]:
    labels = []
    for key in ("source_type", "provider"):
        value = item.get(key)
        if value:
            labels.append(str(value))
    for key in ("source_types", "provider_names"):
        value = item.get(key, [])
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            labels.extend(str(entry) for entry in value if entry)
    return sorted(set(labels))


def select_diverse(items: Sequence[Dict], top_k: int, min_distinct_labels: int = 2) -> List[Dict]:
    """Select high-ranked evidence while preserving distinct provenance labels.

    Ranking remains the primary criterion. Diversity only changes selection when
    another candidate is close enough to the current cutoff to add a distinct
    provider/source perspective.
    """
    ranked = [item for item in items if isinstance(item, dict)]
    ranked = ranked[: max(0, int(top_k))]
    if len(ranked) <= 1:
        return ranked

    desired = max(1, int(min_distinct_labels))
    chosen: List[Dict] = []
    used = set()

    for item in ranked:
        labels = _labels(item)
        candidate_label = next((label for label in labels if label not in used), None)
        if candidate_label is not None or len(used) >= desired:
            chosen.append(item)
            used.update(labels)
        elif len(chosen) < desired:
            chosen.append(item)
            used.update(labels)

    if len(chosen) < len(ranked):
        for item in ranked:
            if item in chosen:
                continue
            chosen.append(item)

    return chosen[: max(0, int(top_k))]

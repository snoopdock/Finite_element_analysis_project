#!/usr/bin/env python3
"""Deterministic diversity selection for evidence candidates."""

from __future__ import annotations

from typing import Dict, Iterable, List, Set


def _values(item: Dict, key: str) -> Set[str]:
    value = item.get(key, [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return set()
    return {str(entry).strip() for entry in value if str(entry).strip()}


def select_diverse_evidence(
    ranked_items: Iterable[Dict],
    *,
    max_items: int = 4,
    max_per_provider: int = 2,
    max_per_source_type: int = 3,
) -> List[Dict]:
    """Select high-ranked candidates while limiting provider/type concentration."""
    candidates = [item for item in ranked_items or [] if isinstance(item, dict)]
    limit = max(0, int(max_items))
    if limit == 0:
        return []

    selected: List[Dict] = []
    provider_counts: Dict[str, int] = {}
    source_type_counts: Dict[str, int] = {}

    for item in candidates:
        if len(selected) >= limit:
            break

        providers = _values(item, "provider_names") or _values(item, "provider")
        source_types = _values(item, "source_types") or _values(item, "source_type")

        provider_blocked = bool(
            providers
            and all(provider_counts.get(provider, 0) >= max_per_provider for provider in providers)
        )
        type_blocked = bool(
            source_types
            and all(source_type_counts.get(source_type, 0) >= max_per_source_type for source_type in source_types)
        )

        if provider_blocked and type_blocked:
            continue

        selected.append(dict(item))
        for provider in providers:
            provider_counts[provider] = provider_counts.get(provider, 0) + 1
        for source_type in source_types:
            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1

    return selected

#!/usr/bin/env python3
"""Conservative evidence-independence and aggregation helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List


DEPENDENCY_FIELDS = (
    "source_id",
    "asserts_source_ids",
    "derived_from_source_ids",
    "cites_source_ids",
)


def source_dependencies(record: Dict[str, Any]) -> set[str]:
    """Return source IDs explicitly identified as dependencies of a record."""
    dependencies: set[str] = set()
    if not isinstance(record, dict):
        return dependencies
    source_id = str(record.get("source_id") or "").strip()
    if source_id:
        dependencies.add(source_id)
    for field in DEPENDENCY_FIELDS[1:]:
        values = record.get(field, [])
        if isinstance(values, str):
            values = [values]
        if isinstance(values, Iterable):
            for value in values:
                text = str(value).strip()
                if text:
                    dependencies.add(text)
    return dependencies


def independent_source_groups(records: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Group records that share explicit source/dependency provenance."""
    groups: List[List[Dict[str, Any]]] = []
    used: set[int] = set()
    dependencies = [source_dependencies(record) for record in records]

    for index, record in enumerate(records):
        if index in used:
            continue
        group = [record]
        used.add(index)
        group_sources = set(dependencies[index])
        changed = True
        while changed:
            changed = False
            for other, other_sources in enumerate(dependencies):
                if other in used:
                    continue
                if group_sources & other_sources:
                    used.add(other)
                    group.append(records[other])
                    group_sources.update(other_sources)
                    changed = True
        groups.append(group)
    return groups


def independent_source_count(records: List[Dict[str, Any]]) -> int:
    """Count provenance-separated groups, not citation count."""
    return len(independent_source_groups(records))


def relation_aggregation_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize support/challenge without converting counts into truth."""
    by_relation: Dict[str, int] = defaultdict(int)
    for record in records or []:
        if not isinstance(record, dict):
            continue
        relation = str(record.get("relationship") or "unknown").strip().lower()
        by_relation[relation] += 1
    return {
        "relation_counts": dict(sorted(by_relation.items())),
        "record_count": sum(by_relation.values()),
        "independent_source_count": independent_source_count(records),
        "scientific_consensus_inferred": False,
    }

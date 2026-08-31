#!/usr/bin/env python3
"""Deterministic branch views over explicit concept hierarchy edges."""

from __future__ import annotations

from typing import Any, Dict, List


def concept_branches(graph: Dict[str, Any], root_id: str | None = None) -> Dict[str, Any]:
    """Build a read-only hierarchy view from authoritative parent links.

    No parent/child relationship is inferred here. Cycles are surfaced rather
    than silently traversed forever.
    """
    concepts = graph.get("concepts", {}) if isinstance(graph, dict) else {}
    if not isinstance(concepts, dict):
        return {"roots": [], "nodes": {}, "cycles": []}

    children: Dict[str, List[str]] = {str(cid): [] for cid in concepts}
    missing: List[str] = []
    for concept_id, concept in concepts.items():
        if not isinstance(concept, dict):
            continue
        for parent_id in concept.get("parent_concept_ids", []) or []:
            parent_id = str(parent_id)
            if parent_id not in concepts:
                missing.append(f"{concept_id}->{parent_id}")
                continue
            children[parent_id].append(str(concept_id))

    for child_list in children.values():
        child_list.sort()

    roots = [cid for cid in concepts if not concepts[cid].get("parent_concept_ids")]
    roots.sort()
    if root_id is not None:
        root_id = str(root_id)
        roots = [root_id] if root_id in concepts else []

    nodes: Dict[str, Dict[str, Any]] = {}
    cycles: List[List[str]] = []

    def visit(cid: str, path: List[str], depth: int) -> None:
        if cid in path:
            start = path.index(cid)
            cycles.append(path[start:] + [cid])
            return
        if cid in nodes and nodes[cid].get("depth", depth) <= depth:
            return
        concept = concepts[cid]
        nodes[cid] = {
            "concept_id": cid,
            "name": concept.get("name", ""),
            "type": concept.get("type", "concept"),
            "depth": depth,
            "children": list(children.get(cid, [])),
        }
        for child in children.get(cid, []):
            visit(child, path + [cid], depth + 1)

    for root in roots:
        visit(root, [], 0)

    return {
        "roots": roots,
        "nodes": nodes,
        "cycles": cycles,
        "missing_parent_references": sorted(set(missing)),
    }

#!/usr/bin/env python3
"""Conservative bridge from the legacy knowledge base to the concept graph."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from core.knowledge_graph import new_graph_id, normalize_concept, normalize_proposition


def _norm_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _source_signature(source_ids: List[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in source_ids if value}))


def _find_concept(graph: Dict[str, Dict], name: str, concept_type: str) -> str | None:
    needle = _norm_name(name)
    for concept_id, concept in graph.items():
        if not isinstance(concept, dict):
            continue
        if _norm_name(concept.get("name")) == needle and concept.get("type") == concept_type:
            return str(concept_id)
    return None


def _ensure_concept(
    graph: Dict[str, Dict],
    history: List[Dict[str, Any]],
    name: str,
    concept_type: str,
    source_ids: List[str],
) -> str:
    existing = _find_concept(graph, name, concept_type)
    if existing:
        concept = graph[existing]
        before = set(concept.get("source_ids", []))
        after = before | set(source_ids)
        if after != before:
            concept["source_ids"] = sorted(after)
            history.append({
                "event": "provenance_extended",
                "concept_id": existing,
                "source_ids_added": sorted(after - before),
            })
        return existing

    concept = normalize_concept({
        "concept_id": new_graph_id(),
        "name": str(name).strip(),
        "type": concept_type,
        "source_ids": source_ids,
        "status": "active",
    })
    graph[concept["concept_id"]] = concept
    history.append({
        "event": "concept_discovered",
        "concept_id": concept["concept_id"],
        "name": concept["name"],
        "type": concept["type"],
        "source_ids": list(concept.get("source_ids", [])),
    })
    return concept["concept_id"]


def _find_proposition(
    propositions: Dict[str, Dict],
    statement: str,
    source_ids: List[str],
    proposition_type: str,
) -> str | None:
    signature = _source_signature(source_ids)
    for proposition_id, proposition in propositions.items():
        if not isinstance(proposition, dict):
            continue
        if _norm_name(proposition.get("statement")) != _norm_name(statement):
            continue
        if str(proposition.get("knowledge_item_type", "")) != proposition_type:
            continue
        if _source_signature(proposition.get("source_ids", [])) == signature:
            return str(proposition_id)
    return None


def sync_legacy_knowledge_base(state: Dict[str, Any]) -> Dict[str, Any]:
    """Add graph records for legacy KB items without deleting or rewriting the KB."""
    graph = state.get("knowledge_graph", {})
    if not isinstance(graph, dict):
        graph = {}

    concepts = graph.get("concepts", {})
    propositions = graph.get("propositions", {})
    history = graph.get("concept_history", [])
    if not isinstance(concepts, dict):
        concepts = {}
    if not isinstance(propositions, dict):
        propositions = {}
    if not isinstance(history, list):
        history = []

    kb = state.get("knowledge_base", {})
    if not isinstance(kb, dict):
        state["knowledge_graph"] = graph
        return state

    for item in kb.get("concepts", []) if isinstance(kb.get("concepts", []), list) else []:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            continue
        concept_id = _ensure_concept(
            concepts,
            history,
            str(item.get("name")),
            "concept",
            [str(value) for value in item.get("source_ids", []) if value],
        )
        item["concept_id"] = concept_id

    for category, proposition_type in (("equations", "equation"), ("rules", "rule"), ("procedures", "procedure")):
        records = kb.get(category, [])
        if not isinstance(records, list):
            continue

        for item in records:
            if not isinstance(item, dict):
                continue

            statement = (
                item.get("rule") or item.get("name") or item.get("title") or item.get("description") or ""
            )
            statement = str(statement).strip()
            if not statement:
                continue

            source_ids = [str(value) for value in item.get("source_ids", []) if value]
            existing_id = _find_proposition(
                propositions,
                statement,
                source_ids,
                proposition_type,
            )

            proposition = {
                "proposition_id": existing_id or new_graph_id(),
                "statement": statement,
                "concept_ids": [],
                "source_ids": source_ids,
                "provenance_kind": "legacy_knowledge_base",
                "knowledge_item_type": proposition_type,
                "status": "proposed",
            }
            normalize_proposition(proposition)
            propositions[proposition["proposition_id"]] = proposition
            item["proposition_id"] = proposition["proposition_id"]

    graph["concepts"] = concepts
    graph["propositions"] = propositions
    graph["relationships"] = graph.get("relationships", {}) if isinstance(graph.get("relationships", {}), dict) else {}
    graph["concept_history"] = history
    state["knowledge_graph"] = graph
    return state

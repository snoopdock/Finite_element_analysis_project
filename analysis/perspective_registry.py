#!/usr/bin/env python3
"""Persist bounded scientific perspective comparisons in the knowledge graph."""

from __future__ import annotations

from typing import Any, Dict, List

from analysis.perspective_analyzer import compare_propositions
from analysis.scientific_context import extract_context
from core.graph_repository import upsert_proposition, upsert_relationship


_RELATIONSHIP_MAP = {
    "complementary": "complements",
    "alternative": "alternative_to",
    "different_framework": "contrasts_with",
    "appears_to_contradict": "appears_to_contradict",
    "contradicts_under_same_assumptions": "contradicts_under_same_assumptions",
    "conditionally_supported": "conditional_on",
    "supported": "related_to",
    "insufficient_evidence": "related_to",
}


def _source_proposition(source_report: Dict, fallback_claim: str) -> Dict[str, Any]:
    reason = str(source_report.get("reason", "")).strip()
    passages = [
        str(value).strip()
        for value in source_report.get("passages", [])
        if str(value).strip()
    ]
    return {
        "statement": reason or fallback_claim,
        "context": {
            "source_id": source_report.get("source_id"),
            "passages": passages,
        },
        "source_ids": [str(source_report.get("source_id"))]
        if source_report.get("source_id")
        else [],
    }


def record_perspective_jobs(
    state: Dict[str, Any],
    jobs: List[Dict],
    provider,
    parser,
    *,
    max_jobs: int = 2,
    model: str | None = None,
) -> Dict[str, Any]:
    """Analyze and persist a bounded number of source-perspective relationships."""
    graph = state.setdefault("knowledge_graph", {
        "concepts": {},
        "propositions": {},
        "relationships": {},
        "concept_history": [],
    })
    if not isinstance(graph, dict):
        return {"jobs_checked": 0, "relationships_added": 0, "reports": []}

    reports = []
    relationships_added = 0

    for job in (jobs or [])[: max(0, int(max_jobs))]:
        if not isinstance(job, dict) or provider.budget_exhausted():
            break

        source_reports = [
            item for item in job.get("source_reports", [])
            if isinstance(item, dict) and item.get("source_id")
        ]
        if len(source_reports) < 2:
            reports.append({
                "section_id": job.get("section_id"),
                "status": "insufficient_perspectives",
                "reason": "Fewer than two source perspectives were available.",
            })
            continue

        # Compare only distinct sources. Their verifier reasons summarize the
        # source-specific interpretation already grounded in source passages.
        first = _source_proposition(source_reports[0], job.get("claim", ""))
        second = _source_proposition(source_reports[1], job.get("claim", ""))

        context_a = extract_context(
            first["statement"],
            first["context"]["passages"],
            provider,
            parser,
            model=model,
            max_tokens=450,
        )
        if context_a.get("skipped") and provider.budget_exhausted():
            break
        context_b = extract_context(
            second["statement"],
            second["context"]["passages"],
            provider,
            parser,
            model=model,
            max_tokens=450,
        )

        first["context"] = context_a.get("context", {})
        second["context"] = context_b.get("context", {})

        comparison = compare_propositions(
            first,
            second,
            provider,
            parser,
            model=model,
            max_tokens=600,
        )
        result = comparison.get("comparison", {})

        first_id = upsert_proposition(graph, {
            "statement": first["statement"],
            "concept_ids": [],
            "source_ids": first["source_ids"],
            "framework": first["context"].get("framework", ""),
            "assumptions": first["context"].get("assumptions", []),
            "conditions": first["context"].get("conditions", []),
            "domain_of_validity": first["context"].get("domain_of_validity", []),
            "method": first["context"].get("method", ""),
            "approximation": first["context"].get("approximation", []),
            "status": "proposed",
        })
        second_id = upsert_proposition(graph, {
            "statement": second["statement"],
            "concept_ids": [],
            "source_ids": second["source_ids"],
            "framework": second["context"].get("framework", ""),
            "assumptions": second["context"].get("assumptions", []),
            "conditions": second["context"].get("conditions", []),
            "domain_of_validity": second["context"].get("domain_of_validity", []),
            "method": second["context"].get("method", ""),
            "approximation": second["context"].get("approximation", []),
            "status": "proposed",
        })

        relationship_type = _RELATIONSHIP_MAP.get(
            result.get("relationship"),
            "related_to",
        )
        relation_id = upsert_relationship(
            graph,
            source_id=first_id,
            target_id=second_id,
            relation_type=relationship_type,
            source_ids=first["source_ids"] + second["source_ids"],
            confidence=float(result.get("confidence", 0.0)),
            framework="; ".join(filter(None, [
                first["context"].get("framework", ""),
                second["context"].get("framework", ""),
            ])),
            assumptions=list(dict.fromkeys(
                first["context"].get("assumptions", [])
                + second["context"].get("assumptions", [])
            )),
            conditions=list(dict.fromkeys(
                first["context"].get("conditions", [])
                + second["context"].get("conditions", [])
            )),
            reason=str(result.get("reason", "")),
        )

        if relation_id:
            relationships_added += 1

        reports.append({
            "section_id": job.get("section_id"),
            "proposition_ids": [first_id, second_id],
            "relationship_id": relation_id,
            "comparison": result,
        })

    state["knowledge_graph"] = graph
    return {
        "jobs_checked": len(reports),
        "relationships_added": relationships_added,
        "reports": reports,
    }

#!/usr/bin/env python3
"""Map existing scientific context into proposed validity scopes."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List


def validity_id(proposition_id: str, context: Dict[str, Any]) -> str:
    payload = "|".join([
        str(proposition_id).strip(),
        str(context.get("framework") or "").strip(),
        str(context.get("domain_of_validity") or context.get("domain") or "").strip(),
        str(context.get("regime") or "").strip(),
        "|".join(sorted(str(v).strip() for v in (context.get("conditions") or []) if str(v).strip())),
        "|".join(sorted(str(v).strip() for v in (context.get("assumptions") or []) if str(v).strip())),
    ])
    return "validity-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def propose_validity_scope(proposition: Dict[str, Any]) -> Dict[str, Any] | None:
    """Create a non-assertive validity proposal from an existing proposition context."""
    if not isinstance(proposition, dict):
        return None
    proposition_id = str(proposition.get("proposition_id") or "").strip()
    if not proposition_id:
        return None

    context = proposition.get("context", {})
    if not isinstance(context, dict):
        context = {}

    conditions = list(context.get("conditions", proposition.get("conditions", [])) or [])
    assumptions = list(context.get("assumptions", proposition.get("assumptions", [])) or [])
    domain = context.get("domain_of_validity", proposition.get("domain_of_validity"))
    framework = context.get("framework", proposition.get("framework"))
    regime = context.get("regime", proposition.get("regime"))
    approximation = context.get("approximation", proposition.get("approximation"))
    limitations = list(context.get("limitations", proposition.get("limitations", [])) or [])
    exceptions = list(context.get("exceptions", proposition.get("exceptions", [])) or [])

    has_scope = any([
        framework,
        domain,
        regime,
        conditions,
        assumptions,
        approximation,
        limitations,
        exceptions,
    ])
    if not has_scope:
        return None

    scope_type = "conditional" if conditions or assumptions else "unknown"
    context_for_id = {
        "framework": framework,
        "domain_of_validity": domain,
        "regime": regime,
        "conditions": conditions,
        "assumptions": assumptions,
    }
    return {
        "validity_id": validity_id(proposition_id, context_for_id),
        "proposition_id": proposition_id,
        "type": scope_type,
        "framework": framework,
        "domain_of_validity": domain,
        "regime": regime,
        "conditions": conditions,
        "assumptions": assumptions,
        "limitations": limitations,
        "exceptions": exceptions,
        "approximation": approximation,
        "evidence_relation_ids": list(proposition.get("evidence_relation_ids", []) or []),
        "status": "proposed",
    }


def propose_validity_scopes(propositions: List[Dict[str, Any]], max_items: int = 32) -> List[Dict[str, Any]]:
    scopes = []
    seen = set()
    for proposition in propositions or []:
        if len(scopes) >= max(0, int(max_items)):
            break
        scope = propose_validity_scope(proposition)
        if not scope or scope["validity_id"] in seen:
            continue
        seen.add(scope["validity_id"])
        scopes.append(scope)
    return scopes

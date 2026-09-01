#!/usr/bin/env python3
"""Structured, interpretable signatures for scientific perspectives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class PerspectiveSignature:
    signature_id: str
    framework: str | None = None
    assumptions: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    domain: str | None = None
    objectives: List[str] = field(default_factory=list)
    claims: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    proposition_ids: List[str] = field(default_factory=list)
    source_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature_id": self.signature_id,
            "framework": self.framework,
            "assumptions": list(self.assumptions),
            "methods": list(self.methods),
            "domain": self.domain,
            "objectives": list(self.objectives),
            "claims": list(self.claims),
            "limitations": list(self.limitations),
            "proposition_ids": list(self.proposition_ids),
            "source_ids": list(self.source_ids),
        }


def _clean(values: Any) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def signature_id_from_payload(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "perspective-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def signature_from_propositions(
    propositions: List[Dict[str, Any]],
    *,
    framework: str | None = None,
    domain: str | None = None,
) -> Dict[str, Any] | None:
    """Build an interpretable signature from existing source-backed propositions."""
    items = [item for item in propositions or [] if isinstance(item, dict)]
    if not items:
        return None

    frameworks = _clean([framework] if framework else [item.get("framework") for item in items])
    domains = _clean([domain] if domain else [item.get("domain_of_validity") for item in items])
    assumptions = _clean(value for item in items for value in item.get("assumptions", []) or [])
    methods = _clean([item.get("method") for item in items] + [value for item in items for value in item.get("methods", []) or []])
    limitations = _clean(value for item in items for value in item.get("limitations", []) or [])
    claims = _clean([item.get("statement") or item.get("claim") for item in items])
    proposition_ids = _clean(item.get("proposition_id") for item in items)
    source_ids = _clean(value for item in items for value in item.get("source_ids", []) or [])

    payload = {
        "framework": frameworks[0] if len(frameworks) == 1 else frameworks,
        "assumptions": sorted(assumptions),
        "methods": sorted(methods),
        "domain": domains[0] if len(domains) == 1 else domains,
        "claims": sorted(claims),
    }
    signature = PerspectiveSignature(
        signature_id=signature_id_from_payload(payload),
        framework=frameworks[0] if len(frameworks) == 1 else None,
        assumptions=assumptions,
        methods=methods,
        domain=domains[0] if len(domains) == 1 else None,
        claims=claims,
        limitations=limitations,
        proposition_ids=proposition_ids,
        source_ids=source_ids,
    )
    return signature.to_dict()

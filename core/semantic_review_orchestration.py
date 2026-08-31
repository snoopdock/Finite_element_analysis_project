#!/usr/bin/env python3
"""Compatibility helper for bounded semantic document review."""

from __future__ import annotations

from typing import Dict, List

from analysis.document_semantic_review import review_document_claims
from utils.text import load_json


def review_written_sections(
    sections: List[Dict],
    evidence_path,
    provider,
    parser,
    config: Dict,
) -> Dict:
    """Run optional bounded semantic review without changing the writer."""
    semantic_config = config.get("semantic_verification", {})
    max_claims = int(semantic_config.get("max_claims_per_cycle", 0))

    if not semantic_config.get("enabled", False) or max_claims <= 0:
        return {
            "enabled": False,
            "claims_checked": 0,
            "claims_supported": 0,
            "claims_contradicted": 0,
            "claims_insufficient": 0,
            "verification_skipped": True,
            "reports": [],
        }

    evidence = load_json(evidence_path, [])
    if not isinstance(evidence, list):
        evidence = []

    return review_document_claims(
        sections,
        evidence,
        provider,
        parser,
        max_claims=max_claims,
        max_sources_per_claim=int(
            semantic_config.get("max_sources_per_claim", 2)
        ),
        max_passages_per_source=int(
            semantic_config.get("max_passages_per_source", 2)
        ),
        max_passage_chars=int(
            semantic_config.get("max_passage_chars", 1800)
        ),
        max_tokens=int(
            semantic_config.get("max_tokens_per_claim", 700)
        ),
        model=semantic_config.get("model"),
    )

#!/usr/bin/env python3
"""Optional runner for bounded semantic concept-relationship analysis.

This module intentionally does not alter the main pipeline. Callers provide
already-loaded state, provider, parser, and configuration. When disabled, the
runner is a no-op.
"""

from __future__ import annotations

from typing import Any, Dict

from analysis.concept_relationship_service import analyze_candidate_concepts


def _enabled(config: Dict[str, Any]) -> bool:
    semantic = config.get("semantic_verification", {}) if isinstance(config, dict) else {}
    return bool(isinstance(semantic, dict) and semantic.get("concept_relationship_enabled", False))


def run_concept_relationship_analysis(
    state: Dict[str, Any],
    provider,
    parser,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Run bounded concept relationship analysis only when explicitly enabled."""
    if not _enabled(config):
        result = {"enabled": False, "candidates": 0, "analyzed": 0, "skipped": 0, "records": []}
        if isinstance(state, dict):
            state["last_concept_relationship_analysis"] = result.copy()
        return result

    semantic = config.get("semantic_verification", {})
    max_pairs = int(semantic.get("max_concept_relationship_pairs_per_cycle", 2))
    max_propositions = int(semantic.get("max_concept_relationship_propositions_per_pair", 8))
    max_records = int(semantic.get("concept_relationship_max_records", 200))
    model = semantic.get("concept_relationship_model")
    max_tokens = int(semantic.get("concept_relationship_max_tokens", 650))

    result = analyze_candidate_concepts(
        state,
        provider,
        parser,
        max_pairs=max(0, max_pairs),
        max_propositions_per_pair=max(0, max_propositions),
        model=model,
        max_tokens=max(1, max_tokens),
        max_records=max(0, max_records),
    )
    result["enabled"] = True
    if isinstance(state, dict):
        state["last_concept_relationship_analysis"] = {
            key: value for key, value in result.items() if key != "records"
        }
    return result

#!/usr/bin/env python3
"""Small orchestration boundary for optional concept-relationship analysis.

The runner keeps Stage 7 autonomous analysis isolated from the main pipeline.
It performs no work when the feature is disabled and never promotes proposals.
"""

from __future__ import annotations

from typing import Any, Dict

from analysis.run_concept_relationship_analysis import run_concept_relationship_analysis


def run_stage7_relationship_cycle(
    state: Dict[str, Any],
    provider,
    parser,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Run one bounded Stage 7 relationship-analysis cycle."""
    result = run_concept_relationship_analysis(state, provider, parser, config)
    if isinstance(state, dict):
        state["last_stage7_relationship_cycle"] = {
            key: value for key, value in result.items() if key != "records"
        }
    return result

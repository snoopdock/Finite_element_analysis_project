"""Application-facing boundary for the R8 research-planning flow.

This module is deliberately thin. It accepts already-produced
AttentionProposal records and delegates composition to the R8.9.1 runtime
coordinator. It does not execute retrieval, persist requests, create receipts,
or mutate scientific or lifecycle state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from core.research_planning_runtime import compose_research_acquisition_flow


def prepare_research_acquisition_flow(
    attention_proposals: Iterable[Mapping[str, Any]],
    *,
    planning_context: Mapping[str, Any] | None = None,
    operational_constraints: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Prepare planning outputs for application consumption.

    The application boundary owns only invocation and return-shape continuity.
    All semantic translation, planning evaluation, and request formulation
    remain owned by their established authorities.
    """
    return compose_research_acquisition_flow(
        attention_proposals,
        planning_context=planning_context,
        operational_constraints=operational_constraints,
    )


__all__ = ["prepare_research_acquisition_flow"]

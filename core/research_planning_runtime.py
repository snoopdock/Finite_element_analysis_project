"""R8.9.1 runtime orchestration for research-planning acquisition flow.

This module composes existing semantic authorities. It does not define planning
or acquisition semantics and does not execute retrieval.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from analysis.acquisition_request_formulation import formulate_acquisition_request
from analysis.retrieval_attention_planning_signal import (
    AttentionProposal,
    ResearchPlanningSignal,
    translate_attention_proposal,
)
from analysis.research_planning_decision import (
    ResearchPlanningDecision,
    evaluate_research_planning_signal,
)


def compose_research_acquisition_flow(
    proposals: Iterable[AttentionProposal | Mapping[str, Any]],
    *,
    operational_constraints: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compose the R8 planning boundaries independently for each proposal.

    The returned records preserve the provenance chain and contain the
    resulting planning decision plus an optional acquisition request. A
    decision that does not formulate an acquisition request produces no request
    field. Operational exceptions are allowed to propagate; they are not
    converted into planning decisions.
    """

    results: list[dict[str, Any]] = []
    for proposal in proposals:
        signal = translate_attention_proposal(proposal)
        decision = evaluate_research_planning_signal(signal)
        result: dict[str, Any] = {
            "attention_proposal": proposal,
            "research_planning_signal": signal,
            "research_planning_decision": decision,
        }
        if _decision_type(decision) == "formulate_acquisition_request":
            result["acquisition_request"] = formulate_acquisition_request(
                decision,
                operational_constraints=operational_constraints,
            )
        results.append(result)
    return results


def _decision_type(decision: ResearchPlanningDecision | Mapping[str, Any]) -> str:
    if isinstance(decision, Mapping):
        value = decision.get("decision_type")
    else:
        value = getattr(decision, "decision_type", None)
    return str(value).lower().replace("-", "_")


__all__ = ["compose_research_acquisition_flow"]

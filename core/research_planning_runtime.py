"""R8.9.1 runtime orchestration for research-planning acquisition flow.

This module composes existing semantic authorities. It does not define planning
or acquisition semantics and does not execute retrieval.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from analysis.acquisition_request_formulation import formulate_acquisition_request
from analysis.retrieval_attention_planning_signal import translate_attention_proposal
from analysis.research_planning_decision import evaluate_research_planning_signal


def compose_research_acquisition_flow(
    proposals: Iterable[Mapping[str, Any]],
    *,
    planning_context: Mapping[str, Any] | None = None,
    operational_constraints: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compose the R8 planning boundaries independently for each proposal.

    ``planning_context`` is passed unchanged to the established R8.3 evaluator;
    it is not interpreted by this coordinator. ``operational_constraints`` is
    passed unchanged to the established R8.8 formulator when a request is
    actually warranted.

    The returned records preserve the provenance chain and contain the
    resulting planning decision plus an optional acquisition request. A
    decision that does not formulate an acquisition request produces no request
    field. Operational exceptions are allowed to propagate; they are not
    converted into planning decisions.
    """

    results: list[dict[str, Any]] = []
    for proposal in proposals:
        signal = translate_attention_proposal(proposal)
        decision = evaluate_research_planning_signal(
            signal,
            planning_context=planning_context,
        )
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


def _decision_type(decision: Mapping[str, Any]) -> str:
    value = decision.get("decision_type")
    return str(value).lower().replace("-", "_")


__all__ = ["compose_research_acquisition_flow"]

#!/usr/bin/env python3
"""Read-only synthetic audit for the R8.4 planning decision evaluator."""

from __future__ import annotations

from copy import deepcopy

from analysis.research_planning_decision import (
    evaluate_research_planning_signal,
    validate_research_planning_decision,
)


def _signal(condition: str = "provider_unavailable", signal_id: str = "RPS1") -> dict:
    provider_limited = condition in {
        "provider_unavailable",
        "provider_partially_available",
        "repeated_query_provider_non_success",
    }
    return {
        "research_planning_signal_id": signal_id,
        "source_attention_id": "A1",
        "schema_version": 1,
        "signal_type": "acquisition_constraint",
        "target": {
            "query_scope": "weak_form_galerkin_fem",
            "provider": "semantic_scholar",
        },
        "operational_condition": {"observed_condition": condition},
        "acquisition_constraint": {
            "provider_access_limitation": provider_limited,
            "provider": "semantic_scholar",
            "query_scope": "weak_form_galerkin_fem",
        },
        "provenance": {"supporting_event_ids": ["E1", "E2"]},
        "translation_policy_version": "r8.2-v1",
    }


def _check_provider_failure() -> None:
    decision = evaluate_research_planning_signal(_signal())
    assert decision["decision_type"] == "prioritize_research"
    assert decision["input_signal_ids"] == ["RPS1"]
    assert 0.0 <= decision["priority"] <= 1.0


def _check_alternative_provider() -> None:
    decision = evaluate_research_planning_signal(
        _signal(), planning_context={"alternative_providers": ["crossref"]}
    )
    assert decision["decision_type"] == "formulate_acquisition_request"


def _check_empty_result_is_not_evidence_gap() -> None:
    decision = evaluate_research_planning_signal(
        _signal("query_returned_empty_result")
    )
    assert decision["decision_type"] == "no_action"
    assert "evidence_gap" not in decision
    assert "confidence" not in decision


def _check_explicit_defer() -> None:
    decision = evaluate_research_planning_signal(
        _signal(), planning_context={"deferred_signal_ids": ["RPS1"]}
    )
    assert decision["decision_type"] == "defer"


def _check_scope_defer() -> None:
    decision = evaluate_research_planning_signal(
        _signal(), planning_context={"active_query_scopes": ["other_scope"]}
    )
    assert decision["decision_type"] == "defer"


def _check_determinism() -> None:
    first = evaluate_research_planning_signal(_signal())
    second = evaluate_research_planning_signal(_signal())
    assert first == second


def _check_input_immutability() -> None:
    source = _signal()
    before = deepcopy(source)
    evaluate_research_planning_signal(
        source, planning_context={"alternative_providers": ["crossref"]}
    )
    assert source == before


def _check_scientific_isolation() -> None:
    decision = evaluate_research_planning_signal(_signal())
    forbidden = {
        "evidence_strength",
        "evidence_gap",
        "confidence",
        "truth_status",
        "epistemic_status",
        "claim_rank",
        "convergence_score",
        "scientific_priority",
    }
    assert forbidden.isdisjoint(decision)
    assert "lifecycle_status" not in decision
    assert "lifecycle_event_id" not in decision


def _check_validation() -> None:
    decision = evaluate_research_planning_signal(_signal())
    assert validate_research_planning_decision(decision) == decision


def _check_invalid_context() -> None:
    try:
        evaluate_research_planning_signal(
            _signal(), planning_context={"scientific_priority": 0.9}
        )
    except ValueError:
        return
    raise AssertionError("scientific planning context field was accepted")


def main() -> int:
    checks = [
        _check_provider_failure,
        _check_alternative_provider,
        _check_empty_result_is_not_evidence_gap,
        _check_explicit_defer,
        _check_scope_defer,
        _check_determinism,
        _check_input_immutability,
        _check_scientific_isolation,
        _check_validation,
        _check_invalid_context,
    ]

    for check in checks:
        check()

    print(f"R8.4 research planning audit: PASS ({len(checks)}/{len(checks)} checks passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

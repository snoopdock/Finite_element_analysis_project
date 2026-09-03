from copy import deepcopy

import pytest

from analysis.research_planning_decision import (
    PLANNER_VERSION,
    evaluate_research_planning_signal,
    evaluate_research_planning_signals,
    validate_research_planning_decision,
)


def signal(condition="provider_unavailable", signal_id="RPS1"):
    return {
        "research_planning_signal_id": signal_id,
        "source_attention_id": "A1",
        "schema_version": 1,
        "signal_type": "acquisition_constraint",
        "target": {"query_scope": "weak_form_galerkin_fem", "provider": "semantic_scholar"},
        "operational_condition": {"observed_condition": condition},
        "acquisition_constraint": {
            "provider_access_limitation": condition not in {
                "query_returned_empty_result",
                "repeated_query_provider_empty_result",
            },
            "provider": "semantic_scholar",
            "query_scope": "weak_form_galerkin_fem",
        },
        "provenance": {"supporting_event_ids": ["E1"]},
        "translation_policy_version": "r8.2-v1",
    }


def test_provider_failure_without_alternative_prioritizes_process():
    decision = evaluate_research_planning_signal(signal())
    assert decision["decision_type"] == "prioritize_research"
    assert 0.0 <= decision["priority"] <= 1.0
    assert decision["input_signal_ids"] == ["RPS1"]


def test_provider_failure_with_alternative_formulates_request():
    decision = evaluate_research_planning_signal(
        signal(),
        planning_context={"alternative_providers": ["crossref"]},
    )
    assert decision["decision_type"] == "formulate_acquisition_request"
    assert "alternative provider" in decision["rationale"]


def test_partial_provider_availability_prioritizes_without_scientific_claim():
    decision = evaluate_research_planning_signal(signal("provider_partially_available"))
    assert decision["decision_type"] == "prioritize_research"
    assert "evidence" not in decision["rationale"].lower()


def test_empty_result_does_not_become_evidence_gap():
    decision = evaluate_research_planning_signal(signal("query_returned_empty_result"))
    assert decision["decision_type"] == "no_action"
    assert "absence" in decision["rationale"].lower()


def test_repeated_empty_result_remains_non_scientific():
    decision = evaluate_research_planning_signal(
        signal("repeated_query_provider_empty_result")
    )
    assert decision["decision_type"] == "no_action"
    assert "evidence_gap" not in decision
    assert "confidence" not in decision


def test_explicit_deferral_wins():
    decision = evaluate_research_planning_signal(
        signal(),
        planning_context={"deferred_signal_ids": ["RPS1"]},
    )
    assert decision["decision_type"] == "defer"


def test_out_of_scope_signal_is_deferred():
    decision = evaluate_research_planning_signal(
        signal(),
        planning_context={"active_query_scopes": ["other_scope"]},
    )
    assert decision["decision_type"] == "defer"


def test_context_unknown_fields_are_rejected():
    with pytest.raises(ValueError, match="unknown planning_context fields"):
        evaluate_research_planning_signal(
            signal(), planning_context={"scientific_priority": 0.9}
        )


def test_decision_id_is_deterministic():
    first = evaluate_research_planning_signal(signal())
    second = evaluate_research_planning_signal(signal())
    assert first["research_planning_decision_id"] == second["research_planning_decision_id"]


def test_decision_id_changes_when_input_changes():
    first = evaluate_research_planning_signal(signal("provider_unavailable", "RPS1"))
    second = evaluate_research_planning_signal(signal("provider_unavailable", "RPS2"))
    assert first["research_planning_decision_id"] != second["research_planning_decision_id"]


def test_planner_does_not_mutate_input():
    original = signal()
    before = deepcopy(original)
    evaluate_research_planning_signal(original, planning_context={"alternative_providers": ["crossref"]})
    assert original == before


def test_batch_order_is_deterministic():
    signals = [signal("provider_unavailable", "RPS2"), signal("provider_unavailable", "RPS1")]
    decisions = evaluate_research_planning_signals(signals)
    assert decisions == sorted(decisions, key=lambda item: item["research_planning_decision_id"])


def test_batch_does_not_modify_signals():
    signals = [signal("provider_unavailable", "RPS1"), signal("provider_partially_available", "RPS2")]
    before = deepcopy(signals)
    evaluate_research_planning_signals(signals)
    assert signals == before


def test_decision_is_not_scientific_attention():
    decision = evaluate_research_planning_signal(signal())
    assert "ScientificAttention" not in decision
    assert "evidence_strength" not in decision
    assert "truth_status" not in decision
    assert "claim_rank" not in decision
    assert "convergence_score" not in decision


def test_decision_does_not_contain_lifecycle_fields():
    decision = evaluate_research_planning_signal(signal())
    assert "lifecycle_status" not in decision
    assert "previous_status" not in decision
    assert "new_status" not in decision
    assert "lifecycle_event_id" not in decision


def test_decision_is_validated_and_uses_planner_version():
    decision = evaluate_research_planning_signal(signal())
    validated = validate_research_planning_decision(decision)
    assert validated == decision
    assert decision["planner_version"] == PLANNER_VERSION


def test_invalid_decision_type_is_rejected():
    with pytest.raises(ValueError, match="unsupported decision_type"):
        validate_research_planning_decision(
            {
                "research_planning_decision_id": "RPD1",
                "decision_type": "reduce_confidence",
                "input_signal_ids": ["RPS1"],
                "rationale": "invalid",
            }
        )


def test_priority_bounds_are_enforced():
    with pytest.raises(ValueError, match="priority must be between"):
        validate_research_planning_decision(
            {
                "research_planning_decision_id": "RPD1",
                "decision_type": "prioritize_research",
                "input_signal_ids": ["RPS1"],
                "rationale": "process-only",
                "priority": 1.1,
            }
        )


def test_acquisition_request_reference_is_not_execution():
    decision = validate_research_planning_decision(
        {
            "research_planning_decision_id": "RPD1",
            "decision_type": "formulate_acquisition_request",
            "input_signal_ids": ["RPS1"],
            "rationale": "A separate acquisition request should be formulated.",
            "acquisition_request_reference": "REQ1",
        }
    )
    assert decision["acquisition_request_reference"] == "REQ1"


def test_scientific_semantic_field_is_rejected_even_nested():
    with pytest.raises(ValueError, match="forbidden scientific semantic field"):
        validate_research_planning_decision(
            {
                "research_planning_decision_id": "RPD1",
                "decision_type": "prioritize_research",
                "input_signal_ids": ["RPS1"],
                "rationale": "process-only",
                "created_at": {"confidence": 0.1},
            }
        )

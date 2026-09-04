from copy import deepcopy

import pytest

from analysis.acquisition_request_formulation import formulate_acquisition_request


def decision(**overrides):
    value = {
        "research_planning_decision_id": "RPD1",
        "decision_type": "formulate_acquisition_request",
        "input_signal_ids": ["RPS1"],
        "rationale": "An alternative acquisition route should be considered.",
        "target": {
            "query_scope": "weak_form_galerkin_fem",
            "provider": "semantic_scholar",
        },
        "priority": 0.8,
    }
    value.update(overrides)
    return value


def test_formulation_creates_valid_request():
    request = formulate_acquisition_request(
        decision(),
        created_at="2026-09-04T10:00:00Z",
    )
    assert request["acquisition_request_id"].startswith("acquisition-request-")
    assert request["schema_version"] == 1
    assert request["created_at"] == "2026-09-04T10:00:00Z"
    assert request["origin"] == {"research_planning_decision_id": "RPD1"}
    assert request["target"] == {"query_scope": "weak_form_galerkin_fem"}
    assert request["constraints"] == {}
    assert request["priority"] == 0.8


def test_only_formulate_decision_is_accepted():
    invalid = decision(decision_type="prioritize_research")
    with pytest.raises(ValueError, match="decision_type=formulate_acquisition_request"):
        formulate_acquisition_request(invalid)


def test_query_scope_is_required_and_not_inferred_from_rationale():
    value = decision(target={"provider": "semantic_scholar"})
    with pytest.raises(ValueError, match="target.query_scope is required"):
        formulate_acquisition_request(value)


def test_provider_target_is_not_inferred_as_provider_preference():
    request = formulate_acquisition_request(decision())
    assert "provider_preferences" not in request["constraints"]
    assert request["target"] == {"query_scope": "weak_form_galerkin_fem"}


def test_explicit_operational_constraints_are_preserved():
    constraints = {
        "provider_preferences": ["semantic_scholar"],
        "provider_access_constraints": {
            "semantic_scholar": "temporarily_unavailable"
        },
        "execution_limits": {"max_attempts": 2},
    }
    request = formulate_acquisition_request(decision(), operational_constraints=constraints)
    assert request["constraints"] == constraints


def test_unknown_operational_constraint_is_rejected():
    with pytest.raises(ValueError, match="unknown operational acquisition constraints"):
        formulate_acquisition_request(
            decision(),
            operational_constraints={"scientific_priority": 0.8},
        )


def test_scientific_constraint_is_rejected_by_request_validation():
    with pytest.raises(ValueError, match="forbidden scientific semantic field"):
        formulate_acquisition_request(
            decision(),
            operational_constraints={"execution_limits": {"confidence": 0.2}},
        )


def test_priority_defaults_to_zero_when_absent():
    value = decision()
    value.pop("priority")
    request = formulate_acquisition_request(value)
    assert request["priority"] == 0.0


def test_formulation_does_not_mutate_decision():
    original = decision()
    before = deepcopy(original)
    formulate_acquisition_request(original)
    assert original == before


def test_each_formulation_gets_new_request_identity():
    first = formulate_acquisition_request(decision())
    second = formulate_acquisition_request(decision())
    assert first["origin"] == second["origin"]
    assert first["acquisition_request_id"] != second["acquisition_request_id"]


def test_formulation_has_no_execution_receipt_or_runtime_fields():
    request = formulate_acquisition_request(decision())
    assert "execution_id" not in request
    assert "execution_status" not in request
    assert "generated_query_inputs" not in request
    assert "translation_losses" not in request

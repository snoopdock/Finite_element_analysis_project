from copy import deepcopy

import pytest

from core.research_planning_runtime import compose_research_acquisition_flow


def proposal(**overrides):
    value = {
        "attention_id": "ATT-1",
        "policy_version": "r7b-v1",
        "query_scope": "weak_form_galerkin_fem",
        "provider": "semantic_scholar",
        "attention_reason": "Repeated operational retrieval issue.",
        "observed_condition": "provider_unavailable",
        "lifecycle_status": "open",
        "supporting_event_ids": ["EV-1"],
        "recommended_acquisition_action": "retry_or_alternative_provider",
    }
    value.update(overrides)
    return value


def test_no_action_decision_stops_before_request_formulation():
    result = compose_research_acquisition_flow(
        [proposal(observed_condition="query_returned_empty_result")]
    )[0]

    assert result["research_planning_decision"]["decision_type"] == "no_action"
    assert "acquisition_request" not in result
    assert result["research_planning_signal"]["source_attention_id"] == "ATT-1"


def test_prioritize_research_decision_stops_before_request_formulation():
    result = compose_research_acquisition_flow([proposal()])[0]

    assert result["research_planning_decision"]["decision_type"] == "prioritize_research"
    assert "acquisition_request" not in result


def test_explicit_alternative_provider_allows_request_formulation():
    result = compose_research_acquisition_flow(
        [proposal()],
        planning_context={"alternative_providers": ["arxiv"]},
        operational_constraints={"execution_limits": {"max_attempts": 2}},
    )[0]

    decision = result["research_planning_decision"]
    request = result["acquisition_request"]

    assert decision["decision_type"] == "formulate_acquisition_request"
    assert request["origin"] == {
        "research_planning_decision_id": decision["research_planning_decision_id"]
    }
    assert request["target"] == {"query_scope": "weak_form_galerkin_fem"}
    assert request["constraints"] == {"execution_limits": {"max_attempts": 2}}


def test_only_formulate_decision_produces_request():
    results = compose_research_acquisition_flow(
        [
            proposal(
                attention_id="ATT-REQUEST",
            ),
            proposal(
                attention_id="ATT-NO-ACTION",
                observed_condition="query_returned_empty_result",
            ),
        ],
        planning_context={"alternative_providers": ["arxiv"]},
    )

    by_attention = {
        item["attention_proposal"]["attention_id"]: item for item in results
    }
    assert "acquisition_request" in by_attention["ATT-REQUEST"]
    assert "acquisition_request" not in by_attention["ATT-NO-ACTION"]


def test_batch_items_are_processed_independently_and_provenance_is_preserved():
    first = proposal(attention_id="ATT-A", supporting_event_ids=["EV-A"])
    second = proposal(
        attention_id="ATT-B",
        observed_condition="query_returned_empty_result",
        supporting_event_ids=["EV-B"],
    )
    original = deepcopy([first, second])

    results = compose_research_acquisition_flow(
        [first, second],
        planning_context={"alternative_providers": ["arxiv"]},
    )

    assert [item["attention_proposal"]["attention_id"] for item in results] == [
        "ATT-A",
        "ATT-B",
    ]
    assert [
        item["research_planning_signal"]["source_attention_id"] for item in results
    ] == ["ATT-A", "ATT-B"]
    assert [
        item["research_planning_signal"]["provenance"]["supporting_event_ids"]
        for item in results
    ] == [["EV-A"], ["EV-B"]]
    assert [
        item["research_planning_decision"]["input_signal_ids"] for item in results
    ] == [
        [results[0]["research_planning_signal"]["research_planning_signal_id"]],
        [results[1]["research_planning_signal"]["research_planning_signal_id"]],
    ]
    assert [first, second] == original


def test_request_identity_is_owned_by_formulation_boundary():
    result = compose_research_acquisition_flow(
        [proposal()],
        planning_context={"alternative_providers": ["arxiv"]},
    )[0]
    request = result["acquisition_request"]

    assert request["acquisition_request_id"].startswith("acquisition-request-")
    assert request["origin"]["research_planning_decision_id"] == result[
        "research_planning_decision"
    ]["research_planning_decision_id"]


def test_operational_translation_failure_propagates():
    with pytest.raises(ValueError, match="unsupported observed_condition"):
        compose_research_acquisition_flow(
            [proposal(observed_condition="invalid-condition")]
        )


def test_operational_planning_failure_propagates():
    with pytest.raises(ValueError, match="ResearchPlanningSignal"):
        compose_research_acquisition_flow(
            [proposal(query_scope="")]
        )


def test_operational_formulation_failure_propagates():
    with pytest.raises(ValueError, match="unknown operational acquisition constraints"):
        compose_research_acquisition_flow(
            [proposal()],
            planning_context={"alternative_providers": ["arxiv"]},
            operational_constraints={"unknown": True},
        )


def test_runtime_does_not_create_receipt_or_execute_retrieval():
    result = compose_research_acquisition_flow(
        [proposal()],
        planning_context={"alternative_providers": ["arxiv"]},
    )[0]

    assert "acquisition_execution_receipt" not in result
    assert "execution_id" not in result
    assert "evidence" not in result
    assert "retrieval_report" not in result

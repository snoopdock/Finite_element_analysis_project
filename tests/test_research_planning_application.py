import pytest

from core.research_planning_application import prepare_research_acquisition_flow


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


def test_application_boundary_delegates_and_preserves_composed_shape():
    result = prepare_research_acquisition_flow(
        [proposal()],
        planning_context={"alternative_providers": ["arxiv"]},
        operational_constraints={"execution_limits": {"max_attempts": 2}},
    )

    assert len(result) == 1
    assert result[0]["attention_proposal"]["attention_id"] == "ATT-1"
    assert result[0]["research_planning_signal"]["source_attention_id"] == "ATT-1"
    assert result[0]["research_planning_decision"]["decision_type"] == (
        "formulate_acquisition_request"
    )
    assert result[0]["acquisition_request"]["target"] == {
        "query_scope": "weak_form_galerkin_fem"
    }


def test_application_boundary_preserves_batch_cardinality_and_order():
    results = prepare_research_acquisition_flow(
        [
            proposal(attention_id="ATT-A"),
            proposal(
                attention_id="ATT-B",
                observed_condition="query_returned_empty_result",
            ),
        ],
        planning_context={"alternative_providers": ["arxiv"]},
    )

    assert len(results) == 2
    assert [item["attention_proposal"]["attention_id"] for item in results] == [
        "ATT-A",
        "ATT-B",
    ]
    assert "acquisition_request" in results[0]
    assert "acquisition_request" not in results[1]


def test_application_boundary_does_not_add_execution_or_scientific_state():
    result = prepare_research_acquisition_flow(
        [proposal()],
        planning_context={"alternative_providers": ["arxiv"]},
    )[0]

    assert "acquisition_execution_receipt" not in result
    assert "execution_id" not in result
    assert "evidence" not in result
    assert "retrieval_report" not in result


def test_application_boundary_propagates_downstream_operational_failures():
    with pytest.raises(ValueError, match="unsupported observed_condition"):
        prepare_research_acquisition_flow(
            [proposal(observed_condition="invalid-condition")]
        )

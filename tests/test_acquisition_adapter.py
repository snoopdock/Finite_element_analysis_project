from copy import deepcopy

import pytest

from analysis.acquisition_adapter import (
    TRANSLATION_POLICY_VERSION,
    execute_acquisition_request,
    project_acquisition_request,
    validate_acquisition_request,
)


def request(**overrides):
    value = {
        "acquisition_request_id": "AR1",
        "schema_version": 1,
        "created_at": "2026-09-03T12:00:00Z",
        "origin": {"research_planning_decision_id": "RPD1"},
        "target": {"query_scope": "weak_form_galerkin_fem"},
        "constraints": {},
        "priority": 0.8,
    }
    value.update(overrides)
    return value


def test_request_validation_accepts_minimal_valid_request():
    validated = validate_acquisition_request(request())
    assert validated["acquisition_request_id"] == "AR1"
    assert validated["priority"] == 0.8


def test_request_validation_rejects_unknown_fields():
    with pytest.raises(ValueError, match="unknown AcquisitionRequest fields"):
        validate_acquisition_request(request(scientific_context="x"))


def test_request_validation_rejects_forbidden_scientific_field_nested():
    with pytest.raises(ValueError, match="forbidden scientific semantic field"):
        validate_acquisition_request(
            request(notes={"metadata": {"confidence": 0.1}})
        )


def test_request_validation_rejects_scientific_target_fields():
    with pytest.raises(ValueError, match="forbidden scientific semantic field"):
        validate_acquisition_request(
            request(target={"query_scope": "fem", "claim_id": "C1"})
        )


def test_request_validation_rejects_unknown_non_scientific_target_fields():
    with pytest.raises(ValueError, match="unknown AcquisitionRequest target fields"):
        validate_acquisition_request(
            request(target={"query_scope": "fem", "request_scope": "extra"})
        )


def test_request_validation_enforces_process_priority_bounds():
    with pytest.raises(ValueError, match="priority must be between"):
        validate_acquisition_request(request(priority=1.1))


def test_request_validation_does_not_mutate_input():
    original = request(
        constraints={"provider_preferences": ["semantic_scholar"]}
    )
    before = deepcopy(original)
    validate_acquisition_request(original)
    assert original == before


def test_query_scope_is_translated_only_to_query_input():
    projection = project_acquisition_request(request())
    assert projection["query_inputs"] == ["weak_form_galerkin_fem"]
    assert projection["translation_results"]["target.query_scope"]["class"] == "translated"
    assert projection["translation_losses"] == []


def test_provider_preferences_are_unrepresentable_not_encoded():
    projection = project_acquisition_request(
        request(
            constraints={
                "provider_preferences": ["semantic_scholar", "alternative_provider"]
            }
        )
    )
    loss = projection["translation_losses"][0]
    assert loss["field"] == "constraints.provider_preferences"
    assert loss["class"] == "unrepresentable"
    assert all("semantic_scholar" not in query for query in projection["query_inputs"])


def test_provider_access_constraints_are_unrepresentable():
    projection = project_acquisition_request(
        request(
            constraints={
                "provider_access_constraints": {
                    "semantic_scholar": "temporarily_unavailable"
                }
            }
        )
    )
    assert any(
        item["field"] == "constraints.provider_access_constraints"
        for item in projection["translation_losses"]
    )


def test_execution_limits_are_not_falsely_enforced():
    projection = project_acquisition_request(
        request(constraints={"execution_limits": {"max_attempts": 2}})
    )
    assert projection["execution_constraints_applied"] == []
    assert projection["translation_results"]["constraints.execution_limits"]["class"] == "unrepresentable"


def test_priority_is_process_metadata_only():
    projection = project_acquisition_request(request(priority=0.9))
    result = projection["translation_results"]["priority"]
    assert result["class"] == "preserved"
    assert result["semantic_status"] == "retained_as_process_metadata"


def test_successful_execution_returns_receipt(monkeypatch):
    calls = []

    def fake_executor(queries, **kwargs):
        calls.append((queries, kwargs))
        return [{"source_id": "S1", "title": "Example"}]

    def fake_report():
        return {
            "status": "success",
            "providers": {"arxiv": {"status": "success"}},
        }

    results, receipt = execute_acquisition_request(
        request(),
        retrieval_executor=fake_executor,
        retrieval_report_getter=fake_report,
    )

    assert results == [{"source_id": "S1", "title": "Example"}]
    assert calls[0][0] == ["weak_form_galerkin_fem"]
    assert receipt["acquisition_request_id"] == "AR1"
    assert receipt["execution_status"] == "success"
    assert receipt["translation_policy_version"] == TRANSLATION_POLICY_VERSION
    assert receipt["generated_query_inputs"] == ["weak_form_galerkin_fem"]
    assert receipt["started_at"]
    assert receipt["completed_at"]
    assert receipt["execution_id"].startswith("acquisition-execution-")


def test_empty_result_is_operational_not_scientific():
    results, receipt = execute_acquisition_request(
        request(),
        retrieval_executor=lambda queries, **kwargs: [],
        retrieval_report_getter=lambda: {"status": "empty_result", "providers": {}},
    )
    assert results == []
    assert receipt["execution_status"] == "empty_result"
    assert "evidence_gap" not in receipt
    assert "confidence" not in receipt


def test_rate_limited_report_maps_to_rate_limited_receipt():
    _, receipt = execute_acquisition_request(
        request(),
        retrieval_executor=lambda queries, **kwargs: [],
        retrieval_report_getter=lambda: {
            "status": "failure",
            "providers": {
                "arxiv": {"status": "rate_limited"},
                "semantic_scholar": {"status": "rate_limited"},
            },
        },
    )
    assert receipt["execution_status"] == "rate_limited"


def test_partial_failure_is_preserved_as_operational_outcome():
    _, receipt = execute_acquisition_request(
        request(),
        retrieval_executor=lambda queries, **kwargs: [{"source_id": "S1"}],
        retrieval_report_getter=lambda: {
            "status": "partial_failure",
            "providers": {
                "arxiv": {"status": "success"},
                "semantic_scholar": {"status": "failure"},
            },
        },
    )
    assert receipt["execution_status"] == "partial_failure"


def test_execution_exception_returns_failure_receipt():
    def fail(*args, **kwargs):
        raise RuntimeError("provider execution failed")

    results, receipt = execute_acquisition_request(
        request(),
        retrieval_executor=fail,
    )
    assert results == []
    assert receipt["execution_status"] == "failure"
    assert receipt["error_summary"] == "provider execution failed"


def test_retry_creates_distinct_execution_ids():
    executor = lambda queries, **kwargs: []
    report = lambda: {"status": "empty_result", "providers": {}}
    _, first = execute_acquisition_request(
        request(), retrieval_executor=executor, retrieval_report_getter=report
    )
    _, second = execute_acquisition_request(
        request(), retrieval_executor=executor, retrieval_report_getter=report
    )
    assert first["acquisition_request_id"] == second["acquisition_request_id"]
    assert first["execution_id"] != second["execution_id"]


def test_receipt_keeps_translation_loss_outside_evidence_records():
    _, receipt = execute_acquisition_request(
        request(
            constraints={
                "provider_preferences": ["semantic_scholar"],
                "execution_limits": {"max_attempts": 2},
            }
        ),
        retrieval_executor=lambda queries, **kwargs: [{"source_id": "S1"}],
        retrieval_report_getter=lambda: {"status": "success", "providers": {}},
    )
    assert "translation_losses" in receipt
    assert all("acquisition_request_id" not in loss for loss in receipt["translation_losses"])


def test_adapter_does_not_call_retrieval_for_empty_projection(monkeypatch):
    request_with_empty_scope = request(target={"query_scope": "   "})
    called = False

    def fake_executor(*args, **kwargs):
        nonlocal called
        called = True
        return []

    with pytest.raises(ValueError, match="target.query_scope"):
        execute_acquisition_request(
            request_with_empty_scope,
            retrieval_executor=fake_executor,
        )
    assert called is False

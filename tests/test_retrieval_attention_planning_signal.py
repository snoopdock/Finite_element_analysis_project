import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.retrieval_attention_planning_signal import (
    SIGNAL_TYPE,
    TRANSLATION_POLICY_VERSION,
    translate_attention_proposal,
    translate_attention_proposals,
    validate_research_planning_signal,
)


@pytest.fixture
def proposal():
    return {
        "attention_id": "attention-a12",
        "policy_version": "r7b-v1",
        "query_scope": "weak form Galerkin FEM",
        "provider": "semantic_scholar",
        "attention_reason": "Query has repeated provider non-success observations.",
        "observed_condition": "repeated_query_provider_non_success",
        "lifecycle_status": "open",
        "supporting_event_ids": ["E12", "E13"],
        "recommended_acquisition_action": "use_alternate_provider",
    }


def test_provider_failure_translates_to_operational_constraint_only(proposal):
    signal = translate_attention_proposal(proposal)

    assert signal["signal_type"] == SIGNAL_TYPE
    assert signal["source_attention_id"] == "attention-a12"
    assert signal["target"] == {
        "query_scope": "weak form Galerkin FEM",
        "provider": "semantic_scholar",
    }
    assert signal["acquisition_constraint"]["provider_access_limitation"] is True
    assert signal["provenance"]["supporting_event_ids"] == ["E12", "E13"]
    assert signal["translation_policy_version"] == TRANSLATION_POLICY_VERSION


def test_translation_is_lossy(proposal):
    proposal["retrieval_policy_internal_detail"] = {"threshold": 2}
    proposal["lifecycle_metadata"] = {"actor": "system"}

    signal = translate_attention_proposal(proposal)

    assert "attention_reason" not in signal
    assert "recommended_acquisition_action" not in signal
    assert "lifecycle_status" not in signal
    assert "retrieval_policy_internal_detail" not in signal
    assert "lifecycle_metadata" not in signal


def test_translation_does_not_mutate_source(proposal):
    original = copy.deepcopy(proposal)
    translate_attention_proposal(proposal)
    assert proposal == original


def test_signal_id_is_deterministic(proposal):
    first = translate_attention_proposal(proposal)
    second = translate_attention_proposal(proposal)
    assert first["research_planning_signal_id"] == second["research_planning_signal_id"]
    assert first == second


def test_created_at_is_non_deterministic_metadata_only(proposal):
    first = translate_attention_proposal(proposal, include_created_at=True)
    second = translate_attention_proposal(proposal, include_created_at=True)

    assert first["research_planning_signal_id"] == second["research_planning_signal_id"]
    assert first["created_at"] != ""
    assert second["created_at"] != ""


def test_empty_result_remains_operational(proposal):
    proposal["observed_condition"] = "query_returned_empty_result"
    signal = translate_attention_proposal(proposal)

    assert signal["acquisition_constraint"]["empty_query_result"] is True
    assert "evidence_gap" not in signal
    assert "confidence" not in signal


def test_partial_provider_availability_is_not_scientific(proposal):
    proposal["observed_condition"] = "provider_partially_available"
    signal = translate_attention_proposal(proposal)

    assert signal["acquisition_constraint"]["provider_access_limitation"] is True
    assert "scientific_relevance" not in signal
    assert "scientific_importance" not in signal


def test_closed_proposal_is_rejected(proposal):
    proposal["lifecycle_status"] = "closed"
    with pytest.raises(ValueError, match="lifecycle_status"):
        translate_attention_proposal(proposal)


def test_missing_provenance_is_rejected(proposal):
    proposal["supporting_event_ids"] = []
    with pytest.raises(ValueError, match="supporting_event_ids"):
        translate_attention_proposal(proposal)


def test_unknown_condition_is_rejected(proposal):
    proposal["observed_condition"] = "scientific_uncertainty"
    with pytest.raises(ValueError, match="observed_condition"):
        translate_attention_proposal(proposal)


def test_scientific_fields_are_rejected_in_signal():
    signal = {
        "research_planning_signal_id": "rps-1",
        "source_attention_id": "attention-a12",
        "schema_version": 1,
        "signal_type": SIGNAL_TYPE,
        "target": {"query_scope": "x", "provider": "p"},
        "provenance": {"supporting_event_ids": ["E1"]},
        "evidence_gap": True,
    }
    with pytest.raises(ValueError, match="forbidden scientific semantic field"):
        validate_research_planning_signal(signal)


def test_nested_scientific_fields_are_rejected():
    signal = {
        "research_planning_signal_id": "rps-1",
        "source_attention_id": "attention-a12",
        "schema_version": 1,
        "signal_type": SIGNAL_TYPE,
        "target": {"query_scope": "x", "provider": "p"},
        "provenance": {"supporting_event_ids": ["E1"]},
        "planning_context": {"confidence_score": 0.9},
    }
    with pytest.raises(ValueError, match="forbidden scientific semantic field"):
        validate_research_planning_signal(signal)


def test_unknown_signal_fields_are_rejected():
    signal = {
        "research_planning_signal_id": "rps-1",
        "source_attention_id": "attention-a12",
        "schema_version": 1,
        "signal_type": SIGNAL_TYPE,
        "target": {"query_scope": "x", "provider": "p"},
        "provenance": {"supporting_event_ids": ["E1"]},
        "scientific_hint": "should never cross boundary",
    }
    with pytest.raises(ValueError, match="unknown ResearchPlanningSignal fields"):
        validate_research_planning_signal(signal)


def test_validation_returns_defensive_copy(proposal):
    signal = translate_attention_proposal(proposal)
    validated = validate_research_planning_signal(signal)

    assert validated == signal
    assert validated is not signal
    validated["target"]["query_scope"] = "changed"
    assert signal["target"]["query_scope"] == "weak form Galerkin FEM"


def test_batch_translation_is_deterministically_ordered(proposal):
    second = copy.deepcopy(proposal)
    second["attention_id"] = "attention-b12"
    second["supporting_event_ids"] = ["E14"]

    signals = translate_attention_proposals([second, proposal])
    ids = [signal["research_planning_signal_id"] for signal in signals]
    assert ids == sorted(ids)
    assert len(signals) == 2


def test_signal_does_not_contain_lifecycle_fields(proposal):
    signal = translate_attention_proposal(proposal)
    assert "lifecycle_status" not in signal
    assert "LifecycleEvent" not in signal


def test_signal_does_not_contain_scientific_attention_fields(proposal):
    signal = translate_attention_proposal(proposal)
    for field in (
        "evidence_gap",
        "disagreement",
        "contextual_complexity",
        "verification_need",
        "importance",
        "decision_consequence",
    ):
        assert field not in signal


def test_signal_contains_no_acquisition_command(proposal):
    signal = translate_attention_proposal(proposal)
    assert "recommended_acquisition_action" not in signal
    assert "execute_retrieval" not in signal


def test_provenance_is_preserved_without_becoming_evidence(proposal):
    signal = translate_attention_proposal(proposal)
    assert signal["source_attention_id"] == proposal["attention_id"]
    assert signal["provenance"]["supporting_event_ids"] == proposal["supporting_event_ids"]
    assert "evidence_relations" not in signal


def test_signal_identity_is_distinct_from_attention_id(proposal):
    signal = translate_attention_proposal(proposal)
    assert signal["research_planning_signal_id"] != proposal["attention_id"]


def test_invalid_signal_type_is_rejected():
    signal = {
        "research_planning_signal_id": "rps-1",
        "source_attention_id": "attention-a12",
        "schema_version": 1,
        "signal_type": "scientific_attention",
        "target": {"query_scope": "x", "provider": "p"},
        "provenance": {"supporting_event_ids": ["E1"]},
    }
    with pytest.raises(ValueError, match="unsupported signal_type"):
        validate_research_planning_signal(signal)


def test_missing_source_attention_id_is_rejected():
    signal = {
        "research_planning_signal_id": "rps-1",
        "schema_version": 1,
        "signal_type": SIGNAL_TYPE,
        "target": {"query_scope": "x", "provider": "p"},
        "provenance": {"supporting_event_ids": ["E1"]},
    }
    with pytest.raises(ValueError, match="missing required fields"):
        validate_research_planning_signal(signal)


from dataclasses import replace

import pytest

from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.verification import VerificationContext, VerificationObligation


def test_obligation_is_deterministic(dependency_result):
    first = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="observation_contract",
        parameters={"predicate": "DEPENDS_ON"},
    )
    second = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="observation_contract",
        parameters={"predicate": "DEPENDS_ON"},
    )
    assert first.obligation_id == second.obligation_id


def test_obligation_defaults_to_all_result_observations_and_evidence(dependency_result):
    obligation = VerificationObligation.from_analysis_result(
        dependency_result,
        obligation_type="observation_contract",
    )
    assert obligation.observation_ids == tuple(x.observation_id for x in dependency_result.observations)
    assert obligation.evidence_ids == tuple(x.evidence_id for x in dependency_result.evidence)


def test_obligation_rejects_foreign_observation(dependency_result):
    with pytest.raises(ValueError, match="observations outside"):
        VerificationObligation.from_analysis_result(
            dependency_result,
            obligation_type="observation_contract",
            observation_ids=["obs:foreign"],
        )


def test_obligation_rejects_foreign_evidence(dependency_result):
    with pytest.raises(ValueError, match="evidence outside"):
        VerificationObligation.from_analysis_result(
            dependency_result,
            obligation_type="observation_contract",
            evidence_ids=["edge:foreign"],
        )


def test_obligation_rejects_blank_type(dependency_result):
    with pytest.raises(ValueError, match="obligation_type"):
        VerificationObligation.from_analysis_result(dependency_result, obligation_type=" ")


def test_context_detects_analysis_binding_mismatch(dependency_result):
    obligation = VerificationObligation.from_analysis_result(
        dependency_result, obligation_type="observation_contract"
    )
    other = replace(dependency_result, analysis_id="analysis:other")
    with pytest.raises(ValueError, match="different analysis"):
        VerificationContext(other).validate_obligation_binding(obligation)


def test_context_detects_semantic_context_mismatch(dependency_result):
    obligation = VerificationObligation.from_analysis_result(
        dependency_result, obligation_type="observation_contract"
    )
    other = replace(
        dependency_result,
        semantic_context=SemanticContext(relationship_vocabulary_version="different/v1"),
    )
    with pytest.raises(ValueError, match="semantic context"):
        VerificationContext(other).validate_obligation_binding(obligation)

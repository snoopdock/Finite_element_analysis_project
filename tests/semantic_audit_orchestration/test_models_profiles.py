import pytest

from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.orchestration import (
    AuditBudget,
    ExecutionMode,
    OperationalPriority,
    VerificationMethod,
    VerificationObjective,
    VerifierOrchestrationProfile,
    VerifierProfileCatalog,
    builtin_profile_catalog,
)
from audit_engine.semantic_audit.verification import ObservationContractVerifier, VerifierRegistry


def test_budget_rejects_zero_cost():
    with pytest.raises(ValueError, match="total_cost_units"):
        AuditBudget(0, 1)


def test_budget_rejects_empty_execution_modes():
    with pytest.raises(ValueError, match="execution mode"):
        AuditBudget(5, 1, ())


def test_profile_rejects_non_affirmative_evidence_ceiling():
    with pytest.raises(ValueError, match="affirmative"):
        VerifierOrchestrationProfile(
            "x", "1", VerificationMethod.CONTRACT, 1, VerificationStatus.INCONCLUSIVE
        )


def test_objective_identity_is_deterministic():
    first = VerificationObjective.create(
        obligation_id="obligation:1",
        minimum_evidence_state=VerificationStatus.VALIDATED,
        priority=OperationalPriority.HIGH,
    )
    second = VerificationObjective.create(
        obligation_id="obligation:1",
        minimum_evidence_state=VerificationStatus.VALIDATED,
        priority=OperationalPriority.HIGH,
    )
    assert first.objective_id == second.objective_id


def test_objective_rejects_conflicting_verifier_lists():
    with pytest.raises(ValueError, match="both allowed and excluded"):
        VerificationObjective.create(
            obligation_id="o",
            minimum_evidence_state=VerificationStatus.OBSERVED,
            allowed_verifier_ids=["v"],
            excluded_verifier_ids=["v"],
        )


def test_catalog_rejects_duplicate_profiles():
    catalog = VerifierProfileCatalog()
    profile = VerifierOrchestrationProfile(
        "x", "1", VerificationMethod.CONTRACT, 1, VerificationStatus.VALIDATED
    )
    catalog.register(profile)
    with pytest.raises(ValueError, match="already registered"):
        catalog.register(profile)


def test_catalog_detects_profile_version_mismatch():
    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    catalog = VerifierProfileCatalog()
    catalog.register(
        VerifierOrchestrationProfile(
            "observation-contract", "9.9.9", VerificationMethod.CONTRACT, 1,
            VerificationStatus.VALIDATED,
        )
    )
    with pytest.raises(ValueError, match="version mismatch"):
        catalog.validate_against_registry(registry)


def test_builtin_profiles_are_policy_metadata_not_verifier_mutation():
    catalog = builtin_profile_catalog()
    profile = catalog.get("observation-contract")
    assert profile is not None
    assert profile.cost_units == 1
    assert profile.execution_mode is ExecutionMode.IN_PROCESS_READ_ONLY
    assert not hasattr(ObservationContractVerifier.descriptor, "cost_units")

def test_builtin_catalog_allows_partial_active_registry():
    registry = VerifierRegistry(); registry.register(ObservationContractVerifier())
    builtin_profile_catalog().validate_against_registry(registry)

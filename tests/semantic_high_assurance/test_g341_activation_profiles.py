from __future__ import annotations

from audit_engine.semantic_audit.high_assurance import (
    AssuranceMechanism,
    BOUNDED_CNF_ADAPTER_ID,
    BOUNDED_CNF_SAT_OBLIGATION,
    BoundedCnfSolverAdapter,
    ControlledHighAssuranceExecutor,
    HighAssuranceAdapterRegistry,
    HighAssurancePolicy,
    REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
)
from audit_engine.semantic_audit.orchestration import builtin_profile_catalog
from audit_engine.semantic_audit.verification.models import VerificationContext, VerificationObligation


def _solver_obligation(analysis_result):
    return VerificationObligation.from_analysis_result(
        analysis_result,
        obligation_type=BOUNDED_CNF_SAT_OBLIGATION,
        requested_verifier_ids=(BOUNDED_CNF_ADAPTER_ID,),
        parameters={
            "clauses": [[1]],
            "variable_count": 1,
            "expected_satisfiable": True,
            "timeout_ms": 1000,
        },
    )


def test_solver_is_denied_by_default_policy(analysis_result, semantic_graph):
    registry = HighAssuranceAdapterRegistry()
    registry.register(BoundedCnfSolverAdapter())
    record = ControlledHighAssuranceExecutor(registry).execute(
        _solver_obligation(analysis_result),
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    assert record.status.value == "denied"
    assert record.denial_reason == "mechanism_not_allowed"


def test_allowing_solver_mechanism_without_activation_is_still_denied(analysis_result, semantic_graph):
    registry = HighAssuranceAdapterRegistry()
    registry.register(BoundedCnfSolverAdapter())
    policy = HighAssurancePolicy(
        allowed_mechanisms=(AssuranceMechanism.SOLVER,),
    )
    record = ControlledHighAssuranceExecutor(registry, policy=policy).execute(
        _solver_obligation(analysis_result),
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    assert record.status.value == "denied"
    assert record.denial_reason == "adapter_not_explicitly_activated"


def test_explicit_solver_activation_allows_execution(analysis_result, semantic_graph):
    registry = HighAssuranceAdapterRegistry()
    registry.register(BoundedCnfSolverAdapter())
    policy = HighAssurancePolicy(
        allowed_mechanisms=(AssuranceMechanism.SOLVER,),
        activated_adapter_ids=(BOUNDED_CNF_ADAPTER_ID,),
    )
    record = ControlledHighAssuranceExecutor(registry, policy=policy).execute(
        _solver_obligation(analysis_result),
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    assert record.status.value == "executed"


def test_builtin_adapter_registry_does_not_implicitly_activate_solver():
    from audit_engine.semantic_audit.high_assurance import builtin_high_assurance_adapter_registry

    ids = {item.descriptor.adapter_id for item in builtin_high_assurance_adapter_registry().adapters()}
    assert BOUNDED_CNF_ADAPTER_ID not in ids
    assert REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID not in ids


def test_solver_and_executable_profiles_are_metadata_only():
    profiles = {item.verifier_id: item for item in builtin_profile_catalog().profiles()}
    assert profiles[BOUNDED_CNF_ADAPTER_ID].method.value == "solver"
    assert profiles[BOUNDED_CNF_ADAPTER_ID].cost_units == 8
    assert profiles[REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID].method.value == "executable"
    assert profiles[REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID].cost_units == 6

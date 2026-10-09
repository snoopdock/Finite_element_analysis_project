from __future__ import annotations

import pytest

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import (
    AssuranceMechanism,
    BOUNDED_CNF_ADAPTER_ID,
    BOUNDED_CNF_SAT_OBLIGATION,
    BoundedCnfSolverAdapter,
    ControlledHighAssuranceExecutor,
    HighAssuranceAdapterRegistry,
    HighAssurancePolicy,
    WitnessKind,
)
from audit_engine.semantic_audit.verification.models import (
    VerificationContext,
    VerificationDecision,
    VerificationObligation,
)


def _obligation(analysis_result, clauses, variable_count, expected_satisfiable=True):
    return VerificationObligation.from_analysis_result(
        analysis_result,
        obligation_type=BOUNDED_CNF_SAT_OBLIGATION,
        requested_verifier_ids=(BOUNDED_CNF_ADAPTER_ID,),
        parameters={
            "clauses": clauses,
            "variable_count": variable_count,
            "expected_satisfiable": expected_satisfiable,
            "timeout_ms": 1000,
        },
    )


def _executor(*, max_variables=12):
    registry = HighAssuranceAdapterRegistry()
    registry.register(BoundedCnfSolverAdapter(max_variables=max_variables))
    policy = HighAssurancePolicy(
        allowed_mechanisms=(
            AssuranceMechanism.STATIC_ANALYSIS,
            AssuranceMechanism.ARTIFACT_INTEGRITY,
            AssuranceMechanism.SOLVER,
        ),
        activated_adapter_ids=(BOUNDED_CNF_ADAPTER_ID,),
    )
    return ControlledHighAssuranceExecutor(registry, policy=policy)


def test_bounded_solver_confirms_satisfiable_formula(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, [[1], [2, -1]], 2, True)
    record = _executor().execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    assert record.result is not None
    assert record.result.decision == VerificationDecision.CONFIRMED
    assert record.result.evidence_state == VerificationStatus.VALIDATED
    assert record.result.witnesses[0].kind == WitnessKind.SOLVER_CERTIFICATE
    assert record.result.witnesses[0].details["verdict"] == "sat"


def test_bounded_solver_confirms_unsatisfiable_formula(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, [[1], [-1]], 1, False)
    record = _executor().execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    result = record.result
    assert result is not None
    assert result.decision == VerificationDecision.CONFIRMED
    witness = result.witnesses[0]
    assert witness.details["verdict"] == "unsat"
    assert witness.details["checked_assignments"] == 2
    assert witness.details["certificate_method"] == "complete_truth_table_exhaustion"


def test_bounded_solver_refutes_wrong_expected_verdict(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, [[1]], 1, False)
    record = _executor().execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    assert record.result is not None
    assert record.result.decision == VerificationDecision.REFUTED
    assert record.result.evidence_state == VerificationStatus.VALIDATED


def test_empty_clause_is_unsatisfiable(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, [[]], 1, False)
    record = _executor().execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    assert record.result is not None
    assert record.result.decision == VerificationDecision.CONFIRMED


def test_empty_cnf_is_satisfiable(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, [], 2, True)
    record = _executor().execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    assert record.result is not None
    assert record.result.decision == VerificationDecision.CONFIRMED


def test_solver_rejects_variable_outside_bound(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, [[1]], 3, True)
    record = _executor(max_variables=2).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    assert record.status.value == "adapter_error"
    assert "max_variables=2" in (record.denial_reason or "")


def test_solver_rejects_literal_outside_declared_variables(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, [[2]], 1, True)
    record = _executor().execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    assert record.status.value == "adapter_error"
    assert "outside variable_count" in (record.denial_reason or "")


def test_solver_envelope_declares_external_solver_exclusion(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, [[1, -2]], 2, True)
    record = _executor().execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=BOUNDED_CNF_ADAPTER_ID,
    )
    result = record.result
    assert result is not None
    assert result.validation_envelope.completeness.value == "exhaustive_within_scope"
    assert "external SAT solver implementations" in result.validation_envelope.excluded_scope


def test_solver_identity_is_deterministic(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, [[1, 2], [-1, 2]], 2, True)
    executor = _executor()
    context = VerificationContext(analysis_result, semantic_graph)
    one = executor.execute(obligation, context, adapter_id=BOUNDED_CNF_ADAPTER_ID)
    two = executor.execute(obligation, context, adapter_id=BOUNDED_CNF_ADAPTER_ID)
    assert one.execution_id == two.execution_id
    assert one.result is not None and two.result is not None
    assert one.result.result_id == two.result.result_id

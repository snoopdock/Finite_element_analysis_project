from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import (
    AssuranceMechanism,
    CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    ContainmentMode,
    ControlledExternalCnfSolverAdapter,
    ControlledHighAssuranceExecutor,
    ControlledJsonSubprocessRunner,
    ExternalProcessRiskAcknowledgement,
    ExternalProcessSpec,
    HighAssuranceAdapterRegistry,
    HighAssuranceExecutionStatus,
    HighAssurancePolicy,
    ValidationCompleteness,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import BOUNDED_CNF_SAT_OBLIGATION
from audit_engine.semantic_audit.orchestration.models import ExecutionMode
from audit_engine.semantic_audit.orchestration.profiles import builtin_profile_catalog
from audit_engine.semantic_audit.verification import VerificationContext, VerificationDecision, VerificationObligation


FIXTURE = (Path(__file__).parent / "fixtures" / "external_cnf_solver_fixture.py").resolve()
SOLVER_ID = "fixture-cnf-solver"
SOLVER_VERSION = "0.1.0"


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _adapter(mode="solve", *, independent_unsat_max_variables=12):
    executable = Path(sys.executable).resolve()
    runner = ControlledJsonSubprocessRunner(
        ExternalProcessSpec(
            process_id="fixture-cnf-process",
            process_version="0.1.0",
            executable_path=str(executable),
            executable_sha256=_sha256(executable),
            arguments=(str(FIXTURE), mode),
        ),
        risk_acknowledgement=ExternalProcessRiskAcknowledgement(True, True),
    )
    return ControlledExternalCnfSolverAdapter(
        runner,
        solver_id=SOLVER_ID,
        solver_version=SOLVER_VERSION,
        independent_unsat_max_variables=independent_unsat_max_variables,
    )


def _obligation(analysis_result, *, clauses, variable_count, expected):
    return VerificationObligation.from_analysis_result(
        analysis_result,
        obligation_type=BOUNDED_CNF_SAT_OBLIGATION,
        requested_verifier_ids=(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,),
        parameters={
            "variable_count": variable_count,
            "clauses": clauses,
            "expected_satisfiable": expected,
            "timeout_ms": 1000,
        },
    )


def _executor(adapter, *, activate=True, allow_side_effects=True, allow_external=True):
    registry = HighAssuranceAdapterRegistry()
    registry.register(adapter)
    policy = HighAssurancePolicy(
        allowed_mechanisms=(AssuranceMechanism.SOLVER,),
        allowed_containment_modes=(ContainmentMode.CONTROLLED_EXTERNAL,) if allow_external else (ContainmentMode.IN_PROCESS_READ_ONLY,),
        allow_side_effects=allow_side_effects,
        activated_adapter_ids=(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,) if activate else (),
    )
    return ControlledHighAssuranceExecutor(registry, policy=policy)


def test_external_solver_is_denied_without_explicit_activation(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, clauses=[[1]], variable_count=1, expected=True)
    record = _executor(_adapter(), activate=False).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    )
    assert record.status == HighAssuranceExecutionStatus.DENIED
    assert record.denial_reason == "adapter_not_explicitly_activated"


def test_external_solver_requires_controlled_external_containment_permission(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, clauses=[[1]], variable_count=1, expected=True)
    record = _executor(_adapter(), allow_external=False).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    )
    assert record.status == HighAssuranceExecutionStatus.DENIED
    assert record.denial_reason == "containment_mode_not_allowed"


def test_external_solver_requires_side_effect_policy_acknowledgement(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, clauses=[[1]], variable_count=1, expected=True)
    record = _executor(_adapter(), allow_side_effects=False).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    )
    assert record.status == HighAssuranceExecutionStatus.DENIED
    assert record.denial_reason == "side_effecting_adapter_not_allowed"


def test_external_sat_model_is_independently_validated(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, clauses=[[1], [-2]], variable_count=2, expected=True)
    record = _executor(_adapter()).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    )
    assert record.status == HighAssuranceExecutionStatus.EXECUTED
    result = record.result
    assert result.decision == VerificationDecision.CONFIRMED
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.validation_envelope.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE
    assert {w.kind.value for w in result.witnesses} == {"execution_trace", "solver_certificate"}


def test_external_sat_can_refute_expected_unsat(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, clauses=[[1]], variable_count=1, expected=False)
    result = _executor(_adapter()).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    ).result
    assert result.decision == VerificationDecision.REFUTED
    assert result.evidence_state == VerificationStatus.VALIDATED


def test_external_unsat_is_independently_validated_when_bounded(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, clauses=[[1], [-1]], variable_count=1, expected=False)
    result = _executor(_adapter()).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    ).result
    assert result.decision == VerificationDecision.CONFIRMED
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.validation_envelope.completeness == ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE


def test_false_external_unsat_is_overruled_by_independent_counterexample(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, clauses=[[1]], variable_count=1, expected=True)
    result = _executor(_adapter("false-unsat")).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    ).result
    assert result.decision == VerificationDecision.CONFIRMED
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert "external_unsat_refuted_by_independent_model" in result.diagnostics
    assert any(w.kind.value == "counterexample" for w in result.witnesses)


def test_unvalidated_large_unsat_cannot_be_promoted_to_validated(analysis_result, semantic_graph):
    # Formula is trivially UNSAT but declared with 13 variables. The external
    # process says UNSAT; the repository intentionally does not independently
    # enumerate above its configured bound.
    obligation = _obligation(analysis_result, clauses=[[1], [-1]], variable_count=13, expected=False)
    result = _executor(_adapter(independent_unsat_max_variables=12)).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    ).result
    assert result.decision == VerificationDecision.CONFIRMED
    assert result.evidence_state == VerificationStatus.OBSERVED
    assert result.validation_envelope.completeness == ValidationCompleteness.PARTIAL


def test_unknown_external_solver_result_is_inconclusive(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, clauses=[[1]], variable_count=1, expected=True)
    result = _executor(_adapter("unknown")).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    ).result
    assert result.decision == VerificationDecision.INCONCLUSIVE
    assert result.evidence_state == VerificationStatus.INCONCLUSIVE


def test_external_solver_response_binding_is_strict(analysis_result, semantic_graph):
    obligation = _obligation(analysis_result, clauses=[[1]], variable_count=1, expected=True)
    record = _executor(_adapter("wrong-binding")).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    )
    assert record.status == HighAssuranceExecutionStatus.ADAPTER_ERROR
    assert "different request" in record.denial_reason


def test_external_solver_profile_is_metadata_only_and_controlled_external():
    profile = builtin_profile_catalog().get(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID)
    assert profile is not None
    assert profile.execution_mode == ExecutionMode.CONTROLLED_EXTERNAL
    assert profile.side_effect_free is False
    assert profile.metadata["activation_required"] is True


def test_expected_verification_answer_is_not_sent_to_external_solver(analysis_result, semantic_graph):
    from audit_engine.semantic_audit.high_assurance.external_process import (
        ExternalJsonProcessResult,
        ExternalProcessTranscript,
    )

    class CapturingRunner:
        def __init__(self):
            self.payload = None

        def run(self, payload, *, timeout_ms):
            self.payload = dict(payload)
            response = {
                "protocol_version": "semantic_external_solver/v1",
                "request_id": payload["request_id"],
                "input_digest": payload["input_digest"],
                "solver_id": SOLVER_ID,
                "solver_version": SOLVER_VERSION,
                "verdict": "sat",
                "certificate": {"kind": "sat_model", "assignment": {"1": True}},
                "diagnostics": [],
            }
            transcript = ExternalProcessTranscript(
                process_id="capture",
                process_version="1",
                executable_sha256="0" * 64,
                input_sha256="1" * 64,
                stdout_sha256="2" * 64,
                stderr_sha256="3" * 64,
                return_code=0,
                timeout_ms=timeout_ms,
                stdout_bytes=1,
                stderr_bytes=0,
            )
            return ExternalJsonProcessResult(response, transcript)

    runner = CapturingRunner()
    adapter = ControlledExternalCnfSolverAdapter(
        runner,
        solver_id=SOLVER_ID,
        solver_version=SOLVER_VERSION,
    )
    obligation = _obligation(analysis_result, clauses=[[1]], variable_count=1, expected=True)
    result = _executor(adapter).execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    ).result
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert "expected_satisfiable" not in runner.payload

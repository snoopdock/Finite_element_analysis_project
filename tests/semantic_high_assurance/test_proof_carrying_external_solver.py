from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
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
    HighAssurancePolicy,
    RUP_PROOF_FORMAT,
    ValidationCompleteness,
    WitnessKind,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import BOUNDED_CNF_SAT_OBLIGATION
from audit_engine.semantic_audit.verification import VerificationContext, VerificationDecision, VerificationObligation


FIXTURE = Path("tests/semantic_high_assurance/fixtures/external_cnf_solver_fixture.py").resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def analysis_context():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("a", "Module"))
    graph.add_node(SemanticNode("b", "Module"))
    graph.add_edge(SemanticEdge("a", "b", "DEPENDS_ON"))
    analysis = SemanticGraphAnalysisService(
        graph,
        semantic_context=SemanticContext(relationship_vocabulary_version="test/v1"),
    ).analyze(GraphQuery("g343-analysis", QueryType.DEPENDENCY, ["a"], {"max_depth": 1}))
    return graph, analysis


def make_adapter(mode: str):
    executable = Path(sys.executable).resolve()
    spec = ExternalProcessSpec(
        process_id="fixture-cnf-process",
        process_version="0.1.0",
        executable_path=str(executable),
        executable_sha256=sha256_file(executable),
        arguments=(str(FIXTURE), mode),
    )
    runner = ControlledJsonSubprocessRunner(
        spec,
        risk_acknowledgement=ExternalProcessRiskAcknowledgement(True, True),
    )
    return ControlledExternalCnfSolverAdapter(
        runner,
        solver_id="fixture-cnf-solver",
        solver_version="0.1.0",
        independent_unsat_max_variables=12,
    )


def execute(mode: str, *, variable_count: int, clauses, expected: bool):
    graph, analysis = analysis_context()
    obligation = VerificationObligation.from_analysis_result(
        analysis,
        obligation_type=BOUNDED_CNF_SAT_OBLIGATION,
        requested_verifier_ids=(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,),
        parameters={
            "variable_count": variable_count,
            "clauses": clauses,
            "expected_satisfiable": expected,
            "timeout_ms": 1500,
        },
    )
    registry = HighAssuranceAdapterRegistry()
    registry.register(make_adapter(mode))
    executor = ControlledHighAssuranceExecutor(
        registry,
        policy=HighAssurancePolicy(
            allowed_mechanisms=(AssuranceMechanism.SOLVER,),
            allowed_containment_modes=(ContainmentMode.CONTROLLED_EXTERNAL,),
            allow_side_effects=True,
            activated_adapter_ids=(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,),
        ),
    )
    record = executor.execute(
        obligation,
        VerificationContext(analysis, graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    )
    assert record.result is not None
    return record.result


def test_large_unsat_can_be_validated_by_repository_checked_rup_proof():
    result = execute(
        "rup-unsat",
        variable_count=13,
        clauses=[[1], [-1]],
        expected=False,
    )
    assert result.decision == VerificationDecision.CONFIRMED
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.validation_envelope.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE
    proof = [w for w in result.witnesses if w.kind == WitnessKind.FORMAL_PROOF]
    assert len(proof) == 1
    assert proof[0].details["proof_format"] == RUP_PROOF_FORMAT


def test_invalid_large_rup_proof_does_not_upgrade_external_unsat():
    result = execute(
        "invalid-rup",
        variable_count=13,
        clauses=[[1, 2], [-1, 2], [1, -2], [-1, -2]],
        expected=False,
    )
    assert result.decision == VerificationDecision.CONFIRMED
    assert result.evidence_state == VerificationStatus.OBSERVED
    assert result.validation_envelope.completeness == ValidationCompleteness.PARTIAL
    assert "external_unsat_proof_not_accepted" in result.diagnostics


def test_proof_checker_format_is_declared_in_validation_envelope():
    result = execute("rup-unsat", variable_count=13, clauses=[[1], [-1]], expected=False)
    assert RUP_PROOF_FORMAT in result.validation_envelope.environment["registered_unsat_proof_formats"]


def test_valid_rup_proof_refutes_expected_sat_hypothesis():
    result = execute("rup-unsat", variable_count=13, clauses=[[1], [-1]], expected=True)
    assert result.decision == VerificationDecision.REFUTED
    assert result.evidence_state == VerificationStatus.VALIDATED

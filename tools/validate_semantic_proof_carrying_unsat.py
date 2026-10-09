#!/usr/bin/env python3
"""Deterministic G3.4.3 proof-carrying UNSAT acceptance validator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    RupUnsatProofChecker,
    ValidationCompleteness,
    WitnessKind,
    builtin_high_assurance_adapter_registry,
    builtin_unsat_proof_checker_registry,
    validate_external_cnf_certificate,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import BOUNDED_CNF_SAT_OBLIGATION, cnf_digest
from audit_engine.semantic_audit.verification import VerificationContext, VerificationDecision, VerificationObligation


FIXTURE = ROOT / "tests" / "semantic_high_assurance" / "fixtures" / "external_cnf_solver_fixture.py"
ARTIFACT = ROOT / "artifacts" / "semantic_proof_carrying_unsat_validation.json"
SOLVER_ID = "fixture-cnf-solver"
SOLVER_VERSION = "0.1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def make_analysis():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("module-a", "Module"))
    graph.add_node(SemanticNode("module-b", "Module"))
    graph.add_edge(SemanticEdge("module-a", "module-b", "DEPENDS_ON"))
    context = SemanticContext(relationship_vocabulary_version="repo-relations/v1")
    analysis = SemanticGraphAnalysisService(graph, semantic_context=context).analyze(
        GraphQuery("g343-validator-analysis", QueryType.DEPENDENCY, ["module-a"], {"max_depth": 1})
    )
    return graph, analysis


def make_adapter(mode: str):
    executable = Path(sys.executable).resolve()
    runner = ControlledJsonSubprocessRunner(
        ExternalProcessSpec(
            process_id="fixture-cnf-process",
            process_version="0.1.0",
            executable_path=str(executable),
            executable_sha256=sha256_file(executable),
            arguments=(str(FIXTURE), mode),
        ),
        risk_acknowledgement=ExternalProcessRiskAcknowledgement(True, True),
    )
    return ControlledExternalCnfSolverAdapter(
        runner,
        solver_id=SOLVER_ID,
        solver_version=SOLVER_VERSION,
        independent_unsat_max_variables=12,
    )


def execute_external(mode: str, *, variable_count: int, clauses, expected: bool):
    graph, analysis = make_analysis()
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
    return record.result


def manual_workflows_05_17() -> bool:
    folder = ROOT / ".github" / "workflows"
    for number in range(5, 18):
        matches = list(folder.glob(f"{number:02d}_*.yml"))
        if len(matches) != 1:
            return False
        text = matches[0].read_text(encoding="utf-8")
        if "on:\n  workflow_dispatch:\n" not in text or "\n  push:" in text or "\n  pull_request:" in text:
            return False
    return True


def run() -> dict[str, object]:
    checks: dict[str, bool] = {}

    direct_clauses = ((1,), (-1,))
    direct_digest = cnf_digest(13, direct_clauses)
    direct = RupUnsatProofChecker().check(
        certificate={
            "kind": "unsat_proof",
            "proof_format": RUP_PROOF_FORMAT,
            "cnf_digest": direct_digest,
            "steps": [[]],
        },
        variable_count=13,
        clauses=direct_clauses,
        subject_digest=direct_digest,
    )
    checks["repository_rup_checker_accepts_sound_empty_clause_derivation"] = direct.accepted

    xor_clauses = ((1, 2), (-1, 2), (1, -2), (-1, -2))
    xor_digest = cnf_digest(2, xor_clauses)
    multi = RupUnsatProofChecker().check(
        certificate={
            "kind": "unsat_proof",
            "proof_format": RUP_PROOF_FORMAT,
            "cnf_digest": xor_digest,
            "steps": [[1], [-1], []],
        },
        variable_count=2,
        clauses=xor_clauses,
        subject_digest=xor_digest,
    )
    checks["repository_rup_checker_validates_every_step"] = multi.accepted and multi.checked_steps == 3

    large = execute_external("rup-unsat", variable_count=13, clauses=[[1], [-1]], expected=False)
    checks["large_external_unsat_proof_reaches_validated"] = bool(
        large
        and large.decision == VerificationDecision.CONFIRMED
        and large.evidence_state == VerificationStatus.VALIDATED
        and large.validation_envelope.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE
    )
    checks["validated_unsat_has_formal_proof_witness"] = bool(
        large and any(w.kind == WitnessKind.FORMAL_PROOF for w in large.witnesses)
    )
    checks["validation_envelope_declares_registered_proof_format"] = bool(
        large and RUP_PROOF_FORMAT in large.validation_envelope.environment["registered_unsat_proof_formats"]
    )

    invalid = execute_external(
        "invalid-rup",
        variable_count=13,
        clauses=[[1, 2], [-1, 2], [1, -2], [-1, -2]],
        expected=False,
    )
    checks["invalid_large_rup_proof_remains_observed"] = bool(
        invalid
        and invalid.evidence_state == VerificationStatus.OBSERVED
        and invalid.validation_envelope.completeness == ValidationCompleteness.PARTIAL
    )

    unsupported = validate_external_cnf_certificate(
        verdict="unsat",
        certificate={
            "kind": "unsat_proof",
            "proof_format": "unsupported/v1",
            "cnf_digest": direct_digest,
            "steps": [[]],
        },
        variable_count=13,
        clauses=direct_clauses,
        subject_digest=direct_digest,
        independent_unsat_max_variables=12,
    )
    checks["unsupported_proof_format_remains_observed"] = (
        unsupported.evidence_state == VerificationStatus.OBSERVED
        and unsupported.completeness == ValidationCompleteness.PARTIAL
    )

    wrong_digest = RupUnsatProofChecker().check(
        certificate={
            "kind": "unsat_proof",
            "proof_format": RUP_PROOF_FORMAT,
            "cnf_digest": "0" * 64,
            "steps": [[]],
        },
        variable_count=13,
        clauses=direct_clauses,
        subject_digest=direct_digest,
    )
    checks["proof_is_bound_to_exact_cnf_digest"] = not wrong_digest.accepted

    small_invalid = validate_external_cnf_certificate(
        verdict="unsat",
        certificate={
            "kind": "unsat_proof",
            "proof_format": RUP_PROOF_FORMAT,
            "cnf_digest": xor_digest,
            "steps": [[]],
        },
        variable_count=2,
        clauses=xor_clauses,
        subject_digest=xor_digest,
        independent_unsat_max_variables=12,
    )
    checks["invalid_small_proof_can_fallback_to_independent_exhaustion"] = (
        small_invalid.evidence_state == VerificationStatus.VALIDATED
        and small_invalid.completeness == ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE
    )

    checks["builtin_proof_registry_is_explicit"] = builtin_unsat_proof_checker_registry().formats() == (RUP_PROOF_FORMAT,)
    checks["external_solver_still_not_in_default_adapter_registry"] = (
        builtin_high_assurance_adapter_registry().get(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID) is None
    )
    try:
        from formal.router import FormalRouter
        FormalRouter().route("existence", 1.0, 0.5)
    except NotImplementedError:
        checks["formal_router_remains_inactive"] = True
    else:
        checks["formal_router_remains_inactive"] = False

    for name in (
        "cnf_rup_unsat_proof_contract.yaml",
        "unsat_proof_checker_registry_contract.yaml",
        "proof_carrying_external_solver_contract.yaml",
    ):
        checks[f"contract_present:{name}"] = bool(
            yaml.safe_load((ROOT / "specs" / "contracts" / name).read_text(encoding="utf-8"))
        )
    for name in ("cnf_rup_unsat_proof.schema.json", "unsat_proof_check.schema.json"):
        checks[f"schema_present:{name}"] = bool(
            json.loads((ROOT / "specs" / "schemas" / name).read_text(encoding="utf-8"))
        )
    workflow = (ROOT / ".github" / "workflows" / "17_semantic_proof_carrying_unsat_validation.yml").read_text(encoding="utf-8")
    checks["workflow_17_manual_only"] = "on:\n  workflow_dispatch:\n" in workflow and "\n  push:" not in workflow
    checks["g3_workflows_05_17_manual_only"] = manual_workflows_05_17()

    passed = all(checks.values())
    payload = {
        "milestone": "G3.4.3",
        "validator": "validate_semantic_proof_carrying_unsat.py",
        "passed": passed,
        "checks": checks,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = run()
    for name, passed in payload["checks"].items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if payload["passed"]:
        print("G3.4.3 proof-carrying UNSAT validation passed.")
        return 0
    print("G3.4.3 proof-carrying UNSAT validation failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

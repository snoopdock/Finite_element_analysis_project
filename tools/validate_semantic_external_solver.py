#!/usr/bin/env python3
"""Deterministic G3.4.2 acceptance validator.

This validator exercises the controlled-external boundary using a repository
fixture process.  The fixture is not a production solver and is never added to
the built-in adapter registry; it exists only to validate process identity,
protocol binding, independent certificate validation, and policy boundaries.
"""

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
    ExternalProcessError,
    ExternalProcessRiskAcknowledgement,
    ExternalProcessSpec,
    HighAssuranceAdapterRegistry,
    HighAssuranceExecutionStatus,
    HighAssurancePolicy,
    ValidationCompleteness,
    builtin_high_assurance_adapter_registry,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import BOUNDED_CNF_SAT_OBLIGATION
from audit_engine.semantic_audit.orchestration.models import ExecutionMode
from audit_engine.semantic_audit.orchestration.profiles import builtin_profile_catalog
from audit_engine.semantic_audit.verification import VerificationContext, VerificationDecision, VerificationObligation


FIXTURE = ROOT / "tests" / "semantic_high_assurance" / "fixtures" / "external_cnf_solver_fixture.py"
ARTIFACT = ROOT / "artifacts" / "semantic_external_solver_validation.json"
SOLVER_ID = "fixture-cnf-solver"
SOLVER_VERSION = "0.1.0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_analysis():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("module-a", "Module"))
    graph.add_node(SemanticNode("module-b", "Module"))
    graph.add_edge(SemanticEdge("module-a", "module-b", "DEPENDS_ON", metadata={"source_id": "code:a"}))
    context = SemanticContext(relationship_vocabulary_version="repo-relations/v1")
    analysis = SemanticGraphAnalysisService(graph, semantic_context=context).analyze(
        GraphQuery("g342-validator-analysis", QueryType.DEPENDENCY, ["module-a"], {"max_depth": 1})
    )
    return graph, analysis


def make_adapter(mode="solve", *, acknowledge=True, unsat_bound=12):
    executable = Path(sys.executable).resolve()
    spec = ExternalProcessSpec(
        process_id="fixture-cnf-process",
        process_version="0.1.0",
        executable_path=str(executable),
        executable_sha256=sha256_file(executable),
        arguments=(str(FIXTURE), mode),
    )
    ack = ExternalProcessRiskAcknowledgement(acknowledge, acknowledge)
    runner = ControlledJsonSubprocessRunner(spec, risk_acknowledgement=ack)
    return ControlledExternalCnfSolverAdapter(
        runner,
        solver_id=SOLVER_ID,
        solver_version=SOLVER_VERSION,
        independent_unsat_max_variables=unsat_bound,
    )


def make_obligation(analysis, *, clauses, variable_count, expected):
    return VerificationObligation.from_analysis_result(
        analysis,
        obligation_type=BOUNDED_CNF_SAT_OBLIGATION,
        requested_verifier_ids=(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,),
        parameters={
            "variable_count": variable_count,
            "clauses": clauses,
            "expected_satisfiable": expected,
            "timeout_ms": 1000,
        },
    )


def make_executor(adapter, *, activated=True):
    registry = HighAssuranceAdapterRegistry()
    registry.register(adapter)
    return ControlledHighAssuranceExecutor(
        registry,
        policy=HighAssurancePolicy(
            allowed_mechanisms=(AssuranceMechanism.SOLVER,),
            allowed_containment_modes=(ContainmentMode.CONTROLLED_EXTERNAL,),
            allow_side_effects=True,
            activated_adapter_ids=(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,) if activated else (),
        ),
    )


def manual_workflows_05_16() -> bool:
    folder = ROOT / ".github" / "workflows"
    for number in range(5, 17):
        matches = list(folder.glob(f"{number:02d}_*.yml"))
        if len(matches) != 1:
            return False
        text = matches[0].read_text(encoding="utf-8")
        if "on:\n  workflow_dispatch:\n" not in text or "\n  push:" in text or "\n  pull_request:" in text:
            return False
    return True


def run() -> dict[str, object]:
    graph, analysis = make_analysis()
    context = VerificationContext(analysis, graph)
    checks: dict[str, bool] = {}

    sat_obligation = make_obligation(analysis, clauses=[[1], [-2]], variable_count=2, expected=True)
    denied = make_executor(make_adapter(), activated=False).execute(
        sat_obligation, context, adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID
    )
    checks["external_solver_denied_without_explicit_activation"] = (
        denied.status == HighAssuranceExecutionStatus.DENIED
        and denied.denial_reason == "adapter_not_explicitly_activated"
    )

    try:
        make_adapter(acknowledge=False).runner.run(
            {"protocol_version": "semantic_external_solver/v1"}, timeout_ms=50
        )
    except ExternalProcessError as exc:
        checks["external_process_requires_isolation_risk_acknowledgement"] = "network isolation" in str(exc)
    else:
        checks["external_process_requires_isolation_risk_acknowledgement"] = False

    sat = make_executor(make_adapter()).execute(
        sat_obligation, context, adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID
    ).result
    checks["external_sat_model_is_independently_validated"] = bool(
        sat
        and sat.decision == VerificationDecision.CONFIRMED
        and sat.evidence_state == VerificationStatus.VALIDATED
        and sat.validation_envelope.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE
    )
    checks["external_execution_trace_discloses_no_os_sandbox"] = bool(
        sat
        and sat.validation_envelope.environment["external_process"]["network_isolation_enforced"] is False
        and sat.validation_envelope.environment["external_process"]["filesystem_isolation_enforced"] is False
    )

    unsat_obligation = make_obligation(analysis, clauses=[[1], [-1]], variable_count=1, expected=False)
    unsat = make_executor(make_adapter()).execute(
        unsat_obligation, context, adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID
    ).result
    checks["bounded_external_unsat_is_independently_validated"] = bool(
        unsat
        and unsat.decision == VerificationDecision.CONFIRMED
        and unsat.evidence_state == VerificationStatus.VALIDATED
        and unsat.validation_envelope.completeness == ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE
    )

    false_unsat_obligation = make_obligation(analysis, clauses=[[1]], variable_count=1, expected=True)
    false_unsat = make_executor(make_adapter("false-unsat")).execute(
        false_unsat_obligation, context, adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID
    ).result
    checks["false_external_unsat_is_overruled_by_repository_counterexample"] = bool(
        false_unsat
        and false_unsat.decision == VerificationDecision.CONFIRMED
        and false_unsat.evidence_state == VerificationStatus.VALIDATED
        and "external_unsat_refuted_by_independent_model" in false_unsat.diagnostics
    )

    large_unsat_obligation = make_obligation(
        analysis, clauses=[[1], [-1]], variable_count=13, expected=False
    )
    large_unsat = make_executor(make_adapter(unsat_bound=12)).execute(
        large_unsat_obligation, context, adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID
    ).result
    checks["unsupported_large_unsat_remains_observed"] = bool(
        large_unsat
        and large_unsat.evidence_state == VerificationStatus.OBSERVED
        and large_unsat.validation_envelope.completeness == ValidationCompleteness.PARTIAL
    )

    checks["external_solver_not_in_default_adapter_registry"] = (
        builtin_high_assurance_adapter_registry().get(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID) is None
    )
    profile = builtin_profile_catalog().get(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID)
    checks["external_solver_profile_is_metadata_only"] = bool(
        profile
        and profile.execution_mode == ExecutionMode.CONTROLLED_EXTERNAL
        and profile.metadata.get("activation_required") is True
    )
    try:
        from formal.router import FormalRouter
        FormalRouter().route("existence", 1.0, 0.5)
    except NotImplementedError:
        checks["formal_router_remains_inactive"] = True
    else:
        checks["formal_router_remains_inactive"] = False

    for name in (
        "external_process_containment_contract.yaml",
        "external_solver_protocol_contract.yaml",
        "solver_certificate_validation_contract.yaml",
        "controlled_external_cnf_solver_contract.yaml",
    ):
        checks[f"contract_present:{name}"] = bool(
            yaml.safe_load((ROOT / "specs" / "contracts" / name).read_text(encoding="utf-8"))
        )
    for name in (
        "external_process_transcript.schema.json",
        "external_solver_response.schema.json",
        "solver_certificate_validation.schema.json",
    ):
        checks[f"schema_present:{name}"] = bool(
            json.loads((ROOT / "specs" / "schemas" / name).read_text(encoding="utf-8"))
        )
    checks["workflow_16_manual_only"] = "workflow_dispatch" in (
        ROOT / ".github" / "workflows" / "16_semantic_external_solver_validation.yml"
    ).read_text(encoding="utf-8")
    checks["g3_workflows_05_16_manual_only"] = manual_workflows_05_16()

    passed = all(checks.values())
    payload = {
        "milestone": "G3.4.2",
        "validator": "validate_semantic_external_solver.py",
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
        print("G3.4.2 external solver containment and certificate validation passed.")
        return 0
    print("G3.4.2 external solver containment and certificate validation failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

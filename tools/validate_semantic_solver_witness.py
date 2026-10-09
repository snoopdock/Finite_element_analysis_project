#!/usr/bin/env python3
"""Deterministic acceptance validator for G3.4.1."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.high_assurance import (
    AssuranceMechanism,
    BOUNDED_CNF_ADAPTER_ID,
    BOUNDED_CNF_SAT_OBLIGATION,
    BoundedCnfSolverAdapter,
    ControlledHighAssuranceExecutor,
    ExecutableHarnessDescriptor,
    ExecutableHarnessRegistry,
    HighAssuranceAdapterRegistry,
    HighAssurancePolicy,
    REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    REGISTERED_EXECUTABLE_WITNESS_OBLIGATION,
    RegisteredExecutableHarness,
    RegisteredExecutableWitnessAdapter,
    builtin_high_assurance_adapter_registry,
)
from audit_engine.semantic_audit.orchestration import builtin_profile_catalog
from audit_engine.semantic_audit.verification.models import VerificationContext, VerificationObligation


def _analysis():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("a", "Module"))
    graph.add_node(SemanticNode("b", "Module"))
    graph.add_edge(SemanticEdge("a", "b", "DEPENDS_ON"))
    result = SemanticGraphAnalysisService(graph, semantic_context=SemanticContext()).analyze(
        GraphQuery("g341-validation", QueryType.DEPENDENCY, ["a"], {"max_depth": 1})
    )
    return graph, result


def _solver_record(graph, result, *, activated: bool):
    adapters = HighAssuranceAdapterRegistry()
    adapters.register(BoundedCnfSolverAdapter())
    policy = HighAssurancePolicy(
        allowed_mechanisms=(AssuranceMechanism.SOLVER,),
        activated_adapter_ids=((BOUNDED_CNF_ADAPTER_ID,) if activated else ()),
    )
    obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type=BOUNDED_CNF_SAT_OBLIGATION,
        requested_verifier_ids=(BOUNDED_CNF_ADAPTER_ID,),
        parameters={
            "clauses": [[1], [-1, 2]],
            "variable_count": 2,
            "expected_satisfiable": True,
            "timeout_ms": 1000,
        },
    )
    return ControlledHighAssuranceExecutor(adapters, policy=policy).execute(
        obligation, VerificationContext(result, graph), adapter_id=BOUNDED_CNF_ADAPTER_ID
    )


def _witness_record(graph, result):
    harnesses = ExecutableHarnessRegistry()
    harnesses.register(
        RegisteredExecutableHarness(
            ExecutableHarnessDescriptor("double", "1.0.0"),
            lambda values: values["x"] * 2,
        )
    )
    adapters = HighAssuranceAdapterRegistry()
    adapters.register(RegisteredExecutableWitnessAdapter(harnesses))
    policy = HighAssurancePolicy(
        allowed_mechanisms=(AssuranceMechanism.EXECUTABLE_WITNESS,),
        activated_adapter_ids=(REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,),
    )
    obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type=REGISTERED_EXECUTABLE_WITNESS_OBLIGATION,
        requested_verifier_ids=(REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,),
        parameters={
            "harness_id": "double",
            "harness_version": "1.0.0",
            "inputs": {"x": 3},
            "expected_output": 6,
            "timeout_ms": 1000,
        },
    )
    return ControlledHighAssuranceExecutor(adapters, policy=policy).execute(
        obligation,
        VerificationContext(result, graph),
        adapter_id=REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    )


def main() -> int:
    graph, result = _analysis()
    denied = _solver_record(graph, result, activated=False)
    solved = _solver_record(graph, result, activated=True)
    executed = _witness_record(graph, result)
    builtin_ids = {a.descriptor.adapter_id for a in builtin_high_assurance_adapter_registry().adapters()}
    profiles = {p.verifier_id: p for p in builtin_profile_catalog().profiles()}
    formal_router = Path("formal/router.py").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/15_semantic_solver_witness_validation.yml").read_text(encoding="utf-8")
    all_g3_manual = True
    for path in sorted(Path(".github/workflows").glob("*.yml")):
        prefix = path.name.split("_", 1)[0]
        if prefix.isdigit() and 5 <= int(prefix) <= 15:
            text = path.read_text(encoding="utf-8")
            all_g3_manual &= "workflow_dispatch" in text and "push:" not in text and "pull_request:" not in text

    checks = {
        "solver_denied_without_explicit_activation": denied.status.value == "denied" and denied.denial_reason == "adapter_not_explicitly_activated",
        "bounded_solver_executes_when_activated": solved.status.value == "executed" and solved.result is not None,
        "bounded_solver_validates_with_certificate": solved.result is not None and solved.result.evidence_state.value == "validated" and solved.result.witnesses[0].kind.value == "solver_certificate",
        "solver_envelope_is_exhaustive_within_scope": solved.result is not None and solved.result.validation_envelope.completeness.value == "exhaustive_within_scope",
        "executable_witness_executes_registered_harness": executed.status.value == "executed" and executed.result is not None,
        "execution_trace_uses_digests": executed.result is not None and "input_digest" in executed.result.witnesses[0].details and "actual_output_digest" in executed.result.witnesses[0].details,
        "solver_not_in_default_adapter_registry": BOUNDED_CNF_ADAPTER_ID not in builtin_ids,
        "executable_witness_not_in_default_adapter_registry": REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID not in builtin_ids,
        "solver_profile_is_metadata_only": BOUNDED_CNF_ADAPTER_ID in profiles and profiles[BOUNDED_CNF_ADAPTER_ID].method.value == "solver",
        "executable_profile_is_metadata_only": REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID in profiles and profiles[REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID].method.value == "executable",
        "formal_router_remains_inactive": "Formal layer is not yet active" in formal_router,
        "activation_contract_present": Path("specs/contracts/high_assurance_explicit_activation_contract.yaml").exists(),
        "bounded_solver_contract_present": Path("specs/contracts/bounded_cnf_solver_contract.yaml").exists(),
        "executable_witness_contract_present": Path("specs/contracts/registered_executable_witness_contract.yaml").exists(),
        "solver_certificate_contract_present": Path("specs/contracts/solver_certificate_contract.yaml").exists(),
        "workflow_15_manual_only": "workflow_dispatch" in workflow and "push:" not in workflow and "pull_request:" not in workflow,
        "g3_workflows_05_15_manual_only": all_g3_manual,
    }

    artifact = {
        "schema_version": "semantic_solver_witness_validation/v1",
        "milestone": "G3.4.1",
        "checks": checks,
        "solver_execution_id": solved.execution_id,
        "executable_witness_execution_id": executed.execution_id,
    }
    target = Path("artifacts/semantic_solver_witness_validation.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for key, value in checks.items():
        print(f"{key}: {'PASS' if value else 'FAIL'}")
    if not all(checks.values()):
        raise SystemExit("G3.4.1 controlled solver/witness validation failed.")
    print("G3.4.1 controlled solver and executable-witness validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext, VerificationStatus
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.high_assurance import register_builtin_high_assurance_verifiers
from audit_engine.semantic_audit.orchestration import AuditBudget, OrchestrationPolicy, VerificationObjective, build_orchestration_plan, builtin_profile_catalog
from audit_engine.semantic_audit.verification import VerificationDecision, VerificationObligation, VerificationService, VerifierRegistry


def analysis_fixture():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("a", "Module"))
    graph.add_node(SemanticNode("b", "Module"))
    graph.add_edge(SemanticEdge("a", "b", "DEPENDS_ON", metadata={"source_id": "validator"}))
    context = SemanticContext(relationship_vocabulary_version="repo-relations/v1")
    result = SemanticGraphAnalysisService(graph, semantic_context=context).analyze(
        GraphQuery("g340-validator", QueryType.DEPENDENCY, ["a"], {"max_depth": 1})
    )
    return graph, result


def main():
    graph, analysis = analysis_fixture()
    registry = VerifierRegistry()
    executor = register_builtin_high_assurance_verifiers(registry)
    service = VerificationService(registry)

    safe_obligation = VerificationObligation.from_analysis_result(
        analysis,
        obligation_type="python_static_import_constraint",
        requested_verifier_ids=("python-static-import",),
        parameters={"source_text": "import os\nfrom pathlib import Path\n", "forbidden_modules": ["networkx"], "timeout_ms": 1000},
    )
    unsafe_obligation = VerificationObligation.from_analysis_result(
        analysis,
        obligation_type="python_static_import_constraint",
        requested_verifier_ids=("python-static-import",),
        parameters={"source_text": "import networkx as nx\n", "forbidden_modules": ["networkx"], "timeout_ms": 1000},
    )
    content = "semantic-artifact"
    digest_obligation = VerificationObligation.from_analysis_result(
        analysis,
        obligation_type="artifact_digest_match",
        requested_verifier_ids=("artifact-digest-integrity",),
        parameters={"content": content, "expected_sha256": hashlib.sha256(content.encode()).hexdigest(), "timeout_ms": 1000},
    )
    safe_receipt = service.verify(safe_obligation, analysis, semantic_graph=graph)
    unsafe_receipt = service.verify(unsafe_obligation, analysis, semantic_graph=graph)
    digest_receipt = service.verify(digest_obligation, analysis, semantic_graph=graph)
    safe_execution = safe_receipt.details["high_assurance_execution"]

    objective = VerificationObjective.create(
        obligation_id=safe_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=(safe_obligation,),
        objectives=(objective,),
        registry=registry,
        profiles=builtin_profile_catalog(),
        budget=AuditBudget(4, 1),
        policy=OrchestrationPolicy(max_route_length=1),
    )

    workflow_dir = Path(".github/workflows")
    checks = {
        "safe_static_import_confirmed": safe_receipt.decision is VerificationDecision.CONFIRMED,
        "forbidden_static_import_refuted": unsafe_receipt.decision is VerificationDecision.REFUTED,
        "digest_integrity_confirmed": digest_receipt.decision is VerificationDecision.CONFIRMED,
        "validated_static_result_has_witness": bool(safe_execution["result"]["witnesses"]),
        "validation_envelope_is_exhaustive_within_scope": safe_execution["result"]["validation_envelope"]["completeness"] == "exhaustive_within_scope",
        "dynamic_import_limit_is_explicit": any("dynamic imports" in item for item in safe_execution["result"]["validation_envelope"]["excluded_scope"]),
        "raw_source_not_serialized": "from pathlib import Path" not in json.dumps(safe_execution, sort_keys=True),
        "high_assurance_verifier_is_orchestratable": plan.routes[0].actions[0].verifier_id == "python-static-import",
        "static_profile_cost_is_explicit": plan.routes[0].actions[0].cost_units == 4,
        "formal_solver_mechanisms_not_enabled_by_default": all(item.value not in {"solver", "executable_witness", "theorem_prover"} for item in executor.policy.allowed_mechanisms),
        "formal_router_not_imported_by_high_assurance": all("import formal" not in p.read_text(encoding="utf-8") and "from formal" not in p.read_text(encoding="utf-8") for p in Path("audit_engine/semantic_audit/high_assurance").glob("*.py")),
        "verifier_contract_present": Path("specs/contracts/high_assurance_verifier_contract.yaml").exists(),
        "validation_envelope_contract_present": Path("specs/contracts/high_assurance_validation_envelope_contract.yaml").exists(),
        "witness_contract_present": Path("specs/contracts/high_assurance_witness_contract.yaml").exists(),
        "execution_contract_present": Path("specs/contracts/high_assurance_execution_contract.yaml").exists(),
        "policy_contract_present": Path("specs/contracts/controlled_high_assurance_policy_contract.yaml").exists(),
        "workflow_14_manual_only": "on:\n  workflow_dispatch:\n" in Path(".github/workflows/14_semantic_high_assurance_verification_validation.yml").read_text(),
        "g3_workflows_05_14_manual_only": all(
            (lambda text: "on:\n  workflow_dispatch:\n" in text and "\n  push:" not in text and "\n  pull_request:" not in text)(
                next(workflow_dir.glob(f"{n:02d}_*.yml")).read_text()
            ) for n in range(5, 15)
        ),
    }
    for key, value in checks.items():
        print(f"{key}: {'PASS' if value else 'FAIL'}")
    payload = {
        "milestone": "G3.4.0",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "safe_receipt_id": safe_receipt.receipt_id,
        "unsafe_receipt_id": unsafe_receipt.receipt_id,
        "digest_receipt_id": digest_receipt.receipt_id,
        "orchestration_plan_id": plan.plan_id,
    }
    target = Path("artifacts/semantic_high_assurance_verification_validation.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if not all(checks.values()):
        raise SystemExit("G3.4.0 controlled high-assurance verification validation failed.")
    print("G3.4.0 controlled high-assurance verification validation passed.")


if __name__ == "__main__":
    main()

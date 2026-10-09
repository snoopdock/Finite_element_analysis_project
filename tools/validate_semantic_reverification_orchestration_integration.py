from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import AuditLongTermMemory, IncrementalReverificationService, ReverificationReplayCatalog, SemanticGraphEvolutionService
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.integration import OrchestrationIntegrationMemoryRecorder, run_budget_aware_reverification
from audit_engine.semantic_audit.orchestration import AuditBudget, OrchestrationPolicy, builtin_profile_catalog
from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader
from audit_engine.semantic_audit.verification import GraphAttributeConstraintVerifier, VerificationDecision, VerificationService, VerifierRegistry


def graph(*, left="experimental", right="experimental"):
    value = SemanticGraph()
    value.add_node(SemanticNode("prod", "Module", attributes={"lifecycle": "production"}))
    value.add_node(SemanticNode("left", "Module", attributes={"lifecycle": left}))
    value.add_node(SemanticNode("right", "Module", attributes={"lifecycle": right}))
    value.add_edge(SemanticEdge("prod", "left", "DEPENDS_ON", metadata={"source_id": "code:left"}))
    value.add_edge(SemanticEdge("prod", "right", "DEPENDS_ON", metadata={"source_id": "code:right"}))
    return value


def main():
    context = SemanticContext(relationship_vocabulary_version="repo-relations/v1")
    registry = VerifierRegistry(); registry.register(GraphAttributeConstraintVerifier())
    service = VerificationService(registry)
    profiles = builtin_profile_catalog()
    rule = DomainRuleLoader.from_mapping({
        "rule_id": "architecture.no_production_to_experimental_dependency",
        "version": "1",
        "domain": "architecture",
        "obligation_type": "graph_attribute_constraint",
        "verifier_id": "graph-attribute-constraint",
        "title": "Production dependency reaches experimental module",
        "finding_message": "Production code depends on an experimental module.",
        "severity": "critical",
        "selector": {
            "scope": "observation", "predicates": ["DEPENDS_ON"],
            "source_entity_types": ["Module"], "target_entity_types": ["Module"],
        },
        "parameters": {
            "relation_types": ["DEPENDS_ON"],
            "source_attributes": {"lifecycle": "production"},
            "target_attributes": {"lifecycle": "experimental"},
        },
    })
    before = graph()
    analysis = SemanticGraphAnalysisService(before, semantic_context=context).analyze(
        GraphQuery("g332-validator", QueryType.DEPENDENCY, ["prod"], {"max_depth": 1})
    )
    domain = DomainRuleExecutor(service).execute(rule, analysis, before)
    catalog = ReverificationReplayCatalog(); catalog.add_domain_execution(analysis=analysis, rule=rule, execution=domain)
    artifacts = [analysis, *domain.receipts, *domain.findings]
    after = graph(left="stable")
    evolution = SemanticGraphEvolutionService().compare(
        before_graph=before, after_graph=after, before_context=context, artifacts=artifacts
    )
    assessment = IncrementalReverificationService().assess(evolution=evolution, artifacts=artifacts)
    memory = AuditLongTermMemory()
    result = run_budget_aware_reverification(
        evolution=evolution, assessment=assessment, catalog=catalog, after_graph=after,
        verification_service=service, registry=registry, profiles=profiles,
        budget=AuditBudget(4, 2), orchestration_policy=OrchestrationPolicy(max_route_length=1),
    )
    before_memory = len(memory)
    commit = OrchestrationIntegrationMemoryRecorder().record(
        memory=memory, result=result, snapshot_id=evolution.after_snapshot.snapshot_id
    )
    decisions = {receipt.decision for receipt in result.reconciliation.successor_receipts}
    checks = {
        "preparation_bound_to_after_snapshot": result.preparation.after_snapshot_id == evolution.after_snapshot.snapshot_id,
        "receipt_tasks_become_objectives": len(result.preparation.objectives) == 2,
        "requested_verifier_authority_preserved": all(b.requested_verifier_ids == ("graph-attribute-constraint",) for b in result.preparation.bindings),
        "shared_budget_respected": result.session.total_consumed_cost_units <= 4,
        "shared_run_budget_respected": result.session.total_consumed_verifier_runs <= 2,
        "successor_receipts_reconciled": len(result.reconciliation.successor_receipts) == 2,
        "changed_decision_observed": VerificationDecision.REFUTED in decisions and VerificationDecision.CONFIRMED in decisions,
        "no_unresolved_receipt_tasks": result.reconciliation.unresolved_task_ids == (),
        "execution_has_no_implicit_memory_side_effect": before_memory == 0,
        "explicit_memory_commit_records_artifacts": len(memory) > 0 and bool(commit.record_ids),
        "bridge_contract_present": Path("specs/contracts/semantic_reverification_orchestration_bridge_contract.yaml").exists(),
        "reconciliation_contract_present": Path("specs/contracts/semantic_orchestration_reconciliation_contract.yaml").exists(),
        "memory_contract_present": Path("specs/contracts/semantic_orchestration_memory_commit_contract.yaml").exists(),
        "combined_result_contract_present": Path("specs/contracts/semantic_budget_aware_reverification_contract.yaml").exists(),
        "workflow_13_manual_only": "on:\n  workflow_dispatch:\n" in Path(".github/workflows/13_semantic_reverification_orchestration_integration_validation.yml").read_text(),
    }
    workflow_dir = Path(".github/workflows")
    checks["g3_workflows_05_13_manual_only"] = all(
        (lambda text: "on:\n  workflow_dispatch:\n" in text and "\n  push:" not in text and "\n  pull_request:" not in text)(
            next(workflow_dir.glob(f"{n:02d}_*.yml")).read_text()
        ) for n in range(5, 14)
    )
    for key, value in checks.items():
        print(f"{key}: {'PASS' if value else 'FAIL'}")
    payload = {
        "milestone": "G3.3.2",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "result_id": result.result_id,
        "preparation_id": result.preparation.preparation_id,
        "session_id": result.session.session_id,
        "reconciliation_id": result.reconciliation.reconciliation_id,
        "memory_record_count": len(memory),
    }
    target = Path("artifacts/semantic_reverification_orchestration_integration_validation.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if not all(checks.values()):
        raise SystemExit("G3.3.2 semantic re-verification orchestration integration validation failed.")
    print("G3.3.2 semantic re-verification orchestration integration validation passed.")


if __name__ == "__main__":
    main()

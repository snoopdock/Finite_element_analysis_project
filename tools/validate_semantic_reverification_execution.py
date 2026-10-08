#!/usr/bin/env python3
"""Deterministic G3.2.2 acceptance artifact generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import (
    AuditLongTermMemory,
    IncrementalReverificationExecutor,
    IncrementalReverificationService,
    ReconciliationDisposition,
    ReverificationExecutionMemoryRecorder,
    ReverificationReplayCatalog,
    SemanticGraphEvolutionService,
    TaskExecutionStatus,
)
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader
from audit_engine.semantic_audit.verification import (
    GraphAttributeConstraintVerifier,
    VerificationDecision,
    VerificationService,
    VerifierRegistry,
)


def graph(target_lifecycle="experimental", include_edge=True):
    value = SemanticGraph()
    value.add_node(SemanticNode("prod", "Module", attributes={"lifecycle": "production"}))
    value.add_node(SemanticNode("exp", "Module", attributes={"lifecycle": target_lifecycle}))
    if include_edge:
        value.add_edge(SemanticEdge("prod", "exp", "DEPENDS_ON", metadata={"source_id": "code:1"}))
    return value


def service():
    registry = VerifierRegistry()
    registry.register(GraphAttributeConstraintVerifier())
    return VerificationService(registry)


def rule():
    return DomainRuleLoader.from_mapping({
        "rule_id": "architecture.no_production_to_experimental_dependency",
        "version": "1",
        "domain": "architecture",
        "obligation_type": "graph_attribute_constraint",
        "verifier_id": "graph-attribute-constraint",
        "title": "Forbidden dependency",
        "finding_message": "Production depends on experimental.",
        "severity": "critical",
        "selector": {"scope": "observation", "predicates": ["DEPENDS_ON"]},
        "parameters": {
            "relation_types": ["DEPENDS_ON"],
            "source_attributes": {"lifecycle": "production"},
            "target_attributes": {"lifecycle": "experimental"},
        },
    })


def prior_chain(context):
    before = graph()
    analysis = SemanticGraphAnalysisService(before, semantic_context=context).analyze(
        GraphQuery("g322-validation", QueryType.DEPENDENCY, ["prod"], {"max_depth": 1})
    )
    policy = rule()
    domain = DomainRuleExecutor(service()).execute(policy, analysis, before)
    catalog = ReverificationReplayCatalog()
    catalog.add_domain_execution(analysis=analysis, rule=policy, execution=domain)
    artifacts = [analysis, *domain.receipts, *domain.findings]
    return before, analysis, policy, domain, catalog, artifacts


def execute_transition(context, after, prior):
    before, _, _, _, catalog, artifacts = prior
    evolution = SemanticGraphEvolutionService().compare(
        before_graph=before,
        after_graph=after,
        before_context=context,
        artifacts=artifacts,
    )
    assessment = IncrementalReverificationService().assess(
        evolution=evolution,
        artifacts=artifacts,
    )
    execution = IncrementalReverificationExecutor(service()).execute(
        evolution=evolution,
        assessment=assessment,
        catalog=catalog,
        after_graph=after,
    )
    return evolution, assessment, execution


def run_validation(output_path: Path):
    context = SemanticContext(relationship_vocabulary_version="repo-relations/v1")
    prior = prior_chain(context)
    old_finding = prior[3].findings[0]

    memory = AuditLongTermMemory()
    evolution, assessment, changed = execute_transition(
        context, graph(target_lifecycle="stable"), prior
    )
    before_memory = len(memory)
    receipt = changed.receipts[0]
    finding_task = next(item for item in changed.task_executions if item.artifact_type == "finding")

    removed_evolution, _, removed = execute_transition(context, graph(include_edge=False), prior)
    removed_receipt = next(item for item in removed.task_executions if item.artifact_type == "verification_receipt")

    commit = ReverificationExecutionMemoryRecorder().record(
        memory=memory,
        result=changed,
        snapshot_id=evolution.after_snapshot.snapshot_id,
    )

    repeat = execute_transition(context, graph(target_lifecycle="stable"), prior)[2]

    checks = {
        "plan_contains_dependency_ordered_work": len(assessment.reverification_plan.tasks) == 3,
        "execution_succeeds": changed.succeeded,
        "receipt_decision_changes_after_attribute_change": receipt.decision is VerificationDecision.REFUTED,
        "finding_is_not_reproduced": finding_task.reconciliation.disposition is ReconciliationDisposition.FINDING_NOT_TRIGGERED,
        "historical_finding_lifecycle_is_unchanged": old_finding.lifecycle_status.value == "open",
        "removed_target_is_not_applicable": removed_receipt.status is TaskExecutionStatus.NOT_APPLICABLE,
        "executor_has_no_implicit_memory_side_effect": before_memory == 0,
        "explicit_memory_commit_records_execution": bool(memory.records_for_artifact("reverification_execution", changed.execution_id)),
        "memory_commit_bound_to_after_snapshot": commit.snapshot_id == evolution.after_snapshot.snapshot_id,
        "execution_identity_is_deterministic": repeat.execution_id == changed.execution_id,
        "execution_contract_present": Path("specs/contracts/semantic_reverification_execution_contract.yaml").is_file(),
        "reconciliation_contract_present": Path("specs/contracts/semantic_artifact_reconciliation_contract.yaml").is_file(),
        "replay_contract_present": Path("specs/contracts/semantic_replay_contract.yaml").is_file(),
        "execution_memory_contract_present": Path("specs/contracts/semantic_reverification_execution_memory_contract.yaml").is_file(),
    }

    payload = {
        "schema_version": "semantic_reverification_execution_validation/v1",
        "checks": checks,
        "passed": all(checks.values()),
        "execution": changed.to_dict(),
        "removed_target_execution": removed.to_dict(),
        "memory_commit": commit.to_dict(),
        "after_snapshot_id": evolution.after_snapshot.snapshot_id,
        "removed_after_snapshot_id": removed_evolution.after_snapshot.snapshot_id,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if not payload["passed"]:
        return 1
    print("G3.2.2 incremental re-verification execution validation passed.")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="artifacts/semantic_reverification_execution_validation.json",
    )
    args = parser.parse_args()
    return run_validation(Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())

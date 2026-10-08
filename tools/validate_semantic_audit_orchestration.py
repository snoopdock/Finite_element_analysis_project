"""Generate deterministic G3.3.0 orchestration acceptance evidence."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.orchestration import (
    AuditBudget,
    ExecutionMode,
    ObjectiveExecutionStatus,
    OrchestrationPolicy,
    RoutePlanningStatus,
    VerificationMethod,
    VerificationObjective,
    VerifierOrchestrationProfile,
    VerifierProfileCatalog,
    build_orchestration_plan,
    execute_orchestration_plan,
)
from audit_engine.semantic_audit.verification import (
    VerificationAttempt,
    VerificationDecision,
    VerificationObligation,
    VerificationService,
    VerifierDescriptor,
    VerifierRegistry,
)


class CheapInconclusive:
    descriptor = VerifierDescriptor("validator-cheap", "1.0.0", ("observation_contract",))

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=VerificationDecision.INCONCLUSIVE,
            evidence_state=VerificationStatus.INCONCLUSIVE,
            evidence_ids=obligation.evidence_ids,
        )


class ExpensiveValidated:
    descriptor = VerifierDescriptor("validator-expensive", "1.0.0", ("observation_contract",))

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=VerificationDecision.CONFIRMED,
            evidence_state=VerificationStatus.VALIDATED,
            evidence_ids=obligation.evidence_ids,
        )


def main() -> None:
    graph = SemanticGraph()
    graph.add_node(SemanticNode("A", "Module"))
    graph.add_node(SemanticNode("B", "Module"))
    graph.add_edge(SemanticEdge("A", "B", "DEPENDS_ON", metadata={"source_id": "validator"}))
    analysis = SemanticGraphAnalysisService(graph).analyze(
        GraphQuery("g330-validator", QueryType.DEPENDENCY, ["A"], {"max_depth": 1})
    )
    obligation = VerificationObligation.from_analysis_result(
        analysis,
        obligation_type="observation_contract",
        parameters={"subject_id": "A", "predicate": "DEPENDS_ON", "object_id": "B"},
    )
    objective = VerificationObjective.create(
        obligation_id=obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )

    registry = VerifierRegistry()
    registry.register(CheapInconclusive())
    registry.register(ExpensiveValidated())
    profiles = VerifierProfileCatalog()
    profiles.register(
        VerifierOrchestrationProfile(
            "validator-cheap", "1.0.0", VerificationMethod.CONTRACT, 1,
            VerificationStatus.VALIDATED,
        )
    )
    profiles.register(
        VerifierOrchestrationProfile(
            "validator-expensive", "1.0.0", VerificationMethod.CONTRACT, 5,
            VerificationStatus.VALIDATED,
        )
    )
    budget = AuditBudget(6, 2)
    plan = build_orchestration_plan(
        obligations=[obligation], objectives=[objective], registry=registry,
        profiles=profiles, budget=budget,
    )
    execution = execute_orchestration_plan(
        plan=plan,
        obligations={obligation.obligation_id: obligation},
        analysis_results={analysis.analysis_id: analysis},
        semantic_graphs={analysis.analysis_id: graph},
        verification_service=VerificationService(registry),
    )

    unprofiled = VerifierProfileCatalog()
    unprofiled_plan = build_orchestration_plan(
        obligations=[obligation], objectives=[objective], registry=registry,
        profiles=unprofiled, budget=AuditBudget(10, 10),
    )

    sandbox_profiles = VerifierProfileCatalog()
    sandbox_profiles.register(
        VerifierOrchestrationProfile(
            "validator-cheap", "1.0.0", VerificationMethod.CONTRACT, 1,
            VerificationStatus.VALIDATED, execution_mode=ExecutionMode.SANDBOXED,
        )
    )
    denied_sandbox = build_orchestration_plan(
        obligations=[obligation], objectives=[objective], registry=registry,
        profiles=sandbox_profiles, budget=AuditBudget(10, 10),
    )

    second_plan = build_orchestration_plan(
        obligations=[obligation], objectives=[objective], registry=registry,
        profiles=profiles, budget=budget,
    )
    second_execution = execute_orchestration_plan(
        plan=second_plan,
        obligations={obligation.obligation_id: obligation},
        analysis_results={analysis.analysis_id: analysis},
        semantic_graphs={analysis.analysis_id: graph},
        verification_service=VerificationService(registry),
    )

    objective_result = execution.objective_results[0]
    checks = {
        "least_cost_primary_selected": plan.routes[0].actions[0].verifier_id == "validator-cheap",
        "bounded_fallback_reserved": [a.verifier_id for a in plan.routes[0].actions] == [
            "validator-cheap", "validator-expensive"
        ],
        "plan_respects_cost_budget": plan.reserved_cost_units <= budget.total_cost_units,
        "plan_respects_run_budget": plan.reserved_verifier_runs <= budget.max_verifier_runs,
        "inconclusive_primary_falls_back": len(objective_result.actions) == 2,
        "fallback_satisfies_objective": objective_result.status is ObjectiveExecutionStatus.SATISFIED,
        "execution_respects_cost_budget": execution.consumed_cost_units <= budget.total_cost_units,
        "execution_respects_run_budget": execution.consumed_verifier_runs <= budget.max_verifier_runs,
        "unprofiled_verifier_gets_no_implicit_cost": unprofiled_plan.routes[0].status is RoutePlanningStatus.UNSCHEDULED_POLICY,
        "sandbox_requires_explicit_permission": denied_sandbox.routes[0].status is RoutePlanningStatus.UNSCHEDULED_POLICY,
        "execution_has_no_findings_side_effect": "findings" not in execution.to_dict(),
        "execution_has_no_memory_side_effect": "memory" not in execution.to_dict(),
        "plan_identity_is_deterministic": plan.plan_id == second_plan.plan_id,
        "execution_identity_is_deterministic": execution.execution_id == second_execution.execution_id,
        "orchestration_contract_present": Path("specs/contracts/semantic_audit_orchestration_contract.yaml").is_file(),
        "resource_profile_contract_present": Path("specs/contracts/verification_resource_profile_contract.yaml").is_file(),
        "budget_contract_present": Path("specs/contracts/audit_budget_contract.yaml").is_file(),
        "execution_contract_present": Path("specs/contracts/orchestration_execution_contract.yaml").is_file(),
    }

    artifact = {
        "schema_version": "semantic_audit_orchestration_validation/v1",
        "milestone": "G3.3.0",
        "checks": checks,
        "plan": plan.to_dict(),
        "execution": execution.to_dict(),
    }
    out = Path("artifacts/semantic_audit_orchestration_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if not all(checks.values()):
        raise SystemExit("G3.3.0 semantic audit orchestration validation failed.")
    print("G3.3.0 semantic audit orchestration validation passed.")


if __name__ == "__main__":
    main()

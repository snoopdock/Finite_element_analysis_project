"""Generate deterministic G3.3.1 adaptive orchestration acceptance evidence."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.orchestration import (
    AdaptiveSessionStatus, AuditBudget, OrchestrationPolicy, VerificationMethod,
    VerificationObjective, VerifierOrchestrationProfile, VerifierProfileCatalog,
    build_orchestration_plan, run_adaptive_orchestration,
)
from audit_engine.semantic_audit.verification import (
    VerificationAttempt, VerificationDecision, VerificationObligation, VerificationService,
    VerifierDescriptor, VerifierRegistry,
)

class CheapInconclusive:
    descriptor = VerifierDescriptor("adaptive-cheap", "1.0.0", ("observation_contract",))
    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id, verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version, decision=VerificationDecision.INCONCLUSIVE,
            evidence_state=VerificationStatus.INCONCLUSIVE, evidence_ids=obligation.evidence_ids,
        )

class ExpensiveValidated:
    descriptor = VerifierDescriptor("adaptive-expensive", "1.0.0", ("observation_contract",))
    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id, verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version, decision=VerificationDecision.CONFIRMED,
            evidence_state=VerificationStatus.VALIDATED, evidence_ids=obligation.evidence_ids,
        )

def main():
    graph = SemanticGraph(); graph.add_node(SemanticNode("A","Module")); graph.add_node(SemanticNode("B","Module"))
    graph.add_edge(SemanticEdge("A","B","DEPENDS_ON", metadata={"source_id":"g331-validator"}))
    analysis = SemanticGraphAnalysisService(graph).analyze(GraphQuery("g331", QueryType.DEPENDENCY,["A"],{"max_depth":1}))
    obligation = VerificationObligation.from_analysis_result(
        analysis, obligation_type="observation_contract",
        parameters={"subject_id":"A","predicate":"DEPENDS_ON","object_id":"B"},
    )
    objective = VerificationObjective.create(
        obligation_id=obligation.obligation_id, minimum_evidence_state=VerificationStatus.VALIDATED
    )
    registry=VerifierRegistry(); registry.register(CheapInconclusive()); registry.register(ExpensiveValidated())
    profiles=VerifierProfileCatalog()
    profiles.register(VerifierOrchestrationProfile("adaptive-cheap","1.0.0",VerificationMethod.CONTRACT,1,VerificationStatus.VALIDATED))
    profiles.register(VerifierOrchestrationProfile("adaptive-expensive","1.0.0",VerificationMethod.CONTRACT,5,VerificationStatus.VALIDATED))
    policy=OrchestrationPolicy(max_route_length=1)
    initial=build_orchestration_plan(
        obligations=[obligation], objectives=[objective], registry=registry, profiles=profiles,
        budget=AuditBudget(6,2), policy=policy,
    )
    kwargs=dict(
        initial_plan=initial, obligations={obligation.obligation_id:obligation},
        analysis_results={analysis.analysis_id:analysis}, verification_service=VerificationService(registry),
        registry=registry, profiles=profiles, semantic_graphs={analysis.analysis_id:graph}, orchestration_policy=policy,
    )
    session=run_adaptive_orchestration(**kwargs); second=run_adaptive_orchestration(**kwargs)
    wf_names=[f"{i:02d}_" for i in range(5,13)]
    workflows=list((ROOT/".github/workflows").glob("*.yml"))
    selected=[p for p in workflows if any(p.name.startswith(prefix) for prefix in wf_names)]
    manual_only=all("on:\n  workflow_dispatch:\n" in p.read_text() and "\n  push:" not in p.read_text() and "\n  pull_request:" not in p.read_text() for p in selected)
    replan=session.replans[0]
    attempted_first=session.executions[0].objective_results[0].actions[0].verifier_id
    selected_second=replan.continuation_plan.routes[0].actions[0].verifier_id if replan.continuation_plan else None
    checks={
        "initial_plan_uses_one_bounded_action": initial.reserved_verifier_runs == 1,
        "inconclusive_outcome_triggers_replan": len(session.replans) == 1,
        "replan_excludes_attempted_verifier": attempted_first != selected_second,
        "continuation_uses_explicit_unattempted_verifier": selected_second == "adaptive-expensive",
        "session_satisfies_objective": session.status is AdaptiveSessionStatus.SATISFIED,
        "cumulative_cost_respects_original_budget": session.total_consumed_cost_units <= initial.budget.total_cost_units,
        "cumulative_runs_respect_original_budget": session.total_consumed_verifier_runs <= initial.budget.max_verifier_runs,
        "session_has_no_findings_side_effect": "findings" not in session.to_dict(),
        "session_has_no_memory_side_effect": "memory" not in session.to_dict(),
        "session_identity_is_deterministic": session.session_id == second.session_id,
        "replan_identity_is_deterministic": session.replans[0].replan_id == second.replans[0].replan_id,
        "adaptive_replanning_contract_present": (ROOT/"specs/contracts/semantic_adaptive_replanning_contract.yaml").is_file(),
        "adaptive_session_contract_present": (ROOT/"specs/contracts/semantic_adaptive_orchestration_session_contract.yaml").is_file(),
        "manual_workflow_contract_present": (ROOT/"specs/contracts/manual_g3_validation_workflow_contract.yaml").is_file(),
        "g3_workflows_are_manual_only": manual_only and len(selected) == 8,
    }
    artifact={"schema_version":"semantic_adaptive_orchestration_validation/v1","milestone":"G3.3.1","checks":checks,"initial_plan":initial.to_dict(),"session":session.to_dict()}
    out=ROOT/"artifacts/semantic_adaptive_orchestration_validation.json"; out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(artifact,indent=2,sort_keys=True)+"\n")
    for name, passed in checks.items(): print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if not all(checks.values()): raise SystemExit("G3.3.1 adaptive orchestration validation failed.")
    print("G3.3.1 adaptive orchestration validation passed.")
if __name__ == "__main__": main()

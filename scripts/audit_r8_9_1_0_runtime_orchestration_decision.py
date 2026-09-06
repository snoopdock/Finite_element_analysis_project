from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DECISION_PATH = Path(__file__).resolve().parents[1] / "specs/decisions/R8.9.1.0_research_planning_runtime_orchestration_decision.yaml"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def norm(value: Any) -> str:
    return str(value).lower().replace("-", "_").replace(" ", "_")


def contains_all(values: list[Any], required: set[str]) -> bool:
    normalized = {norm(v) for v in values}
    return required.issubset(normalized)


def main() -> None:
    if not DECISION_PATH.exists():
        fail(f"decision file not found: {DECISION_PATH}")

    data = yaml.safe_load(DECISION_PATH.read_text(encoding="utf-8"))
    require(isinstance(data, dict), "decision YAML root must be a mapping")
    checks = 0

    # 1. Authority ownership.
    auth = data.get("authority_separation")
    require(isinstance(auth, dict), "missing authority_separation")
    runtime = auth.get("runtime_orchestration", {})
    require(norm(runtime.get("authority_type")) == "composition_only", "runtime authority must be composition_only")
    require(contains_all(runtime.get("owns", []), {
        "sequencing", "delegation", "batch cardinality", "composition-level preconditions",
        "operational error propagation", "provenance preservation across composed boundaries",
    }), "runtime ownership set is incomplete")
    require(contains_all(runtime.get("does_not_own", []), {
        "planning semantics", "acquisition semantics", "retrieval semantics", "evidence semantics",
        "lifecycle semantics", "scientific semantics", "persistence semantics",
    }), "runtime non-ownership set is incomplete")
    for key in ("research_planning_translation", "research_planning_evaluation", "acquisition_request_formulation", "acquisition_execution"):
        require(key in auth, f"missing authority declaration: {key}")
    checks += 1

    # 2. Directionality.
    sequence = data.get("composition_sequence", {}).get("per_input", [])
    require(sequence == [
        "AttentionProposal",
        "ResearchPlanningSignal",
        "ResearchPlanningDecision",
        "AcquisitionRequest_if_applicable",
    ], "composition sequence is not the required semantic direction")
    checks += 1

    # 3. Cardinality.
    card = data.get("cardinality", {})
    require(norm(card.get("input", {}).get("AttentionProposal", {}).get("cardinality")) == "many", "input cardinality must be many")
    require(norm(card.get("output", {}).get("ResearchPlanningDecision", {}).get("cardinality")) == "one_per_input", "decision cardinality must be one_per_input")
    require(norm(card.get("output", {}).get("AcquisitionRequest", {}).get("cardinality")) == "zero_or_more", "request cardinality must be zero_or_more")
    constraints = {norm(v) for v in card.get("constraints", [])}
    require(any("one_attentionproposal_produces_at_most_one_researchplanningsignal" in v for v in constraints), "missing proposal-to-signal cardinality constraint")
    require(any("one_researchplanningsignal_produces_one_researchplanningdecision" in v for v in constraints), "missing signal-to-decision cardinality constraint")
    require(any("only_decision_type_formulate_acquisition_request_may_produce_an_acquisitionrequest" in v for v in constraints), "missing decision-to-request routing constraint")
    checks += 1

    # 4. Batch independence.
    batch = data.get("batch_semantics", {})
    require(norm(batch.get("mode")) == "independent", "batch mode must be independent")
    batch_text = " ".join(str(batch.get(k, "")) for k in ("rule", "rationale", "failure_isolation")).lower()
    require("must not merge" in batch_text, "batch semantics must prohibit merging")
    require("operational failure" in batch_text, "batch failure isolation must be explicit")
    checks += 1

    # 5. Decision-type routing and no-op semantics.
    types = {norm(v) for v in data.get("error_handling", {}).get("domain_decision_types_owned_by_planner", [])}
    require(types == {"no_action", "defer", "prioritize_research", "formulate_acquisition_request"}, "planner decision vocabulary is incomplete or altered")
    no_op = data.get("no_op_semantics", {})
    no_op_text = " ".join(str(v) for v in no_op.values()).lower()
    normalized_no_op_text = norm(no_op_text)
    require(
        "no_separate_no_op_object" in normalized_no_op_text
        or "does_not_create_a_separate_no_op_object" in normalized_no_op_text,
        "no-op semantics must not introduce a new semantic object",
    )
    require("only formulate_acquisition_request" in no_op_text, "request routing condition is missing")
    checks += 1

    # 6. Provenance preservation.
    prov = data.get("provenance_preservation", {})
    require(prov.get("chain", []) == [
        "AttentionProposal.id",
        "ResearchPlanningSignal.source_attention_proposal_id",
        "ResearchPlanningDecision.id",
        "AcquisitionRequest.origin.research_planning_decision_id",
    ], "provenance chain is incomplete or reordered")
    prov_text = " ".join(str(v) for v in prov.get("requirements", [])).lower()
    require("do not replace an upstream identity" in prov_text, "identity preservation rule is missing")
    require("scalar acquisition_request_id" in prov_text, "EvidenceRecord tracing prohibition is missing")
    checks += 1

    # 7. Failure separation.
    errors = data.get("error_handling", {})
    err_rules = " ".join(str(v) for v in errors.get("rules", [])).lower()
    require("runtime failures are operational failures" in str(errors.get("principle", "")).lower(), "runtime/domain failure distinction is missing")
    require("do not create rejecteddecision" in err_rules, "runtime must not synthesize rejected decisions")
    require("do not silently convert an exception into no_action" in err_rules, "exception-to-no_action prohibition is missing")
    require("do not silently retry" in err_rules, "hidden retry prohibition is missing")
    checks += 1

    # 8. Statelessness.
    state = data.get("statelessness", {})
    require(state.get("required") is True, "statelessness must be required")
    require({
        "runtime_state", "runtime_history", "pending_requests", "persisted_decisions", "implicit_retry_state",
    }.issubset({norm(v) for v in state.get("prohibited_members", [])}), "statelessness prohibitions are incomplete")
    checks += 1

    # 9. Boundary exclusions.
    scope = data.get("runtime_scope", {})
    excluded = {norm(v) for v in scope.get("excluded", [])}
    required_exclusions = {
        "retrieval_execution", "provider_selection", "provider_failover_policy", "evidence_storage",
        "retrievalevent_creation_or_mutation", "lifecycle_mutation", "scientific_state_mutation",
        "acquisitionrequest_persistence", "acquisitionexecutionreceipt_persistence",
        "creation_or_reconstruction_of_acquisitionexecutionreceipt", "modification_of_evidencerecord_semantics",
        "merging_of_independent_planning_decisions", "automatic_scheduling", "hidden_retries",
        "new_scientific_or_planning_semantic_objects",
    }
    require(required_exclusions.issubset(excluded), "runtime exclusion set is incomplete")
    adapter = data.get("adapter_boundary", {})
    require("AcquisitionAdapter" in str(adapter.get("downstream_owner")), "adapter downstream ownership is missing")
    require("does not execute" in str(adapter.get("R8_9_1_role", "")).lower(), "R8.9.1 execution exclusion is missing")
    checks += 1

    # 10. Non-expansion invariant.
    nonexp = data.get("non_expansion_invariant", {})
    require({
        "sequencing", "delegation", "batch_cardinality", "operational_error_propagation",
        "provenance_preservation", "composition_level_preconditions",
    }.issubset({norm(v) for v in nonexp.get("may_define", [])}), "composition may_define set is incomplete")
    require({
        "new_planning_semantics", "new_acquisition_semantics", "new_evidence_semantics",
        "new_scientific_semantics", "new_lifecycle_semantics", "new_persistence_semantics",
    }.issubset({norm(v) for v in nonexp.get("may_not_define", [])}), "non-expansion prohibition set is incomplete")
    checks += 1

    # 11. Implementation boundary and closure criteria.
    impl = data.get("implementation_boundary", {})
    require(norm(impl.get("planned_module")) == "core/research_planning_runtime.py", "planned runtime module changed unexpectedly")
    require(norm(impl.get("planned_entry_point")) == "compose_research_acquisition_flow", "planned runtime entry point changed unexpectedly")
    expected_constraints = {
        "pure/stateless orchestration", "reuse existing authorities rather than duplicating their rules",
        "no hidden network activity", "no llm calls", "no lifecycle mutation", "no scientific-state mutation",
        "no persistence", "no implicit adapter execution", "no cross-input merging",
    }
    require(expected_constraints.issubset({str(v).lower() for v in impl.get("implementation_constraints", [])}), "implementation constraints are incomplete")

    closure = data.get("closure_criteria")
    require(isinstance(closure, dict) and closure, "closure_criteria section is missing")
    for key in ("ownership", "responsibilities", "invariants", "implementation", "verification", "ambiguity"):
        entry = closure.get(key)
        require(isinstance(entry, dict) and entry.get("required") is True, f"closure criterion missing/disabled: {key}")
        require(str(entry.get("description", "")).strip(), f"closure criterion lacks description: {key}")
    checks += 1

    # 12. Decision/method status.
    require(norm(data.get("status")) == "accepted", "decision must be accepted before implementation")
    method_alignment = data.get("method_alignment")
    meta_method = data.get("meta_method_freeze")
    method_identity = " ".join(
        str(value)
        for value in (method_alignment.values() if isinstance(method_alignment, dict) else [])
    ).lower()
    finite_procedure = (
        isinstance(meta_method, dict)
        and norm(meta_method.get("status")) == "frozen"
        and len(meta_method.get("finite_procedure", [])) >= 5
        and any("closure" in str(value).lower() for value in meta_method.get("finite_procedure", []))
    )
    require(
        "arch.1_context_first_semantic_restructuring_method" in method_identity or finite_procedure,
        "authoritative method alignment or frozen finite meta-method is missing or altered",
    )
    checks += 1

    print(f"R8.9.1.0 runtime orchestration decision audit: PASS ({checks}/{checks} checks passed)")
    print("Decision closure: eligible to proceed to R8.9.1 implementation; implementation and behavioral verification remain separate closure evidence.")


if __name__ == "__main__":
    main()

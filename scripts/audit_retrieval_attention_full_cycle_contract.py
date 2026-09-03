#!/usr/bin/env python3
"""Audit the R7C.6 full-cycle retrieval-attention integration contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_full_cycle_contract.yaml"
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "R7C.6 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_full_cycle_contract",
        "Unexpected R7C.6 contract name.",
    )

    dependencies = contract["dependencies"]
    check(
        dependencies["attention_context"]["name"] == "retrieval_attention_context",
        "R7C.6 must depend on R7A context construction.",
    )
    check(
        dependencies["attention_policy"]["name"] == "retrieval_attention_policy",
        "R7C.6 must depend on the R7B policy layer.",
    )
    check(
        dependencies["attention_proposal"]["name"] == "retrieval_attention_proposal_contract",
        "R7C.6 must use the R7B.5 proposal boundary.",
    )
    check(
        dependencies["attention_persistence"]["name"] == "retrieval_attention_persistence_contract",
        "R7C.6 must use the R7C persistence boundary.",
    )

    cycle = contract["cycle_boundary"]
    check(
        cycle["ordered_stages"]
        == [
            "retrieve_history_input",
            "build_r7a_context",
            "evaluate_r7b_policy",
            "persist_r7c_proposals",
        ],
        "R7C.6 cycle ordering is incomplete or unexpected.",
    )
    cycle_rules = "\n".join(str(rule) for rule in cycle["rules"])
    check("does not perform retrieval" in cycle_rules, "Full-cycle audit must remain offline.")
    check("No stage executes a recommended acquisition action." in cycle_rules, "Action execution must remain outside R7C.6.")
    check("No stage modifies scientific state." in cycle_rules, "Scientific mutation must remain outside R7C.6.")

    isolation = contract["scientific_isolation"]
    protected = set(isolation["protected_fields"])
    check(
        {
            "propositions",
            "evidence_relations",
            "epistemic_state",
            "evidence_strength",
            "truth_status",
            "ranking",
            "convergence",
            "writing_content",
            "knowledge_base",
            "sections",
        }
        <= protected,
        "Protected scientific fields are incomplete.",
    )
    isolation_rules = "\n".join(str(rule) for rule in isolation["rules"])
    check("must be byte-for-byte equivalent" in isolation_rules, "Scientific-state fidelity rule is missing.")
    check("must not create or mutate the attention-history container" in isolation_rules, "No-attention state rule is missing.")

    attention_state = contract["attention_state_rules"]
    proposal_rules = "\n".join(str(rule) for rule in attention_state["proposal_generation"])
    check("same cycle input" in proposal_rules, "Proposal provenance must remain tied to the cycle input.")
    check("lifecycle_status open" in proposal_rules, "New proposals must begin open.")
    no_attention_rules = "\n".join(str(rule) for rule in attention_state["no_attention"])
    check("zero attention items" in no_attention_rules, "No-attention behavior is missing.")
    idempotency_rules = "\n".join(str(rule) for rule in attention_state["idempotency"])
    check("must not create a duplicate proposal" in idempotency_rules, "Duplicate protection is missing.")
    check("generated_at" in idempotency_rules, "Duplicate persistence must preserve generated_at.")

    reproducibility = contract["reproducibility"]
    check(
        set(reproducibility["deterministic_core"])
        == {
            "attention_id",
            "policy_version",
            "query_scope",
            "provider",
            "attention_reason",
            "observed_condition",
            "lifecycle_status",
            "supporting_event_ids",
            "recommended_acquisition_action",
        },
        "Deterministic proposal core is incomplete or unexpected.",
    )
    reproducibility_rules = "\n".join(str(rule) for rule in reproducibility["rules"])
    check("same retrieval history" in reproducibility_rules, "Reproducibility must depend on retrieval history.")
    check("generated_at" in reproducibility_rules, "Persistence timestamp boundary is missing.")
    check("preserve the original persisted proposal and timestamp" in reproducibility_rules, "Duplicate timestamp preservation is missing.")

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited"])
        == {
            "automatic_action_execution",
            "lifecycle_transition",
            "retrieval_history_mutation",
            "scientific_state_mutation",
        },
        "Execution boundary is incomplete or unexpected.",
    )
    check(
        "new retrieval-history events" in execution["required_future_loop"],
        "Future action execution must return through new retrieval events.",
    )

    scope = contract["scope"]
    excluded = set(scope["excluded"])
    check("network retrieval" in excluded, "Network retrieval must remain excluded.")
    check("action execution" in excluded, "Action execution must remain excluded.")
    check("lifecycle transitions" in excluded, "Lifecycle transitions must remain excluded.")
    check("epistemic inference" in excluded, "Epistemic inference must remain excluded.")

    print("R7C.6 retrieval attention full-cycle contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

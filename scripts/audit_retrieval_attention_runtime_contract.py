#!/usr/bin/env python3
"""Audit the R7C.7 live retrieval-attention runtime boundary contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "specs" / "contracts" / "retrieval_attention_runtime_contract.yaml"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "R7C.7 runtime contract version must be 1.")
    check(contract["name"] == "retrieval_attention_runtime_contract", "Unexpected R7C.7 runtime contract name.")

    deps = contract["dependencies"]
    check(deps["pipeline_adapter"]["name"] == "retrieval_attention_pipeline", "Runtime must delegate to R7C.5 pipeline adapter.")
    check(deps["proposal_persistence"]["name"] == "retrieval_attention_persistence_contract", "Runtime must use R7C persistence.")
    check(deps["full_cycle_contract"]["name"] == "retrieval_attention_full_cycle_contract", "Runtime must inherit R7C.6 boundary.")

    boundary = contract["runtime_boundary"]
    check("after the current retrieval event has been appended" in boundary["invocation_point"]["rule"], "Runtime invocation must occur after retrieval-history append.")
    rules = "\n".join(str(rule) for rule in boundary["rules"])
    check("must not perform retrieval" in rules, "Runtime must not perform retrieval.")
    check("must not execute recommended acquisition actions" in rules, "Runtime must not execute actions.")
    check("must not transition proposal lifecycle state" in rules, "Runtime must not transition lifecycle.")

    policy = contract["policy_configuration"]
    check(
        policy["required_fields"]
        == [
            "policy_version",
            "history_window_events",
            "repeated_non_success_threshold",
            "repeated_empty_result_threshold",
        ],
        "Live policy fields are incomplete or unexpected.",
    )
    policy_rules = "\n".join(str(rule) for rule in policy["rules"])
    check("explicit configuration" in policy_rules, "Live policy must come from explicit configuration.")
    check("hidden numeric policy defaults" in policy_rules, "Hidden runtime policy defaults are prohibited.")

    failure = contract["failure_containment"]
    failure_rules = "\n".join(str(rule) for rule in failure["rules"])
    check("operational process error" in failure_rules, "Attention failures must remain operational errors.")
    check("evidence absence" in failure_rules, "Failure must not become evidence absence.")
    check("epistemic state" in failure_rules, "Failure must not become epistemic state.")
    check("scientific-state mutation" in failure_rules, "Failure must not mutate scientific state.")

    isolation = contract["state_isolation"]
    check(isolation["allowed_changes"] == ["retrieval_attention_history"], "Only attention-history persistence may be changed by the connector.")
    protected = set(isolation["protected_fields"])
    check(
        {
            "retrieval_history",
            "retrieval_report",
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
        "Protected state boundary is incomplete.",
    )

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited"])
        == {
            "automatic_action_execution",
            "lifecycle_transition",
            "scientific_state_mutation",
        },
        "Runtime execution boundary is incomplete or unexpected.",
    )

    idempotency = "\n".join(str(rule) for rule in contract["idempotency"]["rules"])
    check("same retrieval history and policy" in idempotency, "Runtime determinism rule is missing.")
    check("must not overwrite" in idempotency, "Duplicate persistence overwrite protection is missing.")

    print("R7C.7 retrieval attention runtime contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

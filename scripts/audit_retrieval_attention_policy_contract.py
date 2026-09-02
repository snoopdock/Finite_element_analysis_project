#!/usr/bin/env python3
"""Audit the R7B explicit retrieval-attention policy contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_policy_contract.yaml"
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "Contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_policy_contract",
        "Unexpected contract name.",
    )

    dependency = contract["dependency"]
    check(
        dependency["context_contract"]["name"]
        == "retrieval_attention_context_contract",
        "R7B must consume the R7A context contract.",
    )
    check(
        dependency["attention_contract"]["name"]
        == "retrieval_attention_contract",
        "R7B must preserve R6.5 attention semantics.",
    )
    check(
        dependency["provenance_contract"]["name"]
        == "retrieval_attention_provenance_contract",
        "R7B must preserve R6.5B provenance semantics.",
    )
    check(
        "explicit versioned acquisition policy" in dependency["composition_rule"],
        "R7B must consume an explicit versioned policy.",
    )
    check(
        "must not alter" in dependency["composition_rule"],
        "R7B must preserve its read-only boundary.",
    )

    policy = contract["policy"]
    check(
        policy["required_fields"]
        == [
            "policy_version",
            "history_window_events",
            "repeated_non_success_threshold",
            "repeated_empty_result_threshold",
        ],
        "R7B policy fields are incomplete or reordered.",
    )
    policy_rules = "\n".join(str(rule) for rule in policy["rules"])
    check("explicit inputs or explicit configuration" in policy_rules, "Policy values must be explicit.")
    check("hidden constants" in policy_rules, "Hidden threshold constants must be prohibited.")
    check("recorded on every generated attention" in policy_rules, "Policy version provenance is missing.")

    classification = contract["observation_classification"]
    required_classes = {"success_with_records", "successful_empty", "non_success"}
    check(required_classes <= set(classification), "Observation classes are incomplete.")
    class_rules = "\n".join(str(rule) for rule in classification["rules"])
    check("recorded R7A observations" in class_rules, "Classification must use recorded observations.")
    check("does not imply evidence absence" in class_rules, "Non-success must remain non-scientific.")
    check("does not imply scientific absence" in class_rules, "Empty retrieval must remain non-scientific.")

    triggers = contract["trigger_evaluation"]
    required_triggers = {
        "provider_unavailable",
        "provider_partially_available",
        "query_returned_empty_result",
        "repeated_query_provider_non_success",
        "repeated_query_provider_empty_result",
    }
    check(
        required_triggers <= set(triggers["allowed_triggers"]),
        "R7B trigger vocabulary is incomplete.",
    )
    check(
        triggers["precedence"]
        == [
            "current_provider_unavailable",
            "current_provider_partially_available",
            "current_query_returned_empty_result",
            "repeated_query_provider_non_success",
            "repeated_query_provider_empty_result",
        ],
        "R7B trigger precedence is not explicit.",
    )
    trigger_rules = "\n".join(str(rule) for rule in triggers["rules"])
    check("independently" in trigger_rules, "Trigger evaluation must be query/provider scoped.")
    check("Unscoped provider operations" in trigger_rules, "Unscoped operations must not become query-specific attention.")

    repetition = contract["repetition_rules"]
    repetition_text = "\n".join(
        str(value)
        for value in [
            repetition["window"],
            repetition["repeated_non_success"]["condition"],
            repetition["repeated_empty_result"]["condition"],
            *repetition["rules"],
        ]
    )
    check("most recent" in repetition_text, "Temporal repetition window must be bounded and recent.")
    check("supporting event IDs" in repetition_text, "Repetition must remain auditable from event IDs.")
    check("Success with records resets" in repetition_text, "Recovery/repetition reset rule is missing.")
    check("evidence repetition" in repetition_text, "Repetition must remain non-scientific.")

    recovery = contract["recovery_rules"]
    recovery_text = "\n".join(
        str(value)
        for value in [
            recovery["latest_success_with_records"]["effect"],
            recovery["latest_successful_empty"]["effect"],
            *recovery["rules"],
        ]
    )
    check("prevents a prior failure" in recovery_text, "Latest successful recovery semantics are missing.")
    check("is not provider recovery" in recovery_text, "Successful empty retrieval must not count as recovery.")
    check("does not delete" in recovery_text, "Recovery must preserve history.")

    output = contract["attention_output"]
    check(
        output["required_fields"]
        == [
            "attention_id",
            "policy_version",
            "query_scope",
            "provider",
            "attention_reason",
            "observed_condition",
            "lifecycle_status",
            "supporting_event_ids",
        ],
        "R7B attention output fields are incomplete or reordered.",
    )
    check(
        output["field_semantics"]["lifecycle_status"]["initial_value"] == "open",
        "R7B must create newly detected attention as open.",
    )
    check(
        "must not be replaced by aggregate counts alone"
        in output["field_semantics"]["supporting_event_ids"]["rule"],
        "R7B must preserve event-level provenance.",
    )

    action = contract["recommended_action_boundary"]
    allowed_actions = {
        "retry_provider",
        "retry_query",
        "reformulate_query",
        "expand_query_scope",
        "use_alternate_provider",
        "defer_until_provider_recovery",
    }
    check(allowed_actions <= set(action["allowed_actions"]), "R7B action vocabulary is incomplete.")
    action_rules = "\n".join(str(rule) for rule in action["rules"])
    check("outside R7B" in action_rules, "Action execution must remain outside R7B.")
    check("must generate new retrieval history events" in action_rules, "Action execution provenance rule is missing.")

    isolation = contract["scientific_isolation"]
    protected = set(isolation["must_not_modify"])
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
        }
        <= protected,
        "R7B isolation boundary is incomplete.",
    )
    forbidden = set(isolation["forbidden_interpretations"])
    check(
        {
            "scientific_absence",
            "evidence_quality",
            "truth_assessment",
            "epistemic_confidence",
            "ranking_adjustment",
            "convergence_adjustment",
            "writer_instruction",
        }
        <= forbidden,
        "R7B scientific interpretation boundary is incomplete.",
    )

    reproducibility = "\n".join(str(rule) for rule in contract["reproducibility"]["rules"])
    check("same R7A context" in reproducibility, "R7B reproducibility must start from R7A context.")
    check("policy version" in reproducibility, "R7B reproducibility must include policy version.")
    check("supporting event IDs" in reproducibility, "R7B must retain event-level traceability.")
    check("must not require network retrieval or an LLM call" in reproducibility, "R7B must be deterministic/offline.")

    excluded = set(contract["scope"]["excluded"])
    check("action execution" in excluded, "R7B must exclude action execution.")
    check("evidence quality scoring" in excluded, "R7B must exclude evidence scoring.")
    check("epistemic inference" in excluded, "R7B must exclude epistemic inference.")
    check("ranking changes" in excluded, "R7B must exclude ranking changes.")
    check("writer decisions" in excluded, "R7B must exclude writer decisions.")

    print("R7B retrieval attention policy contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

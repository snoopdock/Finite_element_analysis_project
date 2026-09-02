#!/usr/bin/env python3
"""Audit R6.5B attention provenance and lifecycle semantics."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_provenance_contract.yaml"
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "Contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_provenance_contract",
        "Unexpected contract name.",
    )

    provenance = contract["attention_provenance"]
    check(
        provenance["required_fields"]
        == [
            "attention_id",
            "policy_version",
            "supporting_event_ids",
            "observed_condition",
            "generated_at",
        ],
        "Attention provenance required fields are incomplete or reordered.",
    )
    check(
        "query_scope" in provenance["optional_context_fields"],
        "Query scope is not available as provenance context.",
    )
    check(
        "provider" in provenance["optional_context_fields"],
        "Provider is not available as provenance context.",
    )

    reproducibility = contract["reproducibility"]
    check(
        reproducibility["required_trace"]
        == [
            "attention_id",
            "policy_version",
            "supporting_event_ids",
            "observed_condition",
        ],
        "Reproducibility trace is incomplete.",
    )
    rules = "\n".join(str(rule) for rule in reproducibility["rules"])
    check("without access to mutable current scientific state" in rules, "Replay must not depend on mutable scientific state.")
    check("retrieval-history events" in rules, "Supporting trace must use retrieval-history events.")
    check("Policy evolution" in rules, "Policy evolution rule is missing.")
    check("network retrieval or an LLM call" in rules, "Replay must remain offline.")

    lifecycle = contract["lifecycle"]
    statuses = lifecycle["statuses"]
    check(
        set(statuses) == {"open", "addressed", "closed"},
        "Lifecycle vocabulary must be open/addressed/closed.",
    )
    transitions = {
        (item["from"], item["to"])
        for item in lifecycle["transitions"]
    }
    check(
        transitions == {
            ("open", "addressed"),
            ("open", "closed"),
            ("addressed", "closed"),
        },
        "Lifecycle transitions are incomplete or unexpected.",
    )
    lifecycle_rules = "\n".join(str(rule) for rule in lifecycle["rules"])
    check("immutable retrieval history" in lifecycle_rules, "Lifecycle must remain separate from history.")
    check("never rewrite, delete, or replace" in lifecycle_rules, "Lifecycle must not mutate history.")
    check("Closed does not mean" in lifecycle_rules, "Closed must not imply permanent problem resolution.")
    check("Addressed means" in lifecycle_rules, "Addressed semantics are missing.")
    check("later successful retrieval" in lifecycle_rules, "Recovery/closure semantics are missing.")

    policy_rules = "\n".join(
        str(rule) for rule in contract["policy_versioning"]["rules"]
    )
    check("explicit identifiers" in policy_rules, "Policy version must be explicit metadata.")
    check("must not rewrite" in policy_rules, "Existing provenance must survive policy changes.")
    check("preserve the policy_version" in policy_rules, "Replay must preserve recorded policy version.")

    isolation = contract["scientific_isolation"]
    protected = set(isolation["provenance_logic_must_not_modify"])
    check(
        {
            "retrieval_history",
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
        "Scientific/process isolation boundary is incomplete.",
    )
    interpretation_rules = set(isolation["interpretation_rules"])
    check(
        "Attention provenance is process metadata, not evidence." in interpretation_rules,
        "Attention provenance must remain process metadata.",
    )
    check(
        "Lifecycle status must not be interpreted as scientific confidence, truth, uncertainty, or evidence quality." in interpretation_rules,
        "Lifecycle must not acquire scientific meaning.",
    )

    excluded = set(contract["scope"]["excluded"])
    check("attention detection implementation" in excluded, "Detection implementation must remain outside R6.5B.")
    check("numeric repetition thresholds" in excluded, "Threshold policy must remain outside R6.5B.")
    check("action execution" in excluded, "Action execution must remain outside R6.5B.")
    check("epistemic inference" in excluded, "Epistemic inference must remain outside R6.5B.")

    print("R6.5B retrieval attention provenance/lifecycle contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

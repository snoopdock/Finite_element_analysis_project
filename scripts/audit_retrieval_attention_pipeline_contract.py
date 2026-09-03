#!/usr/bin/env python3
"""Audit the R7C.5 retrieval-attention pipeline composition contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "specs" / "contracts" / "retrieval_attention_pipeline_contract.yaml"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "R7C.5 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_pipeline_contract",
        "Unexpected R7C.5 contract name.",
    )

    dependencies = contract["dependencies"]
    expected = {
        "retrieval_attention_context": ("retrieval_attention_context_contract", 1),
        "retrieval_attention_policy": ("retrieval_attention_policy_contract", 1),
        "retrieval_attention_provenance": ("retrieval_attention_provenance_contract", 1),
        "retrieval_attention_proposal": ("retrieval_attention_proposal_contract", 1),
        "retrieval_attention_persistence": ("retrieval_attention_persistence_contract", 1),
    }
    for key, (name, version) in expected.items():
        check(dependencies[key]["name"] == name, f"Unexpected dependency name for {key}.")
        check(dependencies[key]["version"] == version, f"Unexpected dependency version for {key}.")

    composition = contract["composition"]
    check(
        composition["sequence"] == [
            "read_persisted_retrieval_history",
            "build_r7a_context",
            "evaluate_r7b_attention",
            "persist_r7b_proposals",
        ],
        "R7C.5 composition sequence is incomplete or reordered.",
    )
    rules = "\n".join(str(rule) for rule in composition["rules"])
    check("must not duplicate their semantics" in rules, "Adapter must compose rather than duplicate layer semantics.")
    check("Retrieval execution is outside" in rules, "Retrieval execution must remain outside the adapter.")
    check("Lifecycle transitions are outside" in rules, "Lifecycle transitions must remain outside the adapter.")
    check("Recommended action execution is outside" in rules, "Action execution must remain outside the adapter.")
    check("Scientific-state mutation is outside" in rules, "Scientific state must remain outside the adapter.")

    inputs = contract["inputs"]
    check(inputs["required"] == ["state", "explicit_policy"], "R7C.5 required inputs are incorrect.")
    check("supplied explicitly" in inputs["policy_rule"], "Policy must be explicit input.")

    outputs = contract["outputs"]
    check(
        outputs["required"] == ["context", "evaluation", "persisted_count", "duplicate_count"],
        "R7C.5 output contract is incomplete or reordered.",
    )

    persistence_rules = "\n".join(str(rule) for rule in contract["persistence_behavior"]["rules"])
    check("passed unchanged in semantic content" in persistence_rules, "R7B proposal semantics must be preserved.")
    check("must not overwrite" in persistence_rules, "Duplicate proposals must be idempotent.")
    check("zero attention items" in persistence_rules, "No-attention persistence behavior must be explicit.")
    check("Existing retrieval history is not modified" in persistence_rules, "Retrieval history must remain immutable at this boundary.")
    check("Existing scientific state is not modified" in persistence_rules, "Scientific state must remain unchanged.")

    lifecycle = contract["lifecycle_boundary"]
    check(lifecycle["generation_status"] == "open", "R7C.5 proposals must begin open.")
    lifecycle_rules = "\n".join(str(rule) for rule in lifecycle["rules"])
    check("must not transition proposals to addressed or closed" in lifecycle_rules, "Lifecycle transitions must remain outside R7C.5.")

    execution = set(contract["execution_boundary"]["prohibited"])
    check(
        {
            "retrieval_execution",
            "provider_retry",
            "query_reformulation_execution",
            "alternate_provider_execution",
            "automatic_action_execution",
            "proposal_to_scientific_state",
            "retrieval_history_rewrite",
        }
        <= execution,
        "Execution boundary is incomplete.",
    )

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
        "Scientific isolation boundary is incomplete.",
    )

    error_rules = "\n".join(str(rule) for rule in contract["error_boundary"]["rules"])
    check("must not rewrite or delete retrieval history" in error_rules, "Persistence errors must preserve retrieval history.")
    check("must not execute fallback retrieval" in error_rules, "Persistence errors must not trigger fallback retrieval.")

    print("R7C.5 retrieval attention pipeline contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

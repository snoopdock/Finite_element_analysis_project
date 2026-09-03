#!/usr/bin/env python3
"""Audit the R7C.8 live runtime isolation contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "specs" / "contracts" / "retrieval_attention_runtime_isolation_contract.yaml"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "R7C.8 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_runtime_isolation_contract",
        "Unexpected R7C.8 contract name.",
    )

    dependency = contract["dependency"]
    check(
        dependency["runtime_contract"]["name"] == "retrieval_attention_runtime_contract",
        "R7C.8 must extend the runtime contract.",
    )
    check(
        dependency["runtime_contract"]["version"] == 1,
        "Unexpected runtime contract version.",
    )

    required = set(contract["runtime_isolation"]["required_properties"])
    check(
        {
            "attention_processing_is_side_channel",
            "attention_failure_is_operational_error",
            "retrieval_history_remains_immutable_after_recording",
            "scientific_state_remains_unchanged",
            "no_action_execution",
            "no_lifecycle_transition",
        }
        == required,
        "Runtime isolation required-property set is incomplete or unexpected.",
    )

    failure = contract["failure_containment"]
    check(
        failure["required_behavior"]
        == [
            "catch_attention_processing_exception",
            "record_operational_error",
            "continue_pipeline",
        ],
        "Failure containment requirements are incomplete or reordered.",
    )
    check(
        {"scientific_uncertainty", "evidence_absence", "epistemic_state_change", "ranking_change", "convergence_change", "writer_instruction"}
        <= set(failure["forbidden_effects"]),
        "Forbidden failure effects are incomplete.",
    )

    scientific = contract["scientific_isolation"]
    check(
        scientific["allowed_attention_state_change"] == ["retrieval_attention_history"],
        "Only retrieval_attention_history may be changed by attention persistence.",
    )
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
        <= set(scientific["protected_fields"]),
        "Scientific isolation protected fields are incomplete.",
    )

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited"])
        == {
            "automatic_action_execution",
            "lifecycle_transition",
            "scientific_state_mutation",
        },
        "R7C.8 execution boundary is incomplete or unexpected.",
    )

    scope = contract["runtime_scope"]
    check("live invocation ordering" in scope["included"], "Live invocation ordering is outside the declared scope.")
    check("operational error containment" in scope["included"], "Operational error containment is outside the declared scope.")
    check("action execution" in scope["excluded"], "Action execution must remain excluded.")
    check("lifecycle management" in scope["excluded"], "Lifecycle management must remain excluded.")

    print("R7C.8 retrieval attention runtime isolation contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

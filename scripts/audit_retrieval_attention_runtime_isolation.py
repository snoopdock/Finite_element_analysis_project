#!/usr/bin/env python3
"""Audit R7C.8 live runtime isolation without executing main.py."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
RUNTIME_PATH = ROOT / "analysis" / "retrieval_attention_runtime.py"
CONTRACT_PATH = ROOT / "specs" / "contracts" / "retrieval_attention_runtime_isolation_contract.yaml"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _calls(tree: ast.AST, name: str):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == name)
            or (isinstance(node.func, ast.Attribute) and node.func.attr == name)
        )
    ]


def main() -> int:
    import yaml

    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    check(contract["version"] == 1, "R7C.8 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_runtime_isolation_contract",
        "Unexpected R7C.8 contract name.",
    )

    main_source = MAIN_PATH.read_text(encoding="utf-8")
    runtime_source = RUNTIME_PATH.read_text(encoding="utf-8")
    main_tree = ast.parse(main_source)
    runtime_tree = ast.parse(runtime_source)

    dependency = contract["dependency"]
    check(
        dependency["runtime_contract"]["name"] == "retrieval_attention_runtime_contract",
        "R7C.8 must depend on the runtime contract.",
    )

    isolation = contract["runtime_isolation"]
    isolation_rules = "\n".join(str(rule) for rule in isolation["rules"])
    check("after retrieval-event recording" in isolation_rules, "Runtime ordering rule is missing.")
    check("operational error" in isolation_rules, "Operational failure isolation rule is missing.")
    check("must not alter scientific reasoning state" in isolation_rules, "Scientific isolation rule is missing.")

    failure = contract["failure_containment"]
    check(
        failure["required_behavior"] == [
            "catch_attention_processing_exception",
            "record_operational_error",
            "continue_pipeline",
        ],
        "Failure containment behavior is incomplete or unexpected.",
    )
    forbidden_effects = set(failure["forbidden_effects"])
    check(
        {"scientific_uncertainty", "evidence_absence", "epistemic_state_change", "ranking_change", "convergence_change"}
        <= forbidden_effects,
        "Scientific failure effects are not fully prohibited.",
    )

    scientific = contract["scientific_isolation"]
    check(scientific["allowed_attention_state_change"] == ["retrieval_attention_history"], "Attention state-change boundary is incorrect.")
    check(
        {"propositions", "evidence_relations", "epistemic_state", "evidence_strength", "truth_status", "ranking", "convergence", "writing_content", "knowledge_base", "sections"}
        <= set(scientific["protected_fields"]),
        "Protected scientific field list is incomplete.",
    )

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited"]) == {
            "automatic_action_execution",
            "lifecycle_transition",
            "scientific_state_mutation",
        },
        "Runtime execution exclusions are incomplete or unexpected.",
    )

    # main.py must import and invoke the connector, but must not expose execution authority.
    check("process_live_retrieval_attention" in main_source, "main.py is not connected to the live attention runtime.")
    check(_calls(main_tree, "process_live_retrieval_attention"), "main.py does not invoke the live runtime connector.")
    check(_calls(main_tree, "append_retrieval_event"), "main.py no longer records retrieval history before attention.")
    check(
        min(node.lineno for node in _calls(main_tree, "process_live_retrieval_attention"))
        > min(node.lineno for node in _calls(main_tree, "append_retrieval_event")),
        "Live attention call must occur after retrieval-event recording.",
    )
    check("Retrieval attention processing error" in main_source, "main.py lacks attention operational error capture.")
    check("continuing pipeline" in main_source, "main.py lacks explicit continuation after attention failure.")

    for forbidden in (
        "execute_recommended_action",
        "execute_acquisition_action",
        "transition_attention_lifecycle",
        "lifecycle_transition",
        "scientific_decision",
    ):
        check(forbidden not in main_source, f"Forbidden authority symbol found in main.py: {forbidden}")

    # runtime connector must remain a simple delegation layer.
    check("generate_and_persist_retrieval_attention" in runtime_source, "Runtime connector must delegate to R7C.5.")
    for forbidden in (
        "requests.",
        "urllib.",
        "httpx",
        "execute_recommended_action",
        "execute_acquisition_action",
        "transition_attention_lifecycle",
    ):
        check(forbidden not in runtime_source, f"Forbidden runtime behavior found: {forbidden}")

    # Runtime module should contain no direct scientific-state field writes.
    for field in (
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
    ):
        check(
            f'[{field!r}]' not in runtime_source,
            f"Runtime connector appears to mutate protected scientific field: {field}",
        )

    reproducibility_rules = "\n".join(str(rule) for rule in contract["reproducibility"]["rules"])
    check("deterministic proposal evaluation" in reproducibility_rules, "Deterministic delegation rule is missing.")
    check("Persistence timestamps" in reproducibility_rules, "Persistence timestamp boundary is missing.")

    print("R7C.8 retrieval attention runtime isolation audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

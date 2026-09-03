#!/usr/bin/env python3
"""Audit R7C.7 live main.py connection without executing the production cycle."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
CONFIG_PATH = ROOT / "config.yaml"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _contains_call(tree: ast.AST, function_name: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == function_name)
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == function_name
            )
        )
        for node in ast.walk(tree)
    )


def _main_try_call_index(tree: ast.Module) -> tuple[int, int]:
    main_fn = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        ),
        None,
    )
    check(main_fn is not None, "main.py must define main().")

    for index, statement in enumerate(main_fn.body):
        if isinstance(statement, ast.Try):
            for inner_index, node in enumerate(statement.body):
                if isinstance(node, ast.If):
                    if any(
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == "process_live_retrieval_attention"
                        for child in ast.walk(node)
                    ):
                        return index, inner_index
    raise AssertionError("Live attention connector call was not found inside main().")


def main() -> int:
    source = MAIN_PATH.read_text(encoding="utf-8")
    config_source = CONFIG_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    check(
        "from analysis.retrieval_attention_runtime import process_live_retrieval_attention" in source,
        "main.py must import the live retrieval-attention connector.",
    )
    check(
        _contains_call(tree, "process_live_retrieval_attention"),
        "main.py must invoke the live retrieval-attention connector.",
    )
    check(
        "retrieval_event_recorded" in source,
        "main.py must gate attention processing on recorded retrieval history.",
    )
    check(
        "Retrieval attention processing error" in source,
        "main.py must contain an operational attention-processing error path.",
    )
    check(
        "continuing pipeline" in source,
        "Attention-processing failure must explicitly continue the pipeline.",
    )

    # The connector must be invoked after the retrieval event append block.
    retrieval_append_positions = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "append_retrieval_event"
    ]
    attention_positions = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "process_live_retrieval_attention"
    ]
    check(retrieval_append_positions, "Retrieval event append call is missing.")
    check(attention_positions, "Attention connector call is missing.")
    check(
        min(attention_positions) > min(retrieval_append_positions),
        "Attention processing must occur after retrieval-history append.",
    )

    # The live source path must not introduce action execution or lifecycle transitions.
    for forbidden in (
        "execute_recommended_action",
        "execute_acquisition_action",
        "transition_attention_lifecycle",
        "lifecycle_transition",
    ):
        check(forbidden not in source, f"Forbidden live action/lifecycle symbol found: {forbidden}")

    # Policy must be explicit in the production config.
    required_policy_lines = (
        "retrieval_attention:",
        "policy_version:",
        "history_window_events:",
        "repeated_non_success_threshold:",
        "repeated_empty_result_threshold:",
    )
    for text in required_policy_lines:
        check(text in config_source, f"Production config is missing explicit R7C.7 policy field: {text}")

    # Verify attention failures are caught by a local handler rather than becoming
    # a direct scientific-control branch in main.py.
    main_try_index, _ = _main_try_call_index(tree)
    check(main_try_index >= 0, "Attention call must be inside main() error-containment logic.")

    print("R7C.7 live retrieval-attention integration audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

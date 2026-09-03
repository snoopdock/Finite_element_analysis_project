#!/usr/bin/env python3
"""Audit the R8.7.4 AcquisitionAdapter boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "analysis" / "acquisition_adapter.py"


def _source() -> str:
    return ADAPTER.read_text(encoding="utf-8")


def _function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _literal_strings(node: ast.AST) -> set[str]:
    values: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            values.add(item.value)
    return values


def main() -> int:
    failures: list[str] = []
    checks = 0

    def require(label: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    try:
        text = _source()
        tree = ast.parse(text)
    except Exception as exc:
        print(f"R8.7.4 AcquisitionAdapter audit: FAIL\n- unable to parse adapter: {exc}")
        return 1

    functions = {
        name: _function(tree, name)
        for name in (
            "validate_acquisition_request",
            "project_acquisition_request",
            "execute_acquisition_request",
        )
    }
    for name, node in functions.items():
        require(f"missing required function: {name}", node is not None)

    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
    imported_modules = {
        (node.module or "")
        for node in imports
    }
    import_names = {
        alias.name
        for node in imports
        for alias in node.names
    }
    require("adapter imports existing retrieval module", "research.evidence" in imported_modules)
    require("adapter imports retrieve_evidence_parallel", "retrieve_evidence_parallel" in import_names)
    require("adapter imports get_last_retrieval_report", "get_last_retrieval_report" in import_names)

    forbidden_direct_imports = {
        "main",
        "analysis.scientific_attention",
        "analysis.gap_detector",
        "analysis.correction_planner",
        "core.writer_orchestration",
    }
    for forbidden in forbidden_direct_imports:
        require(
            f"forbidden architectural import: {forbidden}",
            forbidden not in imported_modules,
        )

    require(
        "adapter defines translation policy version",
        "TRANSLATION_POLICY_VERSION = \"r8.7.4-v1\"" in text,
    )
    require(
        "adapter exposes AcquisitionRequest validation",
        functions["validate_acquisition_request"] is not None,
    )
    require(
        "adapter exposes precise projection",
        functions["project_acquisition_request"] is not None,
    )
    require(
        "adapter exposes explicit execution",
        functions["execute_acquisition_request"] is not None,
    )

    scientific_strings = {
        "confidence",
        "evidence_strength",
        "epistemic_status",
        "truth_status",
        "claim_rank",
        "convergence_score",
        "scientific_priority",
    }
    # The adapter may mention prohibited terms in validation constants, so this
    # check is deliberately structural: forbidden scientific state must not be
    # written through calls to known scientific mutators because none are allowed.
    call_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    require(
        "no scientific-state mutator calls are present",
        not bool(
            call_names
            & {
                "update_scientific_attention",
                "set_confidence",
                "update_epistemic_state",
                "update_claim_ranking",
            }
        ),
    )

    project = functions["project_acquisition_request"]
    if project:
        project_calls = [
            node.func.id
            for node in ast.walk(project)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        require(
            "projection has no retrieval execution call",
            "retrieve_evidence_parallel" not in project_calls,
        )
        require(
            "projection has no network call",
            not bool(set(project_calls) & {"get", "post", "request", "urlopen"}),
        )

    execute = functions["execute_acquisition_request"]
    if execute:
        execute_calls = [
            node.func.id
            for node in ast.walk(execute)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        require(
            "execution invokes retrieval only from execution function",
            "retrieve_evidence_parallel" not in {
                name
                for name in execute_calls
                if name != "executor"
            }
            or "executor" in execute_calls,
        )

    require(
        "receipt contains execution_id",
        '"execution_id"' in text,
    )
    require(
        "receipt contains acquisition_request_id",
        '"acquisition_request_id"' in text,
    )
    require(
        "receipt contains execution status",
        '"execution_status"' in text,
    )
    require(
        "receipt contains translation provenance",
        '"translation_losses"' in text and '"translation_results"' in text,
    )
    require(
        "receipt contains generated query inputs",
        '"generated_query_inputs"' in text,
    )
    require(
        "retries use unique execution identity",
        "uuid.uuid4" in text,
    )
    require(
        "provider preferences are classified as unrepresentable",
        '"constraints.provider_preferences"' in text and '"unrepresentable"' in text,
    )
    require(
        "provider access constraints are classified as unrepresentable",
        '"constraints.provider_access_constraints"' in text,
    )
    require(
        "execution limits are not silently treated as supported",
        '"constraints.execution_limits"' in text and "No exact semantic equivalent" in text,
    )
    require(
        "process priority remains metadata",
        "retained_as_process_metadata" in text,
    )
    require(
        "adapter does not create lifecycle events",
        "LifecycleEvent" not in {
            value
            for node in ast.walk(tree)
            for value in _literal_strings(node)
            if "create LifecycleEvent" in value
        },
    )
    require(
        "adapter does not mutate EvidenceRecord",
        "EvidenceRecord" not in {
            value
            for node in ast.walk(tree)
            for value in _literal_strings(node)
            if "mutate EvidenceRecord" in value
        },
    )

    if failures:
        print(f"R8.7.4 AcquisitionAdapter audit: FAIL ({checks} checks evaluated)")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"R8.7.4 AcquisitionAdapter audit: PASS ({checks}/{checks} checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

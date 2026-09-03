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


def _functions(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _called_names(node: ast.AST) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


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

    functions = _functions(tree)
    for name in (
        "validate_acquisition_request",
        "project_acquisition_request",
        "execute_acquisition_request",
    ):
        require(f"missing required function: {name}", name in functions)

    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
    imported_modules = {(node.module or "") for node in imports}
    imported_names = {
        alias.name
        for node in imports
        for alias in node.names
    }
    require("adapter imports existing retrieval module", "research.evidence" in imported_modules)
    require("adapter imports retrieve_evidence_parallel", "retrieve_evidence_parallel" in imported_names)
    require("adapter imports get_last_retrieval_report", "get_last_retrieval_report" in imported_names)

    forbidden_imports = {
        "main",
        "analysis.scientific_attention",
        "analysis.gap_detector",
        "analysis.correction_planner",
        "core.writer_orchestration",
    }
    for forbidden in forbidden_imports:
        require(
            f"forbidden architectural import: {forbidden}",
            forbidden not in imported_modules,
        )

    require(
        "adapter defines R8.7.4 translation policy",
        'TRANSLATION_POLICY_VERSION = "r8.7.4-v1"' in text,
    )
    require(
        "adapter defines its own schema version",
        "ACQUISITION_ADAPTER_SCHEMA_VERSION" in text,
    )

    project = functions.get("project_acquisition_request")
    execute = functions.get("execute_acquisition_request")

    if project:
        project_calls = _called_names(project)
        require(
            "projection performs no retrieval execution",
            "retrieve_evidence_parallel" not in project_calls,
        )
        require(
            "projection performs no network request",
            not bool(project_calls & {"get", "post", "request", "urlopen"}),
        )

    if execute:
        execute_calls = _called_names(execute)
        require(
            "execution delegates through executor boundary",
            "executor" in execute_calls,
        )
        require(
            "execution reads retrieval report through report getter",
            "report_getter" in execute_calls,
        )

    require("receipt records execution_id", '"execution_id"' in text)
    require("receipt records acquisition_request_id", '"acquisition_request_id"' in text)
    require("receipt records execution_status", '"execution_status"' in text)
    require(
        "receipt records translation results and losses",
        '"translation_results"' in text and '"translation_losses"' in text,
    )
    require("receipt records generated query inputs", '"generated_query_inputs"' in text)
    require("receipt records provider execution summary", '"provider_execution_summary"' in text)
    require("execution identities are occurrence-specific", "uuid.uuid4" in text)

    require(
        "provider preferences cannot be falsely enforced",
        '"constraints.provider_preferences"' in text
        and '"unrepresentable"' in text,
    )
    require(
        "provider access constraints cannot be falsely enforced",
        '"constraints.provider_access_constraints"' in text,
    )
    require(
        "execution limits require exact equivalence",
        "No exact semantic equivalent is exposed by the current retrieval boundary." in text,
    )
    require("process priority is retained as metadata", "retained_as_process_metadata" in text)
    require("adapter produces explicit translation loss", "translation_losses.append" in text)

    source_forbidden_mutators = {
        "update_scientific_attention",
        "set_confidence",
        "update_epistemic_state",
        "update_claim_ranking",
        "create_lifecycle_event",
        "advance_lifecycle",
    }
    call_names = _called_names(tree)
    require(
        "adapter has no known scientific or lifecycle mutator calls",
        not bool(call_names & source_forbidden_mutators),
    )

    require(
        "adapter does not define retrieval implementation",
        "def retrieve_evidence_parallel" not in text,
    )
    require(
        "adapter does not change EvidenceRecord schema",
        "class EvidenceRecord" not in text,
    )
    require(
        "adapter does not create RetrievalEvent implementation",
        "def create_retrieval_event" not in text,
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

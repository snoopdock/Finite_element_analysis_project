#!/usr/bin/env python3
"""Audit the R8.8.0 AcquisitionRequest formulation runtime boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "analysis" / "acquisition_request_formulation.py"
DECISION = ROOT / "specs" / "decisions" / "R8.8.0_acquisition_request_formulation_decision.yaml"


def main() -> int:
    failures: list[str] = []
    checks = 0

    def require(label: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    try:
        text = MODULE.read_text(encoding="utf-8")
        decision = DECISION.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except Exception as exc:
        print(f"R8.8.0 AcquisitionRequest formulation runtime audit: FAIL\n- unable to read/parse artifacts: {exc}")
        return 1

    normalized_decision = " ".join(decision.split())
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    require("formulator function exists", "formulate_acquisition_request" in functions)
    require("output validator is used", "validate_acquisition_request" in {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    })
    require("planning decision validator is used", "validate_research_planning_decision" in {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    })

    source_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for forbidden in (
        "execute_acquisition_request",
        "retrieve_evidence_parallel",
        "create_retrieval_event",
        "create_lifecycle_event",
    ):
        require(f"forbidden runtime call absent: {forbidden}", forbidden not in source_calls)

    imported_modules = {
        node.module or ""
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    }
    require("no main import", "main" not in imported_modules)
    require("no scientific attention import", "analysis.scientific_attention" not in imported_modules)
    require("no correction planner import", "analysis.correction_planner" not in imported_modules)
    require("no gap detector import", "analysis.gap_detector" not in imported_modules)

    require("provider is not inferred", "target.provider is deliberately not mapped" in text)
    require("provider preferences are not inferred", "provider_preferences or provider_access_constraints" in text)
    require("rationale is not converted into a query", "must not invent a query from rationale text" in text)
    require("request origin preserves decision identity", "research_planning_decision_id" in text)
    require("new request identity is generated", "uuid4" in text)
    require("constraints default to empty mapping", "return {}" in text)
    require("request formulation is explicit", "decision_type=formulate_acquisition_request" in text)
    require("execution is explicitly downstream", "Execution belongs exclusively to the downstream AcquisitionAdapter boundary." in normalized_decision)
    require("decision does not create request automatically", "does not automatically create an AcquisitionRequest" in normalized_decision)

    formulator = functions.get("formulate_acquisition_request")
    if formulator:
        names = {
            node.func.id
            for node in ast.walk(formulator)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        require("formulator validates planning decision", "validate_research_planning_decision" in names)
        require("formulator validates resulting request", "validate_acquisition_request" in names)
        require("formulator does not execute retrieval", "execute_acquisition_request" not in names)

    if failures:
        print(f"R8.8.0 AcquisitionRequest formulation runtime audit: FAIL ({checks} checks evaluated)")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"R8.8.0 AcquisitionRequest formulation runtime audit: PASS ({checks}/{checks} checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

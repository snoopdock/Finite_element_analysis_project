from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
RUNTIME = ROOT / "analysis/retrieval_attention_runtime.py"
DECISION = ROOT / "specs/decisions/R8.9.2_research_planning_application_integration_decision.yaml"

FORBIDDEN_MAIN_CALLS = {
    "translate_attention_proposal",
    "evaluate_research_planning_signal",
    "formulate_acquisition_request",
    "execute_acquisition_request",
    "append_retrieval_event",
}

FORBIDDEN_MAIN_IMPORTS = {
    "analysis.acquisition_adapter",
    "analysis.acquisition_request_formulation",
    "research.evidence",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def main() -> None:
    require(MAIN.exists(), f"main.py not found: {MAIN}")
    require(RUNTIME.exists(), f"retrieval-attention runtime not found: {RUNTIME}")
    require(DECISION.exists(), f"R8.9.2 decision not found: {DECISION}")

    main_source = MAIN.read_text(encoding="utf-8")
    runtime_source = RUNTIME.read_text(encoding="utf-8")
    main_tree = ast.parse(main_source, filename=str(MAIN))
    runtime_tree = ast.parse(runtime_source, filename=str(RUNTIME))

    main_modules = imported_modules(main_tree)
    main_calls = call_names(main_tree)

    require(
        "core.research_planning_application" in main_modules,
        "main.py does not import the application planning boundary",
    )
    require(
        "prepare_research_acquisition_flow" in main_calls,
        "main.py does not invoke the established application boundary",
    )

    for token in FORBIDDEN_MAIN_IMPORTS:
        require(token not in main_modules, f"forbidden semantic dependency imported in main.py: {token}")
    for token in FORBIDDEN_MAIN_CALLS:
        if token == "append_retrieval_event":
            continue
        require(token not in main_calls, f"forbidden semantic authority called from main.py: {token}")

    require(
        "RESEARCH_PLANNING_RESULT_FIELD" in main_source,
        "explicit application-owned planning result field is missing",
    )
    require(
        "attention_proposals" in main_source,
        "attention proposals are not passed through the application boundary",
    )
    require(
        "not isinstance(proposals, list) or not proposals" in main_source,
        "zero-proposal guard is missing",
    )
    require(
        "state.pop(RESEARCH_PLANNING_RESULT_FIELD, None)" in main_source,
        "zero-proposal path does not avoid a synthesized planning result",
    )
    require(
        "research_planning_operational_results" in main_source,
        "planning result is not stored in an operational application field",
    )
    require(
        "except Exception as exc" in main_source
        and "Retrieval attention processing error" in main_source,
        "planning failure is not contained at the existing operational error boundary",
    )

    runtime_functions = {
        node.name
        for node in runtime_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    require(
        "process_live_retrieval_attention" in runtime_functions,
        "retrieval-attention runtime entry point is missing",
    )
    require(
        '"attention_proposals"' in runtime_source,
        "runtime result does not expose current attention proposals",
    )

    print("R8.9.2 application integration audit: PASS (10/10 checks passed)")
    print("Application boundary remains thin; planning semantics stay in the established R8.9.1 authorities.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/research_planning_runtime.py"
DECISION = ROOT / "specs/decisions/R8.9.1.0_research_planning_runtime_orchestration_decision.yaml"

FORBIDDEN_IMPORT_TOKENS = {
    "research.evidence",
    "core.pipeline",
    "core.state_manager",
    "core.retrieval_history_state",
    "analysis.acquisition_adapter",
    "lifecycle",
    "scientific",
}

FORBIDDEN_NAME_TOKENS = {
    "retrieve_evidence_parallel",
    "execute_acquisition_request",
    "append_retrieval_event",
    "save_state",
    "AcquisitionExecutionReceipt",
    "ScientificAttention",
    "LifecycleEvent",
}

FORBIDDEN_RUNTIME_STATE_NAMES = {
    "runtime_state",
    "runtime_history",
    "pending_requests",
    "persisted_decisions",
    "implicit_retry_state",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def main() -> None:
    require(MODULE.exists(), f"runtime module not found: {MODULE}")
    require(DECISION.exists(), f"R8.9.1.0 decision not found: {DECISION}")

    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MODULE))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    compose = functions.get("compose_research_acquisition_flow")
    require(compose is not None, "compose_research_acquisition_flow is missing")
    require(
        any(arg.arg == "proposals" for arg in compose.args.args),
        "proposals input is missing",
    )
    keyword_only = {arg.arg for arg in compose.args.kwonlyargs}
    require(
        {"planning_context", "operational_constraints"}.issubset(keyword_only),
        "bounded planning/formulation context parameters are missing",
    )

    modules = imported_modules(tree)
    for token in FORBIDDEN_IMPORT_TOKENS:
        require(token not in modules, f"forbidden runtime dependency imported: {token}")

    names = call_names(tree)
    for token in FORBIDDEN_NAME_TOKENS:
        require(token not in names, f"forbidden runtime operation referenced: {token}")

    # The coordinator must delegate to the established semantic authorities,
    # rather than reimplementing their semantics locally.
    require("translate_attention_proposal" in names, "R8.2 translator is not delegated")
    require(
        "evaluate_research_planning_signal" in names,
        "R8.3 planner is not delegated",
    )
    require(
        "formulate_acquisition_request" in names,
        "R8.8 formulator is not delegated",
    )

    source_lower = source.lower()
    require("for proposal in proposals" in source_lower, "independent proposal iteration is missing")
    require("acquisition_request" in source_lower, "request routing is missing")
    require(
        '"formulate_acquisition_request"' in source_lower,
        "request routing condition is not explicit",
    )
    require(
        "planning_context=planning_context" in source_lower,
        "planning context is not delegated unchanged",
    )
    require(
        "operational_constraints=operational_constraints" in source_lower,
        "operational constraints are not delegated unchanged",
    )
    require("results.append(result)" in source_lower, "composed result collection is missing")

    # No mutable module-level runtime state is permitted.
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            target_text = ast.unparse(target)
            require(
                target_text not in FORBIDDEN_RUNTIME_STATE_NAMES,
                f"forbidden runtime state member declared: {target_text}",
            )

    print("R8.9.1 runtime orchestration implementation audit: PASS (10/10 checks passed)")
    print("Implementation boundary conforms to R8.9.1.0; behavioral verification remains required for closure.")


if __name__ == "__main__":
    main()

"""Bounded, provider-free semantic primitives for AE-32D deterministic rules.

This module is not a trial runner. It accepts source text and task-visible contract
values only; it never loads case records, machine references, or ground truth.
Unsupported syntax is reported explicitly instead of being guessed.
"""
from __future__ import annotations

import ast
import operator
from typing import Any


_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.not_}


class UnsupportedRuleSyntax(ValueError):
    pass


def _find_function(source: str, function_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    ]
    if len(matches) != 1 or isinstance(matches[0], ast.AsyncFunctionDef):
        raise UnsupportedRuleSyntax("function_missing_duplicated_or_async")
    return matches[0]


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        result: set[str] = set()
        for item in node.elts:
            result.update(_target_names(item))
        return result
    return set()


def _loaded_names(node: ast.AST) -> set[str]:
    result: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and child is not node:
            continue
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            result.add(child.id)
    return result


def analyze_unbound_local_return(source: str, function_name: str, variable_name: str) -> dict[str, Any]:
    """Conservatively analyze a straight-line/if-only function for an unbound return read."""
    try:
        function = _find_function(source, function_name)
    except (SyntaxError, UnsupportedRuleSyntax) as exc:
        return {"status": "unsupported", "reason": str(exc), "unbound_return_read": False}

    args = function.args
    parameters = {
        item.arg for item in (
            list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        )
    }
    if args.vararg:
        parameters.add(args.vararg.arg)
    if args.kwarg:
        parameters.add(args.kwarg.arg)
    declared_global: set[str] = set()
    declared_nonlocal: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Global):
            declared_global.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            declared_nonlocal.update(node.names)
    if variable_name in parameters or variable_name in declared_global or variable_name in declared_nonlocal:
        return {"status": "supported", "unbound_return_read": False, "reason": "not_function_local"}

    def local_store(node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Name) and child.id == variable_name and isinstance(child.ctx, ast.Store)
            for child in ast.walk(node)
        )

    if not local_store(function):
        return {"status": "supported", "unbound_return_read": False, "reason": "no_local_assignment"}

    budget = [0]
    unbound: list[dict[str, Any]] = []
    unsupported: list[str] = []

    def read_check(node: ast.AST, assigned: set[str], context: str) -> None:
        if variable_name in _loaded_names(node) and variable_name not in assigned:
            unbound.append({"line": getattr(node, "lineno", None), "context": context})

    def block(statements: list[ast.stmt], states: list[set[str]]) -> list[set[str]]:
        current = [set(state) for state in states]
        for statement in statements:
            budget[0] += 1
            if budget[0] > 256:
                unsupported.append("statement_budget_exceeded")
                return current
            if isinstance(statement, ast.Return):
                for state in current:
                    read_check(statement.value or ast.Constant(None), state, "return")
                return []
            if isinstance(statement, ast.Assign):
                for state in current:
                    read_check(statement.value, state, "assignment_rhs")
                names = set().union(*(_target_names(target) for target in statement.targets))
                current = [state | names for state in current]
            elif isinstance(statement, ast.AnnAssign):
                for state in current:
                    if statement.value is not None:
                        read_check(statement.value, state, "annotated_assignment_rhs")
                current = [state | _target_names(statement.target) for state in current]
            elif isinstance(statement, ast.AugAssign):
                for state in current:
                    read_check(statement.target, state, "augmented_assignment_target")
                    read_check(statement.value, state, "augmented_assignment_rhs")
                current = [state | _target_names(statement.target) for state in current]
            elif isinstance(statement, ast.If):
                for state in current:
                    read_check(statement.test, state, "branch_test")
                body_states = block(statement.body, current)
                else_states = block(statement.orelse, current) if statement.orelse else [set(x) for x in current]
                current = body_states + else_states
                if len(current) > 64:
                    unsupported.append("control_flow_path_budget_exceeded")
                    return current
            elif isinstance(statement, (ast.Pass,)):
                continue
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Nested scopes do not execute as part of this function's straight-line body.
                continue
            else:
                unsupported.append("unsupported_statement:" + type(statement).__name__)
                return current
        return current

    block(function.body, [set(parameters)])
    if unsupported:
        return {
            "status": "unsupported",
            "reason": sorted(set(unsupported)),
            "unbound_return_read": bool(unbound),
            "evidence": unbound,
        }
    return {
        "status": "supported",
        "unbound_return_read": bool(unbound),
        "evidence": unbound,
        "scoped_property": "target local is definitely assigned before every analyzed return read",
    }


def safe_evaluate(node: ast.AST, environment: dict[str, Any], *, depth: int = 0) -> Any:
    """Evaluate a deliberately small pure-expression subset; never calls eval()."""
    if depth > 32:
        raise UnsupportedRuleSyntax("expression_depth_exceeded")
    if isinstance(node, ast.Constant) and isinstance(node.value, (bool, int, float, str, type(None))):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in environment:
            raise UnsupportedRuleSyntax("unbound_name:" + node.id)
        return environment[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = safe_evaluate(node.left, environment, depth=depth + 1)
        right = safe_evaluate(node.right, environment, depth=depth + 1)
        if isinstance(node.op, ast.Pow) and (not isinstance(right, int) or abs(right) > 16):
            raise UnsupportedRuleSyntax("power_budget_exceeded")
        value = _BINOPS[type(node.op)](left, right)
        if isinstance(value, (int, float)) and abs(value) > 10**18:
            raise UnsupportedRuleSyntax("numeric_result_budget_exceeded")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return _UNARYOPS[type(node.op)](safe_evaluate(node.operand, environment, depth=depth + 1))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left = safe_evaluate(node.left, environment, depth=depth + 1)
        right = safe_evaluate(node.comparators[0], environment, depth=depth + 1)
        op = node.ops[0]
        if isinstance(op, ast.Eq): return left == right
        if isinstance(op, ast.NotEq): return left != right
        if isinstance(op, ast.Lt): return left < right
        if isinstance(op, ast.LtE): return left <= right
        if isinstance(op, ast.Gt): return left > right
        if isinstance(op, ast.GtE): return left >= right
    if isinstance(node, ast.IfExp):
        test = safe_evaluate(node.test, environment, depth=depth + 1)
        return safe_evaluate(node.body if test else node.orelse, environment, depth=depth + 1)
    raise UnsupportedRuleSyntax("unsupported_expression:" + type(node).__name__)


def evaluate_function_subset(
    source: str, function_name: str, arguments: list[Any]
) -> dict[str, Any]:
    """Interpret only assignments, if-statements and return in a pure function subset."""
    try:
        function = _find_function(source, function_name)
        parameters = list(function.args.posonlyargs) + list(function.args.args)
        if function.args.vararg or function.args.kwarg or function.args.kwonlyargs:
            raise UnsupportedRuleSyntax("unsupported_function_signature")
        if len(arguments) != len(parameters):
            raise UnsupportedRuleSyntax("argument_count_mismatch")
        environment = {parameter.arg: value for parameter, value in zip(parameters, arguments)}

        def execute(statements: list[ast.stmt]) -> tuple[bool, Any]:
            for statement in statements:
                if isinstance(statement, ast.Assign):
                    value = safe_evaluate(statement.value, environment)
                    if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                        raise UnsupportedRuleSyntax("unsupported_assignment_target")
                    environment[statement.targets[0].id] = value
                elif isinstance(statement, ast.AnnAssign):
                    if statement.value is None or not isinstance(statement.target, ast.Name):
                        raise UnsupportedRuleSyntax("unsupported_annotated_assignment")
                    environment[statement.target.id] = safe_evaluate(statement.value, environment)
                elif isinstance(statement, ast.If):
                    branch = statement.body if safe_evaluate(statement.test, environment) else statement.orelse
                    returned, value = execute(branch)
                    if returned:
                        return True, value
                elif isinstance(statement, ast.Return):
                    return True, safe_evaluate(statement.value or ast.Constant(None), environment)
                elif isinstance(statement, ast.Pass):
                    continue
                else:
                    raise UnsupportedRuleSyntax("unsupported_statement:" + type(statement).__name__)
            return False, None

        returned, value = execute(function.body)
        if not returned:
            raise UnsupportedRuleSyntax("function_did_not_return")
        return {"status": "supported", "kind": "return", "value": value}
    except (SyntaxError, UnsupportedRuleSyntax, ArithmeticError, TypeError, ValueError) as exc:
        return {"status": "unsupported", "reason": str(exc)}


def analyze_exception_contract_suppression(
    source: str, function_name: str, exception_name: str, contract_kind: str
) -> dict[str, Any]:
    if contract_kind != "raise":
        return {"status": "unsupported", "reason": "contract_kind_not_raise", "suppression_observed": False}
    try:
        function = _find_function(source, function_name)
    except (SyntaxError, UnsupportedRuleSyntax) as exc:
        return {"status": "unsupported", "reason": str(exc), "suppression_observed": False}
    evidence = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            caught = handler.type.id if isinstance(handler.type, ast.Name) else None
            if caught != exception_name:
                continue
            returns_normally = any(isinstance(child, ast.Return) for child in handler.body)
            reraises = any(isinstance(child, ast.Raise) and child.exc is None for child in handler.body)
            if returns_normally and not reraises:
                evidence.append({"line": handler.lineno, "caught": caught, "returns_normally": True})
    return {
        "status": "supported",
        "suppression_observed": bool(evidence),
        "evidence": evidence,
        "decision_authority": "defect_only_if_task_contract_requires_propagation",
    }


def analyze_stale_intermediate_sink(
    source: str,
    function_name: str,
    intermediate_name: str,
    input_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        function = _find_function(source, function_name)
    except (SyntaxError, UnsupportedRuleSyntax) as exc:
        return {"status": "unsupported", "reason": str(exc), "stale_sink_observed": False}
    assigned = any(
        isinstance(node, ast.Assign)
        and intermediate_name in set().union(*(_target_names(t) for t in node.targets))
        for node in ast.walk(function)
    )
    returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
    if len(returns) != 1:
        return {"status": "unsupported", "reason": "requires_exactly_one_return", "stale_sink_observed": False}
    sink_names = _loaded_names(returns[0].value or ast.Constant(None))
    bypasses_intermediate = assigned and intermediate_name not in sink_names
    comparisons = []
    for case in input_cases:
        actual = evaluate_function_subset(source, function_name, case["arguments"])
        comparisons.append({
            "status": actual["status"],
            "expected": case["expected"],
            "actual": actual.get("value"),
            "matches": actual.get("status") == "supported" and actual.get("value") == case["expected"],
        })
    mismatch = any(item["status"] != "supported" or not item["matches"] for item in comparisons)
    return {
        "status": "supported" if all(item["status"] == "supported" for item in comparisons) else "partial",
        "intermediate_assigned": assigned,
        "sink_reads_intermediate": intermediate_name in sink_names,
        "stale_sink_observed": bool(bypasses_intermediate and mismatch),
        "comparisons": comparisons,
        "decision_authority": "defect_only_if_contract_formula_and_causal_path_are_both_established",
    }


def observe_dynamic_attribute_mismatch(
    consumer_source: str, provider_source: str, function_name: str, provider_class: str
) -> dict[str, Any]:
    try:
        consumer = _find_function(consumer_source, function_name)
        provider_tree = ast.parse(provider_source)
    except (SyntaxError, UnsupportedRuleSyntax) as exc:
        return {"status": "unsupported", "reason": str(exc), "decision": "abstain"}
    reads = [
        node.attr for node in ast.walk(consumer)
        if isinstance(node, ast.Attribute) and node.attr and isinstance(node.ctx, ast.Load)
    ]
    classes = [node for node in provider_tree.body if isinstance(node, ast.ClassDef) and node.name == provider_class]
    if len(classes) != 1:
        return {"status": "unsupported", "reason": "provider_class_not_unique", "decision": "abstain"}
    declared: set[str] = set()
    for node in ast.walk(classes[0]):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
            if isinstance(node.ctx, ast.Store):
                declared.add(node.attr)
    missing = sorted(set(reads) - declared)
    return {
        "status": "supported",
        "observed_unmatched_attribute_reads": missing,
        "visible_provider_attributes": sorted(declared),
        "decision": "abstain" if missing else "no_mismatch_observed",
        "reason": "static class inspection cannot rule out dynamic attribute provision or external wrappers",
    }

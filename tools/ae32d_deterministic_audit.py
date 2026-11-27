"""Deterministic AE-32D condition A adapter over an allowlisted task projection.

This is an exploratory case-level baseline, not an official benchmark scorer.
It reads only the pinned fixture source and task-visible contract files in the
sanitized projection. It never loads case records or hidden reference metadata.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator

from tools.ae32d_deterministic_rules import (
    analyze_exception_contract_suppression,
    analyze_stale_intermediate_sink,
    analyze_unbound_local_return,
    evaluate_function_subset,
    observe_dynamic_attribute_mismatch,
)
from tools.ae32d_trial_contracts import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
TASK_SCHEMA = ROOT / "evaluation" / "ae32d" / "sanitized-task-projection.schema.json"
REPORT_SCHEMA = ROOT / "evaluation" / "ae32d" / "condition-report.schema.json"
ADAPTER_REVISION = "ae32d-deterministic-a/0.1.0"
MAX_SCOPE_FILES = 64
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_SEARCH_RESULTS = 80
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relpath(value: str) -> bool:
    if not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True, timeout=10,
    )
    return result.stdout.strip()


def _resolve_fixture_root(source_root: Path, fixture_path: str) -> Path:
    if not _safe_relpath(fixture_path):
        raise ValueError("unsafe_fixture_path")
    cursor = source_root
    for part in PurePosixPath(fixture_path).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("fixture_path_contains_symlink")
    resolved = cursor.resolve(strict=True)
    resolved.relative_to(source_root)
    if not resolved.is_dir():
        raise ValueError("fixture_path_not_directory")
    return resolved


def _scope_relative_path(scope_item: str, fixture_path: str) -> str | None:
    """Convert a declared file path to fixture-relative form; descriptors remain descriptors."""
    if not _safe_relpath(scope_item):
        raise ValueError("unsafe_declared_scope_path")
    prefix = fixture_path.rstrip("/") + "/"
    if scope_item.startswith(prefix):
        return scope_item[len(prefix):]
    # Human-readable scope descriptors are not treated as filenames.
    if " " in scope_item:
        return None
    return scope_item


def _read_scope_file(fixture_root: Path, relative: str) -> tuple[bytes, str]:
    if not _safe_relpath(relative):
        raise ValueError("unsafe_scope_relative_path")
    candidate = fixture_root
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("scope_file_contains_symlink")
    resolved = candidate.resolve(strict=True)
    resolved.relative_to(fixture_root)
    if not resolved.is_file():
        raise ValueError("scope_entry_not_regular_file")
    data = resolved.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("scope_file_size_budget_exceeded")
    return data, resolved.as_posix()


def _load_expected_contract(files: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    entry = files.get("expected_behavior.json")
    if entry is None:
        return None
    try:
        raw = json.loads(entry["text"])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    # Explicit allowlist: fixture metadata such as case_id and benchmark eligibility
    # is never passed into the rule engine.
    function = raw.get("function")
    input_cases = raw.get("input_cases")
    if not isinstance(function, str) or not function:
        return None
    if not isinstance(input_cases, list):
        return None
    sanitized_cases = []
    for item in input_cases:
        if not isinstance(item, dict) or not isinstance(item.get("arguments"), list):
            return None
        expected = item.get("expected")
        if not isinstance(expected, dict) or expected.get("kind") not in {"return", "raise"}:
            return None
        if expected["kind"] == "return":
            if "value" not in expected:
                return None
            sanitized_expected = {"kind": "return", "value": expected["value"]}
        else:
            exception = expected.get("exception")
            if not isinstance(exception, str) or not exception:
                return None
            sanitized_expected = {"kind": "raise", "exception": exception}
        sanitized_cases.append({"arguments": item["arguments"], "expected": sanitized_expected})
    return {"function": function, "input_cases": sanitized_cases}


def _top_level_functions(source: str) -> list[ast.FunctionDef]:
    tree = ast.parse(source)
    return [node for node in tree.body if isinstance(node, ast.FunctionDef)]


def _assigned_local_names(function: ast.FunctionDef) -> list[str]:
    names: set[str] = set()
    stack: list[ast.AST] = [function]
    while stack:
        node = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            stack.append(child)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
    parameters = {
        item.arg for item in (
            list(function.args.posonlyargs) + list(function.args.args) + list(function.args.kwonlyargs)
        )
    }
    return sorted(names - parameters)


def _line_evidence(path: str, line: int, digest: str, role: str = "supports") -> dict[str, Any]:
    return {
        "path": path, "line_start": max(1, int(line)), "line_end": max(1, int(line)),
        "file_sha256": digest, "role": role,
    }


def run_deterministic_audit(task_projection: dict[str, Any], source_root: str | Path) -> dict[str, Any]:
    """Run condition A against one immutable source snapshot and sanitized task projection."""
    task_schema = json.loads(TASK_SCHEMA.read_text(encoding="utf-8"))
    report_schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(task_schema).validate(task_projection)
    if task_projection["condition"] != "A_deterministic":
        raise ValueError("condition_A_requires_A_deterministic_projection")

    root = Path(source_root).resolve(strict=True)
    if not root.is_dir() or Path(source_root).is_symlink():
        raise ValueError("source_root_must_be_regular_directory")
    actual_sha = _git_head(root)
    expected_sha = task_projection["source"]["source_commit_sha"]
    if actual_sha != expected_sha:
        raise ValueError("source_revision_mismatch:" + actual_sha)

    fixture_path = task_projection["source"]["fixture_path"]
    fixture_root = _resolve_fixture_root(root, fixture_path)
    files: dict[str, dict[str, Any]] = {}
    missing_paths: list[str] = []
    descriptors: list[str] = []
    total_bytes = 0

    for item in task_projection["task"]["declared_scope"]:
        relative = _scope_relative_path(item, fixture_path)
        if relative is None:
            descriptors.append(item)
            continue
        if relative in files:
            continue
        try:
            data, _ = _read_scope_file(fixture_root, relative)
        except FileNotFoundError:
            missing_paths.append(relative)
            continue
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_BYTES or len(files) >= MAX_SCOPE_FILES:
            raise ValueError("scope_inventory_budget_exceeded")
        try:
            text_value = data.decode("utf-8")
        except UnicodeDecodeError:
            missing_paths.append(relative + ":unsupported_encoding")
            continue
        files[relative] = {"bytes": data, "text": text_value, "sha256": _sha256(data)}

    manifest = [
        {"path": path, "size": len(item["bytes"]), "sha256": item["sha256"]}
        for path, item in sorted(files.items())
    ]
    manifest_digest = _canonical_digest(manifest)
    contract = _load_expected_contract(files)
    findings: list[dict[str, Any]] = []
    counterevidence: list[str] = []
    unresolved: list[str] = []
    limitations: list[str] = []
    trace: list[dict[str, Any]] = []

    # Deterministic ordinary source search over the same declared file set.
    tokens = sorted(set(TOKEN_RE.findall(
        task_projection["task"]["title"] + " " + task_projection["task"]["problem_statement"]
    )))
    search_matches = []
    for token in tokens[:24]:
        for path, entry in sorted(files.items()):
            for line_number, line in enumerate(entry["text"].splitlines(), start=1):
                if token.casefold() in line.casefold():
                    search_matches.append({
                        "path": path, "line": line_number, "token": token,
                        "snippet": line[:240], "sha256": entry["sha256"],
                    })
                    if len(search_matches) >= MAX_SEARCH_RESULTS:
                        break
            if len(search_matches) >= MAX_SEARCH_RESULTS:
                break
        if len(search_matches) >= MAX_SEARCH_RESULTS:
            break
    trace.append({"step_id": "A-SEARCH", "operation": "deterministic_scope_search",
                  "status": "partial" if len(search_matches) >= MAX_SEARCH_RESULTS else "ok",
                  "details": {"query_count": len(tokens[:24]), "match_count": len(search_matches)}})

    python_files = {
        path: entry for path, entry in files.items() if path.endswith(".py")
    }
    contract_function = contract["function"] if contract else None
    defect_detected = False
    contract_cases_pass = bool(contract and contract["input_cases"])
    contract_case_count = 0

    for path, entry in sorted(python_files.items()):
        try:
            functions = _top_level_functions(entry["text"])
        except SyntaxError:
            limitations.append("python_parse_error:" + path)
            contract_cases_pass = False
            continue
        for function in functions:
            if contract_function and function.name != contract_function:
                continue

            # Control-flow definite assignment.
            for variable in _assigned_local_names(function):
                result = analyze_unbound_local_return(entry["text"], function.name, variable)
                if result["status"] == "unsupported":
                    limitations.append("unbound_analysis_unsupported:" + path + ":" + variable)
                    contract_cases_pass = False
                elif result["unbound_return_read"] and contract:
                    return_cases = [
                        row for row in contract["input_cases"]
                        if row["expected"]["kind"] == "return"
                    ]
                    if return_cases:
                        evidence = []
                        for row in result.get("evidence", []):
                            evidence.append(_line_evidence(path, row.get("line") or 1, entry["sha256"]))
                        findings.append({
                            "finding_id": "A-CFG-" + function.name + "-" + variable,
                            "statement": (
                                "A function-local value is read at a return or augmented-assignment "
                                "site on a path without a reaching local assignment."
                            ),
                            "classification": "inference",
                            "evidence": evidence or [_line_evidence(path, function.lineno, entry["sha256"])],
                        })
                        defect_detected = True

            # Explicit exception propagation contract.
            if contract:
                raise_cases = [
                    row for row in contract["input_cases"] if row["expected"]["kind"] == "raise"
                ]
                for row in raise_cases:
                    exception_name = row["expected"]["exception"]
                    try_node = ast.parse(entry["text"])
                    call_names = sorted({
                        node.func.id for node in ast.walk(try_node)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    })
                    for operation_name in call_names:
                        result = analyze_exception_contract_suppression(
                            entry["text"], function.name, exception_name, "raise", operation_name
                        )
                        if result["status"] == "unsupported":
                            limitations.append("exception_rule_unsupported:" + path)
                        elif result["suppression_observed"]:
                            line = result["evidence"][0]["line"]
                            findings.append({
                                "finding_id": "A-EXC-" + function.name + "-" + exception_name,
                                "statement": (
                                    "A handler catches the contract-specified exception from the "
                                    "relevant operation and returns normally instead of propagating it."
                                ),
                                "classification": "inference",
                                "evidence": [_line_evidence(path, line, entry["sha256"])],
                            })
                            defect_detected = True
                            break

            # Data-flow sink check against task-visible input/output examples.
            if contract and contract["input_cases"]:
                return_cases = [
                    {"arguments": row["arguments"], "expected": row["expected"]["value"]}
                    for row in contract["input_cases"] if row["expected"]["kind"] == "return"
                ]
                if return_cases:
                    contract_case_count += len(return_cases)
                    for variable in _assigned_local_names(function):
                        result = analyze_stale_intermediate_sink(
                            entry["text"], function.name, variable, return_cases
                        )
                        if result["status"] == "partial":
                            limitations.append("dataflow_evaluation_partial:" + path + ":" + variable)
                            contract_cases_pass = False
                        elif result["status"] == "supported" and result["stale_sink_observed"]:
                            return_node = next(
                                node for node in ast.walk(function) if isinstance(node, ast.Return)
                            )
                            findings.append({
                                "finding_id": "A-DATAFLOW-" + function.name + "-" + variable,
                                "statement": (
                                    "A computed intermediate is bypassed by the output sink and the "
                                    "task-visible contract example does not match the returned value."
                                ),
                                "classification": "inference",
                                "evidence": [
                                    _line_evidence(path, return_node.lineno, entry["sha256"]),
                                ],
                            })
                            defect_detected = True
                            break

            # Verify all task-visible return examples using the safe interpreter.
            if contract and function.name == contract_function:
                for row in contract["input_cases"]:
                    if row["expected"]["kind"] != "return":
                        continue
                    actual = evaluate_function_subset(entry["text"], function.name, row["arguments"])
                    if actual["status"] != "supported" or actual["value"] != row["expected"]["value"]:
                        contract_cases_pass = False
                    trace.append({
                        "step_id": "A-CONTRACT-" + str(contract_case_count + 1),
                        "operation": "safe_contract_example_evaluation",
                        "status": "ok" if actual["status"] == "supported" else "partial",
                        "details": {
                            "function": function.name,
                            "matches": actual.get("status") == "supported" and actual.get("value") == row["expected"]["value"],
                        },
                    })

    # Provider-interface cases have no complete structured behavior contract.
    # Preserve the visible attribute mismatch as an observation and abstain.
    if not contract:
        extractor = next((item for path, item in sorted(python_files.items())
                          if PurePosixPath(path).name == "extractor.py"), None)
        adapter = next((item for path, item in sorted(python_files.items())
                        if PurePosixPath(path).name == "adapter.py"), None)
        if extractor and adapter:
            try:
                extractor_function = _top_level_functions(extractor["text"])[0]
                annotation = extractor_function.args.args[0].annotation if extractor_function.args.args else None
                provider_class = annotation.id if isinstance(annotation, ast.Name) else None
                if provider_class is None:
                    provider_tree = ast.parse(adapter["text"])
                    provider_class = next(
                        (node.name for node in provider_tree.body if isinstance(node, ast.ClassDef)), None
                    )
                if provider_class:
                    result = observe_dynamic_attribute_mismatch(
                        extractor["text"], adapter["text"], extractor_function.name, provider_class, "provider"
                    )
                    if result.get("observed_unmatched_attribute_reads"):
                        attr = result["observed_unmatched_attribute_reads"][0]
                        findings.append({
                            "finding_id": "A-ATTRIBUTE-" + attr,
                            "statement": (
                                "The consumer reads an attribute not declared in the visible provider class; "
                                "dynamic construction and runtime provision remain unresolved."
                            ),
                            "classification": "observation",
                            "evidence": [
                                _line_evidence("extractor.py", extractor_function.lineno, extractor["sha256"]),
                                _line_evidence("adapter.py", 1, adapter["sha256"]),
                            ],
                        })
                        unresolved.append("The supplied evidence does not establish the complete provider contract or runtime object.")
            except (SyntaxError, IndexError):
                limitations.append("provider_attribute_analysis_unsupported")

    if missing_paths:
        limitations.extend("missing_declared_scope_file:" + path for path in missing_paths)
    if descriptors:
        limitations.extend("scope_descriptor_not_resolved_to_file:" + item for item in descriptors)
    if defect_detected:
        decision = "defect"
    elif contract and contract_cases_pass and contract_case_count > 0 and not limitations:
        decision = "no_defect"
    else:
        decision = "abstain"

    status = "completed" if not missing_paths and not limitations else "partial"
    report = {
        "schema_version": "ae32d/condition-report/v1",
        "case_id": task_projection["case_id"],
        "condition": "A_deterministic",
        "adapter_revision": ADAPTER_REVISION,
        "source_commit_sha": actual_sha,
        "task_contract_digest": task_projection["task_contract_digest"],
        "config_digest": _canonical_digest({
            "adapter_revision": ADAPTER_REVISION,
            "search_token_limit": 24,
            "search_result_limit": MAX_SEARCH_RESULTS,
            "scope_file_limit": MAX_SCOPE_FILES,
            "file_byte_limit": MAX_FILE_BYTES,
            "total_byte_limit": MAX_TOTAL_BYTES,
        }),
        "source_manifest_digest": manifest_digest,
        "status": status,
        "coverage": {
            "declared_scope_complete": not missing_paths and not descriptors,
            "truncated": len(search_matches) >= MAX_SEARCH_RESULTS,
            "unreadable_paths": [],
            "missing_paths": missing_paths,
        },
        "findings": findings,
        "counterevidence": counterevidence,
        "unresolved_questions": unresolved,
        "decision": decision,
        "limitations": limitations,
        "execution_trace": trace,
    }
    Draft202012Validator(report_schema).validate(report)
    return report

#!/usr/bin/env python3
"""Verify the pinned AE-32D multi-case fixture matrix without external services."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PINNED_SOURCE_COMMIT = "dd80be6e7a3e0a912beace92ce0fac446ea6ed61"
FIXTURES = {
    "branch_unbound": "tests/semantic_audit/fixtures/ae32d_branch_unbound_incident",
    "no_defect": "tests/semantic_audit/fixtures/ae32d_no_defect_control",
    "ambiguous_provider": "tests/semantic_audit/fixtures/ae32d_ambiguous_provider_contract",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head(root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10, check=True,
    )
    return proc.stdout.strip()


def run_python(directory: Path, code: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(directory),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-I", "-c", code], cwd=directory,
        capture_output=True, text=True, timeout=10, env=env,
    )


def verify_branch_unbound(root: Path) -> dict:
    folder = root / FIXTURES["branch_unbound"]
    source = folder / "branch_logic.py"
    contract = folder / "expected_behavior.json"
    incident = folder / "incident.md"
    errors, checks = [], []
    for item in (source, contract, incident):
        if not item.is_file():
            errors.append("branch_unbound_missing:" + item.name)
    if errors:
        return {"status": "failed", "errors": errors, "checks": checks}
    tree = ast.parse(source.read_text(encoding="utf-8"))
    data = json.loads(contract.read_text(encoding="utf-8"))
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "work"), None)
    if fn is None:
        errors.append("branch_unbound_work_function_missing")
    else:
        conditional_assign = any(
            isinstance(n, ast.If) and any(
                isinstance(x, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "result"
                    for target in x.targets for t in ast.walk(target)
                ) for x in ast.walk(n)
            ) for n in fn.body
        )
        unconditional_return = any(
            isinstance(n, ast.Return) and isinstance(n.value, ast.Name)
            and n.value.id == "result" for n in ast.walk(fn)
        )
        if conditional_assign and unconditional_return:
            checks.append("conditional_assignment_then_unconditional_return")
        else:
            errors.append("branch_unbound_ast_pattern_not_found")
    expected = [
        {"arguments": [True], "expected": {"kind": "return", "value": 5}},
        {"arguments": [False], "expected": {"kind": "return", "value": 0}},
    ]
    if data.get("input_cases") != expected:
        errors.append("branch_unbound_contract_mismatch")
    else:
        checks.append("declared_behavior_contract_matches")
    proc = run_python(folder, "import branch_logic; print(branch_logic.work(False))")
    combined = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 and "UnboundLocalError" in combined and "result" in combined:
        checks.append("false_branch_unbound_local_reproduced")
    else:
        errors.append("branch_unbound_runtime_not_reproduced")
    return {
        "status": "verified" if not errors else "failed",
        "checks": checks, "errors": errors,
        "runtime": {"exit_code": proc.returncode, "stderr_tail": (proc.stderr or "")[-800:]},
        "files": {p.name: digest(p) for p in (source, contract, incident)},
    }


def verify_no_defect(root: Path) -> dict:
    folder = root / FIXTURES["no_defect"]
    source, contract, incident = (folder / "control.py", folder / "expected_behavior.json",
                                  folder / "incident.md")
    errors, checks = [], []
    for item in (source, contract, incident):
        if not item.is_file():
            errors.append("no_defect_missing:" + item.name)
    if errors:
        return {"status": "failed", "errors": errors, "checks": checks}
    tree = ast.parse(source.read_text(encoding="utf-8"))
    data = json.loads(contract.read_text(encoding="utf-8"))
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "work"), None)
    if fn is None:
        errors.append("no_defect_work_function_missing")
    else:
        init_before_if = any(
            isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "result" for t in n.targets
            ) and any(isinstance(later, ast.If) and later.lineno > n.lineno for later in fn.body)
            for n in fn.body
        )
        if init_before_if:
            checks.append("result_initialized_before_conditional")
        else:
            errors.append("no_defect_initialization_structure_missing")
    expected = [
        {"arguments": [True], "expected": {"kind": "return", "value": 5}},
        {"arguments": [False], "expected": {"kind": "return", "value": 0}},
    ]
    if data.get("input_cases") != expected:
        errors.append("no_defect_contract_mismatch")
    else:
        checks.append("declared_behavior_contract_matches")
    proc = run_python(folder, "import json, control; print(json.dumps([control.work(True), control.work(False)]))")
    try:
        observed = json.loads(proc.stdout.strip()) if proc.returncode == 0 else None
    except json.JSONDecodeError:
        observed = None
    if observed == [5, 0]:
        checks.append("both_contract_paths_execute_as_declared")
    else:
        errors.append("no_defect_runtime_contract_mismatch")
    return {
        "status": "verified" if not errors else "failed",
        "checks": checks, "errors": errors,
        "runtime": {"exit_code": proc.returncode, "observed": observed,
                    "stderr_tail": (proc.stderr or "")[-800:]},
        "files": {p.name: digest(p) for p in (source, contract, incident)},
    }


def verify_ambiguous_provider(root: Path) -> dict:
    folder = root / FIXTURES["ambiguous_provider"]
    names = ("extractor.py", "adapter.py", "factory.py", "incident.md")
    paths = [folder / name for name in names]
    errors, checks = [], []
    for path in paths:
        if not path.is_file():
            errors.append("ambiguous_provider_missing:" + path.name)
    if errors:
        return {"status": "failed", "errors": errors, "checks": checks}
    extractor = ast.parse((folder / "extractor.py").read_text(encoding="utf-8"))
    adapter = ast.parse((folder / "adapter.py").read_text(encoding="utf-8"))
    factory = ast.parse((folder / "factory.py").read_text(encoding="utf-8"))
    reads_total_calls = any(isinstance(n, ast.Attribute) and n.attr == "total_calls"
                            for n in ast.walk(extractor))
    writes_calls = any(isinstance(n, ast.Attribute) and n.attr == "calls"
                       for n in ast.walk(adapter))
    imports_runtime_provider = any(
        isinstance(n, ast.ImportFrom) and n.module == "runtime_provider"
        for n in ast.walk(factory)
    )
    missing_runtime_module = not (folder / "runtime_provider.py").exists() and not (
        folder / "runtime_provider" / "__init__.py"
    ).exists()
    if reads_total_calls and writes_calls:
        checks.append("visible_consumer_adapter_name_difference")
    else:
        errors.append("ambiguous_visible_contract_witness_missing")
    if imports_runtime_provider and missing_runtime_module:
        checks.append("factory_dependency_implementation_absent_from_evidence")
    else:
        errors.append("ambiguous_missing_dependency_not_established")
    return {
        "status": "ambiguity_boundary_verified" if not errors else "failed",
        "checks": checks, "errors": errors,
        "runtime": {"executed": False, "reason": "concrete provider implementation is outside the evidence bundle"},
        "files": {p.name: digest(p) for p in paths},
    }


def verify_matrix(root: Path) -> dict:
    cases = {
        "branch_unbound": verify_branch_unbound(root),
        "no_defect": verify_no_defect(root),
        "ambiguous_provider": verify_ambiguous_provider(root),
    }
    ok = all(value["status"] in {"verified", "ambiguity_boundary_verified"}
             and not value["errors"] for value in cases.values())
    return {
        "schema_version": "ae32d/case-matrix-verification/v1",
        "pinned_source_commit": PINNED_SOURCE_COMMIT,
        "status": "machine_verified_matrix" if ok else "machine_verification_failed",
        "primary_benchmark_eligible": False,
        "human_independent_adjudication": "not_performed",
        "cases": cases,
        "limitations": [
            "The matrix verifies bounded synthetic fixture properties, not general audit-engine accuracy.",
            "The ambiguity case verifies an evidence boundary; it intentionally does not execute the unavailable provider implementation.",
            "No case receives a gold label or primary-score eligibility from this workflow.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = (args.source_root or Path(os.environ["AE32D_CASE_SOURCE_ROOT"])).resolve()
    errors = []
    try:
        observed_head = git_head(root)
    except (OSError, subprocess.SubprocessError) as exc:
        observed_head = None
        errors.append("source_git_identity_unavailable:" + type(exc).__name__)
    if observed_head != PINNED_SOURCE_COMMIT:
        errors.append("source_head_does_not_match_pinned_commit")
    result = verify_matrix(root)
    result["observed_source_commit"] = observed_head
    result["errors"] = errors
    if errors:
        result["status"] = "machine_verification_failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "source_commit": observed_head,
                      "case_statuses": {k: v["status"] for k, v in result["cases"].items()},
                      "errors": errors}, indent=2))
    return 0 if result["status"] == "machine_verified_matrix" else 1


if __name__ == "__main__":
    raise SystemExit(main())

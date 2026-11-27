#!/usr/bin/env python3
"""Verify two additional AE-32D synthetic defect families at an immutable source pin."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PINNED_SOURCE_COMMIT = "c0d700c0a2599aabda8957f54e750a812ea2ef5d"
BASE = Path("tests/semantic_audit/fixtures")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime(folder: Path, code: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-c", code], cwd=folder, env=env,
                          capture_output=True, text=True, timeout=10)


def verify_exception_swallow(root: Path) -> dict:
    folder = root / BASE / "ae32d_exception_swallow_incident"
    paths = [folder / n for n in ("loader.py", "expected_behavior.json", "incident.md")]
    errors, checks = [], []
    if not all(p.is_file() for p in paths):
        return {"status": "failed", "errors": ["exception_fixture_file_missing"], "checks": []}
    tree = ast.parse(paths[0].read_text(encoding="utf-8"))
    contract = json.loads(paths[1].read_text(encoding="utf-8"))
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "load_config"), None)
    handler = next((n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)
                    and isinstance(n.type, ast.Name) and n.type.id == "OSError"), None) if fn else None
    returns_empty = bool(handler) and any(
        isinstance(n, ast.Return) and isinstance(n.value, ast.Dict) and not n.value.keys
        for n in ast.walk(handler)
    )
    if returns_empty:
        checks.append("oserror_handler_suppresses_exception_with_empty_mapping")
    else:
        errors.append("exception_suppression_ast_not_found")
    expected = contract.get("input_cases") == [
        {"arguments": ["failing_reader"], "expected": {"kind": "raise", "exception": "OSError"}}
    ]
    if expected:
        checks.append("propagation_contract_declared")
    else:
        errors.append("exception_contract_mismatch")
    proc = runtime(folder, "import loader\\n"
                   "try: loader.load_config(loader.failing_reader)\n"
                   "except OSError: print('PROPAGATED')\n"
                   "else: print('SWALLOWED')")
    observed = proc.stdout.strip()
    if proc.returncode == 0 and observed == "SWALLOWED":
        checks.append("runtime_confirms_declared_exception_is_swallowed")
    else:
        errors.append("exception_swallow_runtime_not_reproduced")
    return {"status": "verified" if not errors else "failed", "checks": checks, "errors": errors,
            "runtime": {"exit_code": proc.returncode, "observed": observed,
                        "stderr_tail": proc.stderr[-800:]},
            "files": {p.name: sha(p) for p in paths}}


def verify_stale_dataflow(root: Path) -> dict:
    folder = root / BASE / "ae32d_dataflow_stale_value_incident"
    paths = [folder / n for n in ("invoice.py", "expected_behavior.json", "incident.md")]
    errors, checks = [], []
    if not all(p.is_file() for p in paths):
        return {"status": "failed", "errors": ["dataflow_fixture_file_missing"], "checks": []}
    tree = ast.parse(paths[0].read_text(encoding="utf-8"))
    contract = json.loads(paths[1].read_text(encoding="utf-8"))
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "invoice_total"), None)
    assigned_discounted = bool(fn) and any(
        isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "discounted"
        for target in n.targets for t in ast.walk(target)) for n in fn.body
    )
    return_uses_stale_subtotal = bool(fn) and any(
        isinstance(n, ast.Return) and isinstance(n.value, ast.BinOp)
        and isinstance(n.value.left, ast.Name) and n.value.left.id == "subtotal"
        for n in ast.walk(fn)
    )
    if assigned_discounted and return_uses_stale_subtotal:
        checks.append("discounted_intermediate_not_consumed_at_return_sink")
    else:
        errors.append("stale_dataflow_ast_pattern_not_found")
    expected = contract.get("input_cases") == [
        {"arguments": [100, 10, 5], "expected": {"kind": "return", "value": 95}}
    ]
    if expected:
        checks.append("discounted_total_contract_declared")
    else:
        errors.append("dataflow_contract_mismatch")
    proc = runtime(folder, "import invoice; print(invoice.invoice_total(100, 10, 5))")
    observed = proc.stdout.strip()
    if proc.returncode == 0 and observed == "105":
        checks.append("runtime_reproduces_stale_value_at_output")
    else:
        errors.append("stale_dataflow_runtime_not_reproduced")
    return {"status": "verified" if not errors else "failed", "checks": checks, "errors": errors,
            "runtime": {"exit_code": proc.returncode, "observed": observed,
                        "expected": 95, "stderr_tail": proc.stderr[-800:]},
            "files": {p.name: sha(p) for p in paths}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = (args.source_root or Path(os.environ["AE32D_EXTENDED_SOURCE_ROOT"])).resolve()
    errors = []
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        head = None
        errors.append("extended_source_identity_unavailable:" + type(exc).__name__)
    if head != PINNED_SOURCE_COMMIT:
        errors.append("extended_source_head_does_not_match_pin")
    cases = {"exception_swallow": verify_exception_swallow(root),
             "stale_dataflow": verify_stale_dataflow(root)}
    if any(v["status"] != "verified" or v["errors"] for v in cases.values()):
        errors.append("one_or_more_extended_cases_failed")
    report = {
        "schema_version": "ae32d/extended-case-verification/v1",
        "pinned_source_commit": PINNED_SOURCE_COMMIT,
        "observed_source_commit": head,
        "status": "machine_verified_extended_cases" if not errors else "machine_verification_failed",
        "primary_benchmark_eligible": False,
        "human_independent_adjudication": "not_performed",
        "cases": cases,
        "errors": errors,
        "limitations": ["Synthetic fixture verification is not independent gold adjudication.",
                        "The verifier does not claim general audit-engine accuracy."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "source_commit": head,
                      "case_statuses": {k: v["status"] for k, v in cases.items()},
                      "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

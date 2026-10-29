#!/usr/bin/env python3
"""Machine-check the AE-32D provider-interface candidate without human-review claims."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED = [
    "main.py",
    "pipeline/extractor.py",
    "providers/adapter.py",
    "providers/factory.py",
    "tests/checks.py",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def line_of(node: ast.AST) -> int | None:
    return getattr(node, "lineno", None)


def attr_accesses(tree: ast.AST, attr: str) -> list[int]:
    return [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and n.attr == attr and isinstance(n.ctx, ast.Load)
    ]


def self_assignments(tree: ast.AST, attr: str) -> list[int]:
    lines: list[int] = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for target in targets:
                for sub in ast.walk(target):
                    if (
                        isinstance(sub, ast.Attribute)
                        and sub.attr == attr
                        and isinstance(sub.value, ast.Name)
                        and sub.value.id == "self"
                    ):
                        lines.append(sub.lineno)
    return sorted(set(lines))


def function_nodes(tree: ast.AST, name: str) -> list[ast.AST]:
    return [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]


def run_check(fixture: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    paths = {rel: fixture / rel for rel in REQUIRED}

    for rel, path in paths.items():
        if not path.is_file():
            errors.append(f"required_file_missing:{rel}")

    if errors:
        return {"passed": False, "errors": errors, "findings": findings}

    raw = {rel: p.read_bytes() for rel, p in paths.items()}
    trees: dict[str, ast.AST] = {}
    for rel, p in paths.items():
        try:
            trees[rel] = ast.parse(raw[rel].decode("utf-8"), filename=rel)
        except (UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"source_parse_failed:{rel}:{type(exc).__name__}")

    if errors:
        return {"passed": False, "errors": errors, "findings": findings}

    extractor = trees["pipeline/extractor.py"]
    adapter = trees["providers/adapter.py"]
    main_tree = trees["main.py"]
    factory = trees["providers/factory.py"]

    consumer_lines = attr_accesses(extractor, "total_calls")
    adapter_total_calls_writes = self_assignments(adapter, "total_calls")
    adapter_calls_writes = self_assignments(adapter, "calls")
    adapter_total_calls_reads = attr_accesses(adapter, "total_calls")

    if not consumer_lines:
        errors.append("expected_consumer_access_total_calls_not_found")
    else:
        findings.append({
            "check": "consumer_reads_total_calls",
            "status": "pass",
            "file": "pipeline/extractor.py",
            "lines": consumer_lines,
            "evidence": "AST contains a load access to provider.total_calls.",
        })

    if not adapter_calls_writes:
        errors.append("adapter_self_calls_assignment_not_found")
    else:
        findings.append({
            "check": "adapter_defines_calls_counter",
            "status": "pass",
            "file": "providers/adapter.py",
            "lines": adapter_calls_writes,
            "evidence": "AST contains an assignment to self.calls.",
        })

    if adapter_total_calls_writes or adapter_total_calls_reads:
        errors.append("adapter_contains_total_calls_member_reference")
    else:
        findings.append({
            "check": "adapter_does_not_define_or_read_total_calls",
            "status": "pass",
            "file": "providers/adapter.py",
            "lines": [],
            "evidence": "AST contains no total_calls attribute access or assignment in adapter.py.",
        })

    main_text = raw["main.py"].decode("utf-8")
    factory_text = raw["providers/factory.py"].decode("utf-8")
    if "return extract(build_provider())" not in main_text:
        errors.append("main_call_path_not_confirmed")
    else:
        findings.append({
            "check": "main_calls_extractor_with_factory_provider",
            "status": "pass",
            "file": "main.py",
            "lines": [next(i for i, line in enumerate(main_text.splitlines(), 1)
                           if "return extract(build_provider())" in line)],
            "evidence": "Main entry point passes the factory-built provider to extract().",
        })

    if "return ProviderAdapter()" not in factory_text:
        errors.append("factory_adapter_construction_not_confirmed")
    else:
        findings.append({
            "check": "factory_constructs_provider_adapter",
            "status": "pass",
            "file": "providers/factory.py",
            "lines": [next(i for i, line in enumerate(factory_text.splitlines(), 1)
                           if "return ProviderAdapter()" in line)],
            "evidence": "Factory returns a ProviderAdapter instance.",
        })

    # Dynamic reproduction is intentionally restricted to this known, small fixture entry point.
    proc = subprocess.run(
        [sys.executable, "main.py"],
        cwd=fixture,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    runtime_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    runtime_match = (
        proc.returncode != 0
        and "AttributeError" in runtime_text
        and "total_calls" in runtime_text
        and "ProviderAdapter" in runtime_text
    )
    if runtime_match:
        findings.append({
            "check": "runtime_reproduces_expected_attribute_error",
            "status": "pass",
            "file": "main.py",
            "lines": [],
            "evidence": "Executing the controlled fixture exits nonzero with AttributeError referencing ProviderAdapter.total_calls.",
            "exit_code": proc.returncode,
        })
    else:
        errors.append("expected_runtime_attribute_error_not_reproduced")
        findings.append({
            "check": "runtime_reproduces_expected_attribute_error",
            "status": "fail",
            "file": "main.py",
            "lines": [],
            "evidence": "Expected ProviderAdapter.total_calls AttributeError was not observed.",
            "exit_code": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-2000:],
        })

    manifest = [
        {"path": rel, "sha256": hashlib.sha256(raw[rel]).hexdigest()}
        for rel in REQUIRED
    ]
    return {
        "passed": not errors,
        "errors": errors,
        "findings": findings,
        "fixture_manifest": manifest,
        "runtime": {
            "exit_code": proc.returncode,
            "expected_attribute_error_observed": runtime_match,
            "stdout": (proc.stdout or "")[-1000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    fixture = args.fixture.resolve()
    result = run_check(fixture)
    source_revision = os.environ.get("GITHUB_SHA") or os.environ.get("SOURCE_REVISION") or "local-unset"
    workflow_run_id = os.environ.get("GITHUB_RUN_ID") or "local-run"
    workflow_revision = os.environ.get("WORKFLOW_REVISION") or source_revision

    report = {
        "schema_version": "ae32d/machine-verification/v1",
        "case_id": "AE32D-CANDIDATE-PROVIDER-INTERFACE-001",
        "verification_mode": "deterministic_static_checks_plus_controlled_runtime_reproduction",
        "status": "machine_verified_candidate" if result["passed"] else "machine_verification_failed",
        "primary_benchmark_eligible": False,
        "human_independent_adjudication": "not_performed",
        "limitations": [
            "This action verifies a narrow, deterministic fixture contract; it is not a human independent review.",
            "A passing result does not establish general audit-engine accuracy or benchmark eligibility.",
            "Source identity is the checked-out revision recorded below; this action does not silently equate it with the older frozen candidate commit.",
        ],
        "source_revision": source_revision,
        "workflow_revision": workflow_revision,
        "workflow_run_id": workflow_run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "source_revision": source_revision,
        "checks_passed": sum(x.get("status") == "pass" for x in result["findings"]),
        "errors": result["errors"],
        "report": str(args.output),
    }, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

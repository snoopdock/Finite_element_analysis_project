#!/usr/bin/env python3
"""Machine-check the fixed AE-32D provider-interface candidate without human-review claims."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIXTURE_RELATIVE_PATH = Path(
    "tests/semantic_audit/fixtures/ae32c_provider_interface_incident"
)
REQUIRED = (
    "main.py",
    "pipeline/extractor.py",
    "providers/adapter.py",
    "providers/factory.py",
    "tests/checks.py",
)


def resolve_fixture(repository_root: Path | str) -> Path:
    """Resolve only the one declared fixture; reject symlinked path components."""
    supplied_root = Path(repository_root).expanduser()
    if supplied_root.is_symlink():
        raise ValueError("repository_root_symlink_rejected")
    try:
        root = supplied_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("repository_root_missing_or_invalid") from exc
    if not root.is_dir():
        raise ValueError("repository_root_missing_or_invalid")

    current = root
    parts = FIXTURE_RELATIVE_PATH.parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            raise ValueError("fixture_component_missing") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("fixture_component_symlink_rejected")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ValueError("fixture_component_not_directory")
        if index == len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ValueError("fixture_not_directory")

    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("fixture_path_escape") from exc
    if resolved != current:
        raise ValueError("fixture_path_resolution_changed")
    return resolved


def _read_required_files(fixture: Path) -> tuple[dict[str, bytes], list[str]]:
    raw: dict[str, bytes] = {}
    errors: list[str] = []
    for relative in REQUIRED:
        current = fixture
        components = Path(relative).parts
        invalid = False
        for index, component in enumerate(components):
            current = current / component
            try:
                info = current.lstat()
            except OSError:
                errors.append(f"required_file_missing:{relative}")
                invalid = True
                break
            if stat.S_ISLNK(info.st_mode):
                errors.append(f"required_file_symlink_rejected:{relative}")
                invalid = True
                break
            if index < len(components) - 1 and not stat.S_ISDIR(info.st_mode):
                errors.append(f"required_parent_not_directory:{relative}")
                invalid = True
                break
            if index == len(components) - 1 and not stat.S_ISREG(info.st_mode):
                errors.append(f"required_file_not_regular:{relative}")
                invalid = True
                break
        if not invalid:
            try:
                raw[relative] = current.read_bytes()
            except OSError:
                errors.append(f"required_file_read_failed:{relative}")
    return raw, errors


def attr_accesses(tree: ast.AST, attr: str) -> list[int]:
    return [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.ctx, ast.Load)
    ]


def self_assignments(tree: ast.AST, attr: str) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for subnode in ast.walk(target):
                    if (
                        isinstance(subnode, ast.Attribute)
                        and subnode.attr == attr
                        and isinstance(subnode.value, ast.Name)
                        and subnode.value.id == "self"
                    ):
                        lines.append(subnode.lineno)
    return sorted(set(lines))


def _runtime_environment() -> dict[str, str]:
    """Pass only basic process-launch variables, never Actions tokens or secrets."""
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_fixture(fixture: Path) -> tuple[bool, dict[str, Any], str | None]:
    command = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        "import runpy, sys; sys.path.insert(0, '.'); runpy.run_path('main.py', run_name='__main__')",
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=fixture,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=15,
            check=False,
            close_fds=True,
            env=_runtime_environment(),
        )
    except subprocess.TimeoutExpired:
        return False, {
            "status": "TIMED_OUT",
            "exit_code": None,
            "expected_attribute_error_observed": False,
            "stdout_tail": "",
            "stderr_tail": "",
        }, "runtime_reproduction_timed_out"
    except OSError as exc:
        return False, {
            "status": "LAUNCH_FAILED",
            "exit_code": None,
            "expected_attribute_error_observed": False,
            "stdout_tail": "",
            "stderr_tail": type(exc).__name__,
        }, "runtime_reproduction_launch_failed"

    runtime_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    matched = (
        proc.returncode != 0
        and "AttributeError" in runtime_text
        and "total_calls" in runtime_text
        and "ProviderAdapter" in runtime_text
    )
    return matched, {
        "status": "EXPECTED_FAILURE_REPRODUCED" if matched else "UNEXPECTED_RUNTIME_RESULT",
        "exit_code": proc.returncode,
        "expected_attribute_error_observed": matched,
        "stdout_tail": (proc.stdout or "")[-1000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }, None if matched else "expected_runtime_attribute_error_not_reproduced"


def run_check(repository_root: Path | str) -> dict[str, Any]:
    """Verify the fixed fixture under a repository root; callers cannot select a path."""
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        fixture = resolve_fixture(repository_root)
    except ValueError as exc:
        return {
            "passed": False,
            "errors": [str(exc)],
            "findings": findings,
            "fixture_path": FIXTURE_RELATIVE_PATH.as_posix(),
        }

    raw, file_errors = _read_required_files(fixture)
    if file_errors:
        return {
            "passed": False,
            "errors": file_errors,
            "findings": findings,
            "fixture_path": FIXTURE_RELATIVE_PATH.as_posix(),
        }

    trees: dict[str, ast.AST] = {}
    for relative in REQUIRED:
        try:
            trees[relative] = ast.parse(
                raw[relative].decode("utf-8"), filename=relative
            )
        except (UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"source_parse_failed:{relative}:{type(exc).__name__}")

    if errors:
        return {
            "passed": False,
            "errors": errors,
            "findings": findings,
            "fixture_path": FIXTURE_RELATIVE_PATH.as_posix(),
        }

    extractor = trees["pipeline/extractor.py"]
    adapter = trees["providers/adapter.py"]
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
            "lines": [
                next(
                    index for index, line in enumerate(main_text.splitlines(), 1)
                    if "return extract(build_provider())" in line
                )
            ],
            "evidence": "Main entry point passes the factory-built provider to extract().",
        })

    if "return ProviderAdapter()" not in factory_text:
        errors.append("factory_adapter_construction_not_confirmed")
    else:
        findings.append({
            "check": "factory_constructs_provider_adapter",
            "status": "pass",
            "file": "providers/factory.py",
            "lines": [
                next(
                    index for index, line in enumerate(factory_text.splitlines(), 1)
                    if "return ProviderAdapter()" in line
                )
            ],
            "evidence": "Factory returns a ProviderAdapter instance.",
        })

    runtime_match, runtime, runtime_error = _run_fixture(fixture)
    if runtime_match:
        findings.append({
            "check": "runtime_reproduces_expected_attribute_error",
            "status": "pass",
            "file": "main.py",
            "lines": [],
            "evidence": "The fixed fixture exits nonzero with AttributeError referencing ProviderAdapter.total_calls.",
            "exit_code": runtime["exit_code"],
        })
    else:
        errors.append(runtime_error or "runtime_reproduction_failed")
        findings.append({
            "check": "runtime_reproduces_expected_attribute_error",
            "status": "fail",
            "file": "main.py",
            "lines": [],
            "evidence": "Expected ProviderAdapter.total_calls AttributeError was not observed.",
            "exit_code": runtime["exit_code"],
            "stderr_tail": runtime["stderr_tail"],
        })

    manifest = [
        {
            "path": relative,
            "sha256": hashlib.sha256(raw[relative]).hexdigest(),
        }
        for relative in REQUIRED
    ]
    return {
        "passed": not errors,
        "errors": errors,
        "findings": findings,
        "fixture_path": FIXTURE_RELATIVE_PATH.as_posix(),
        "fixture_manifest": manifest,
        "runtime": runtime,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    repository_root = Path(__file__).resolve().parents[1]
    result = run_check(repository_root)
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
            "The verifier accepts only the fixed repository fixture; no workflow input selects executable source.",
            "The fixture process runs with Python isolated mode and a minimal environment, but this is not an operating-system sandbox.",
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
        "checks_passed": sum(item.get("status") == "pass" for item in result["findings"]),
        "errors": result["errors"],
        "report": str(args.output),
    }, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

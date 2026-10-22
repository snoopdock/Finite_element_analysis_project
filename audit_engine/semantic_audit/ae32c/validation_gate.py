"""Fail-closed validation prerequisite for AE-32C live provider workflows.

The gate accepts only a completed, successful manual validation run from the
central dispatcher on main, with a detached G9.42 report bound to the exact
source commit and workflow/validation-engine commit. Live callers must still
run the central independent evidence verifier and provenance-catalog verifier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "ae32c/validation-prerequisite/v1"
EXPECTED_BRANCH = "stage1/section-uuids"
EXPECTED_PROFILE = "G9.42"
EXPECTED_WORKFLOW_PATH = ".github/workflows/00_manual_validation_dispatcher.yml"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40,64}\Z")
_RUN_ID_RE = re.compile(r"[0-9]{1,20}\Z")


class ValidationGateError(ValueError):
    """Validation evidence cannot authorize a live provider request."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValidationGateError(code)


def _read_regular(root: Path, name: str, *, max_bytes: int = 4_000_000) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or name in {".", ".."}:
        raise ValidationGateError("unsafe_evidence_filename")
    root = Path(root)
    if root.is_symlink():
        raise ValidationGateError("missing_or_unsafe_evidence_directory")
    root = root.resolve(strict=True)
    path = root / name
    if path.is_symlink() or not path.is_file() or path.resolve(strict=True).parent != root:
        raise ValidationGateError("missing_or_unsafe_evidence_file")
    if path.stat().st_size > max_bytes:
        raise ValidationGateError("evidence_file_too_large")
    return path.read_bytes()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(Path(root).resolve(strict=True)), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    value = result.stdout.strip()
    if result.returncode or _COMMIT_RE.fullmatch(value) is None:
        raise ValidationGateError("cannot_establish_checkout_commit")
    return value


def validate_run_metadata(
    metadata: Mapping[str, Any],
    *,
    expected_run_id: str,
    expected_repository: str | None = None,
) -> dict[str, Any]:
    """Validate the GitHub Actions API record before artifact download/use."""
    _require(isinstance(metadata, Mapping), "invalid_run_metadata")
    _require(_RUN_ID_RE.fullmatch(str(expected_run_id)) is not None, "invalid_validation_run_id")
    _require(str(metadata.get("id", "")) == str(expected_run_id), "validation_run_id_mismatch")
    _require(metadata.get("event") == "workflow_dispatch", "validation_run_not_manual")
    _require(metadata.get("status") == "completed", "validation_run_not_completed")
    _require(metadata.get("conclusion") == "success", "validation_run_not_successful")
    _require(metadata.get("head_branch") == "main", "validation_workflow_not_from_main")
    path = metadata.get("path")
    _require(
        path in {
            EXPECTED_WORKFLOW_PATH,
            EXPECTED_WORKFLOW_PATH + "@refs/heads/main",
        },
        "unexpected_validation_workflow",
    )
    head_sha = metadata.get("head_sha")
    _require(isinstance(head_sha, str) and _COMMIT_RE.fullmatch(head_sha) is not None,
             "invalid_validation_workflow_commit")
    attempt = metadata.get("run_attempt")
    _require(type(attempt) is int and attempt >= 1, "invalid_validation_run_attempt")
    if expected_repository:
        repo = metadata.get("head_repository")
        _require(isinstance(repo, Mapping) and repo.get("full_name") == expected_repository,
                 "validation_run_repository_mismatch")
    return {
        "run_id": str(expected_run_id),
        "run_attempt": str(attempt),
        "engine_commit_sha": head_sha,
        "workflow_path": path,
        "workflow_head_branch": "main",
        "workflow_status": "completed",
        "workflow_conclusion": "success",
    }


def _validate_stage(report: Mapping[str, Any], stage_name: str) -> None:
    results = report.get("results")
    _require(isinstance(results, Mapping), "validation_results_missing")
    entry = results.get(stage_name)
    _require(isinstance(entry, Mapping), f"{stage_name}_result_missing")
    _require(entry.get("status") == "passed", f"{stage_name}_not_passed")
    _require(entry.get("exit_code") == 0, f"{stage_name}_nonzero_exit")
    counts = entry.get("counts")
    _require(isinstance(counts, Mapping), f"{stage_name}_counts_missing")
    tests = counts.get("tests")
    failures = counts.get("failures")
    errors = counts.get("errors")
    skipped = counts.get("skipped")
    _require(type(tests) is int and tests > 0, f"{stage_name}_zero_tests")
    _require(type(failures) is int and failures == 0, f"{stage_name}_failures_present")
    _require(type(errors) is int and errors == 0, f"{stage_name}_errors_present")
    _require(type(skipped) is int and 0 <= skipped < tests, f"{stage_name}_invalid_skips")


def validate_report_binding(
    evidence_dir: Path,
    *,
    run_metadata: Mapping[str, Any],
    expected_run_id: str,
    expected_source_commit: str,
    expected_profile_sha256: str,
) -> dict[str, Any]:
    """Check report identity and detached checksum before independent verification."""
    evidence_dir = Path(evidence_dir).resolve(strict=True)
    report_bytes = _read_regular(evidence_dir, "validation_report.json")
    checksum_bytes = _read_regular(evidence_dir, "validation_report.sha256", max_bytes=1000)
    checksum_text = checksum_bytes.decode("utf-8").strip()
    expected_line = re.fullmatch(r"([0-9a-f]{64})  validation_report\.json", checksum_text)
    _require(expected_line is not None, "invalid_detached_report_digest")
    report_sha = sha256_bytes(report_bytes)
    _require(report_sha == expected_line.group(1), "validation_report_digest_mismatch")
    try:
        report = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationGateError("validation_report_invalid_json") from exc
    _require(isinstance(report, Mapping), "validation_report_not_object")
    _require(report.get("schema_version") in {"1.0", "1.1"}, "unsupported_validation_report_schema")
    _require(report.get("status") == "passed" and report.get("error") is None,
             "validation_report_not_passed")
    _require(report.get("requested_profile") == EXPECTED_PROFILE and
             report.get("profile_id") == EXPECTED_PROFILE, "validation_profile_not_g942")
    _require(report.get("target_branch") == EXPECTED_BRANCH, "validation_target_branch_mismatch")
    _require(report.get("target_commit_sha") == expected_source_commit,
             "validation_source_commit_mismatch")
    _require(report.get("github_run_id") == str(expected_run_id), "validation_report_run_id_mismatch")
    _require(report.get("github_run_attempt") == str(run_metadata["run_attempt"]),
             "validation_report_attempt_mismatch")
    _require(report.get("engine_commit_sha") == run_metadata["engine_commit_sha"],
             "validation_engine_commit_mismatch")
    _require(report.get("profile_sha256") == expected_profile_sha256,
             "validation_profile_digest_mismatch")
    _require(_COMMIT_RE.fullmatch(str(expected_source_commit)) is not None,
             "invalid_expected_source_commit")
    unit = report.get("engine_unit_tests")
    _require(isinstance(unit, Mapping) and unit.get("status") == "passed" and
             type(unit.get("count")) is int and unit.get("count", 0) > 0,
             "validation_engine_unit_tests_not_passed")
    _validate_stage(report, "targeted")
    _validate_stage(report, "regression")

    # The catalog is checked by the trusted central verifier in verify_validation_gate().
    catalog_bytes = _read_regular(evidence_dir / "catalog", "catalog_entry.json", max_bytes=100_000)
    try:
        catalog = json.loads(catalog_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationGateError("validation_catalog_entry_invalid") from exc
    _require(isinstance(catalog, Mapping), "validation_catalog_entry_not_object")
    _require(catalog.get("status") == "passed" and catalog.get("regression_status") == "passed",
             "validation_catalog_not_passed")
    _require(catalog.get("profile_id") == EXPECTED_PROFILE and
             catalog.get("branch") == EXPECTED_BRANCH, "validation_catalog_scope_mismatch")
    _require(catalog.get("source_commit_sha") == expected_source_commit,
             "validation_catalog_source_commit_mismatch")
    _require(catalog.get("engine_commit_sha") == run_metadata["engine_commit_sha"],
             "validation_catalog_engine_commit_mismatch")
    _require(str(catalog.get("github_run_id")) == str(expected_run_id) and
             str(catalog.get("github_run_attempt")) == str(run_metadata["run_attempt"]),
             "validation_catalog_run_binding_mismatch")
    _require(catalog.get("report_sha256") == report_sha, "validation_catalog_report_digest_mismatch")

    receipt_bytes = _read_regular(evidence_dir, "bundle_receipt.json", max_bytes=10_000)
    receipt_sha_file = _read_regular(evidence_dir, "bundle_receipt.sha256", max_bytes=1000).decode("utf-8").strip()
    _require(receipt_sha_file == f"{sha256_bytes(receipt_bytes)}  bundle_receipt.json",
             "validation_bundle_receipt_digest_mismatch")
    try:
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationGateError("validation_bundle_receipt_invalid") from exc
    _require(isinstance(receipt, Mapping), "validation_bundle_receipt_not_object")
    _require(receipt.get("bundle_sha256") == catalog.get("bundle_sha256") and
             receipt.get("byte_size") == catalog.get("bundle_size_bytes"),
             "validation_bundle_receipt_catalog_mismatch")
    _require(receipt.get("report_sha256") == report_sha, "validation_bundle_report_digest_mismatch")
    _require(receipt.get("source_commit_sha") == expected_source_commit and
             receipt.get("engine_commit_sha") == run_metadata["engine_commit_sha"],
             "validation_bundle_commit_binding_mismatch")
    _require(str(receipt.get("github_run_id")) == str(expected_run_id) and
             str(receipt.get("github_run_attempt")) == str(run_metadata["run_attempt"]),
             "validation_bundle_run_binding_mismatch")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "validation_run_id": str(expected_run_id),
        "validation_run_attempt": str(run_metadata["run_attempt"]),
        "validation_profile": EXPECTED_PROFILE,
        "source_branch": EXPECTED_BRANCH,
        "source_commit_sha": expected_source_commit,
        "validation_engine_commit_sha": run_metadata["engine_commit_sha"],
        "validation_report_sha256": report_sha,
        "validation_bundle_sha256": str(catalog["bundle_sha256"]),
        "validation_profile_sha256": expected_profile_sha256,
        "targeted_tests": report["results"]["targeted"]["counts"]["tests"],
        "regression_tests": report["results"]["regression"]["counts"]["tests"],
        "regression_skipped": report["results"]["regression"]["counts"]["skipped"],
    }


def verify_validation_gate(
    evidence_dir: Path,
    *,
    run_metadata_path: Path,
    expected_run_id: str,
    expected_repository: str,
    source_root: Path,
    engine_root: Path,
) -> dict[str, Any]:
    """Bind the downloaded artifact to this checkout, then run trusted verifiers."""
    try:
        metadata = json.loads(Path(run_metadata_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationGateError("validation_run_metadata_unreadable") from exc
    run_binding = validate_run_metadata(
        metadata,
        expected_run_id=expected_run_id,
        expected_repository=expected_repository,
    )
    source_root = Path(source_root).resolve(strict=True)
    engine_root = Path(engine_root).resolve(strict=True)
    source_commit = git_head(source_root)
    profile_path = source_root / "validation" / "profiles" / (EXPECTED_PROFILE + ".yaml")
    if profile_path.is_symlink() or not profile_path.is_file():
        raise ValidationGateError("g942_profile_missing_or_unsafe")
    profile_sha = sha256_bytes(profile_path.read_bytes())
    record = validate_report_binding(
        evidence_dir,
        run_metadata=run_binding,
        expected_run_id=expected_run_id,
        expected_source_commit=source_commit,
        expected_profile_sha256=profile_sha,
    )

    verifier = engine_root / "tools" / "verify_validation_evidence.py"
    catalog_verifier = engine_root / "tools" / "validation_catalog.py"
    if verifier.is_symlink() or not verifier.is_file() or catalog_verifier.is_symlink() or not catalog_verifier.is_file():
        raise ValidationGateError("trusted_validation_verifiers_missing")
    command = [
        sys.executable, str(verifier),
        "--evidence-dir", str(Path(evidence_dir).resolve(strict=True)),
        "--repository", str(source_root),
        "--engine-repository", str(engine_root),
        "--expected-branch", EXPECTED_BRANCH,
        "--expected-run-id", str(expected_run_id),
        "--expected-run-attempt", str(run_binding["run_attempt"]),
        "--require-engine-tests", "--require-pass",
    ]
    verified = subprocess.run(command, capture_output=True, text=True, check=False)
    if verified.stdout:
        print(verified.stdout, file=sys.stderr, end="")
    if verified.stderr:
        print(verified.stderr, file=sys.stderr, end="")
    if verified.returncode != 0:
        raise ValidationGateError("independent_validation_evidence_verification_failed")

    catalog_command = [
        sys.executable, str(catalog_verifier), "verify",
        "--evidence-dir", str(Path(evidence_dir).resolve(strict=True)),
    ]
    catalog_result = subprocess.run(catalog_command, capture_output=True, text=True, check=False)
    if catalog_result.stdout:
        print(catalog_result.stdout, file=sys.stderr, end="")
    if catalog_result.stderr:
        print(catalog_result.stderr, file=sys.stderr, end="")
    if catalog_result.returncode != 0:
        raise ValidationGateError("independent_validation_catalog_verification_failed")
    record["independent_evidence_verification"] = "passed"
    record["independent_catalog_verification"] = "passed"
    return record


def _write_outputs(path: str | None, record: Mapping[str, Any]) -> None:
    if not path:
        return
    output = Path(path)
    with output.open("a", encoding="utf-8") as stream:
        for key, value in record.items():
            if isinstance(value, (str, int, bool)):
                stream.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check-run")
    check.add_argument("--run-metadata", required=True)
    check.add_argument("--expected-run-id", required=True)
    check.add_argument("--expected-repository", required=True)
    check.add_argument("--github-output", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--evidence-dir", required=True)
    verify.add_argument("--run-metadata", required=True)
    verify.add_argument("--expected-run-id", required=True)
    verify.add_argument("--expected-repository", required=True)
    verify.add_argument("--source-root", required=True)
    verify.add_argument("--engine-root", required=True)
    verify.add_argument("--github-output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "check-run":
            metadata = json.loads(Path(args.run_metadata).read_text(encoding="utf-8"))
            record = validate_run_metadata(
                metadata, expected_run_id=args.expected_run_id,
                expected_repository=args.expected_repository,
            )
        else:
            record = verify_validation_gate(
                Path(args.evidence_dir), run_metadata_path=Path(args.run_metadata),
                expected_run_id=args.expected_run_id, expected_repository=args.expected_repository,
                source_root=Path(args.source_root), engine_root=Path(args.engine_root),
            )
        _write_outputs(args.github_output, record)
        print(json.dumps(record, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except (ValidationGateError, OSError, KeyError, TypeError, ValueError) as exc:
        code = str(exc) if isinstance(exc, ValidationGateError) else type(exc).__name__
        print(f"AE-32C validation prerequisite rejected: {code}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

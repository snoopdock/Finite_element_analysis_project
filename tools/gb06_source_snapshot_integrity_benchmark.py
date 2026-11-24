#!/usr/bin/env python3
"""G4 source-snapshot integrity-cost benchmark.

Measures the repository audit/manifest scan, first content load, and second
source-validation pass. It invokes the production snapshot methods on a
minimally initialized RepositoryEvidenceTools instance and deliberately does
not build the semantic graph or initialize a traversal backend.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import platform
import statistics
import sys
from pathlib import Path
from time import perf_counter_ns
from typing import Any
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from audit_engine.semantic_audit.ae32b import evidence_tools as evidence_module
from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools

SCHEMA = "ae32c/m7-g4-source-snapshot-cost/v3"
AUTHORITY = {
    "atomic_repository_snapshot_established": False,
    "backend_auto_selection_permitted": False,
    "performance_winner_established": False,
    "production_approval": False,
    "scientific_approval_permitted": False,
}


class BenchmarkError(ValueError):
    """Invalid source snapshot benchmark configuration or report."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _timing_summary(observations: list[int]) -> dict[str, Any]:
    if len(observations) < 3 or any(type(item) is not int or item < 0 for item in observations):
        raise BenchmarkError("timing_observation_set_invalid")
    ordered = sorted(observations)
    median = statistics.median(ordered)
    return {
        "unit": "ns",
        "observations_ns": observations,
        "median_ns": median,
        "minimum_ns": ordered[0],
        "maximum_ns": ordered[-1],
        "mad_ns": statistics.median([abs(item - median) for item in ordered]),
    }


def _snapshot_phases(repository: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Time production methods without per-file instrumentation in timed phases."""
    measurements: dict[str, Any] = {
        "repository_audit_ns": 0,
        "content_load_ns": 0,
        "second_validation_ns": 0,
        "source_load_file_reads": 0,
        "source_load_bytes_read": 0,
        "source_validation_file_reads": 0,
        "source_validation_bytes_read": 0,
    }
    original_audit = evidence_module.audit_repository
    original_load = RepositoryEvidenceTools._load_indexed_content
    original_validate = RepositoryEvidenceTools._validate_loaded_source_snapshot
    original_read = evidence_module._read_snapshot_file_with_identity

    def timed_audit(*args, **kwargs):
        started = perf_counter_ns()
        try:
            return original_audit(*args, **kwargs)
        finally:
            measurements["repository_audit_ns"] = max(0, perf_counter_ns() - started)

    def timed_load(self):
        started = perf_counter_ns()
        try:
            return original_load(self)
        finally:
            measurements["content_load_ns"] = max(0, perf_counter_ns() - started)

    def timed_validate(self):
        started = perf_counter_ns()
        try:
            return original_validate(self)
        finally:
            measurements["second_validation_ns"] = max(0, perf_counter_ns() - started)

    def new_instance(report):
        instance = RepositoryEvidenceTools.__new__(RepositoryEvidenceTools)
        instance.root = evidence_module._validate_root(repository)
        instance.report = report
        instance.manifest_sha256 = report["audit"]["manifest_sha256"]
        instance.manifest_rows = {
            row["path"]: row for row in report.get("source_manifest", [])
            if row.get("status") == "included"
        }
        instance.evidence_index_status = (
            "complete" if report.get("audit", {}).get("status") == "complete" else "incomplete"
        )
        instance.contents = {}
        instance.file_hashes = {}
        instance.file_sizes = {}
        instance.file_identities = {}
        instance.skipped_sensitive_files = 0
        instance.skipped_non_utf8_files = 0
        return instance

    source_revision = os.environ.get("AE32C_SOURCE_REVISION")
    runner_revision = os.environ.get("AE32C_RUNNER_REVISION")
    started = perf_counter_ns()
    with (
        patch.object(evidence_module, "audit_repository", timed_audit),
        patch.object(RepositoryEvidenceTools, "_load_indexed_content", timed_load),
        patch.object(RepositoryEvidenceTools, "_validate_loaded_source_snapshot", timed_validate),
    ):
        report = evidence_module.audit_repository(
            repository, source_revision=source_revision, runner_revision=runner_revision,
        )
        instance = new_instance(report)
        timed_load(instance)
        timed_validate(instance)
    measurements["source_snapshot_pipeline_ns"] = max(0, perf_counter_ns() - started)

    # Read accounting is replayed outside the timed interval. Wrapping every
    # production read in the timed path would add Python callback/counter
    # overhead to the very operations whose cost is being measured.
    accounting_phase: list[str | None] = [None]

    def counted_read(*args, **kwargs):
        data, identity = original_read(*args, **kwargs)
        current = accounting_phase[0]
        if current == "load":
            measurements["source_load_file_reads"] += 1
            measurements["source_load_bytes_read"] += len(data)
        elif current == "validation":
            measurements["source_validation_file_reads"] += 1
            measurements["source_validation_bytes_read"] += len(data)
        return data, identity

    accounting_instance = new_instance(report)
    with patch.object(evidence_module, "_read_snapshot_file_with_identity", counted_read):
        accounting_phase[0] = "load"
        original_load(accounting_instance)
        accounting_phase[0] = "validation"
        original_validate(accounting_instance)
        accounting_phase[0] = None

    rows = [
        row for rel, row in instance.manifest_rows.items()
        if not evidence_module._is_sensitive_path(rel)
    ]
    measurements["source_file_count"] = len(rows)
    measurements["source_bytes"] = sum(int(row.get("size", 0)) for row in rows)
    measurements["manifest_sha256"] = instance.manifest_sha256
    measurements["manifest_included_file_count"] = int(report["audit"]["included_file_count"])
    measurements["manifest_included_bytes"] = int(report["audit"]["included_bytes"])
    measurements["evidence_index_status"] = instance.evidence_index_status
    measurements["skipped_non_utf8_files"] = instance.skipped_non_utf8_files
    expected_files = measurements["source_file_count"]
    expected_bytes = measurements["source_bytes"]
    if (
        measurements["source_load_file_reads"] != expected_files
        or measurements["source_validation_file_reads"] != expected_files
        or measurements["source_load_bytes_read"] != expected_bytes
        or measurements["source_validation_bytes_read"] != expected_bytes
    ):
        raise BenchmarkError("source_snapshot_read_accounting_mismatch")
    expected_total = (
        measurements["repository_audit_ns"]
        + measurements["content_load_ns"]
        + measurements["second_validation_ns"]
    )
    measurements["unattributed_pipeline_ns"] = (
        measurements["source_snapshot_pipeline_ns"] - expected_total
    )
    if measurements["unattributed_pipeline_ns"] < 0:
        raise BenchmarkError("instrumented_phase_time_exceeds_pipeline_total")
    return report, measurements


def make_report(
    repository: str | Path,
    *,
    repeats: int = 3,
    warmup: int = 1,
) -> dict[str, Any]:
    root = Path(repository).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise BenchmarkError("repository_not_directory")
    if type(repeats) is not int or not 3 <= repeats <= 15:
        raise BenchmarkError("repeats_out_of_bounds")
    if type(warmup) is not int or not 0 <= warmup <= 5:
        raise BenchmarkError("warmup_out_of_bounds")

    samples: list[dict[str, Any]] = []
    accepted_manifest = None
    for index in range(warmup + repeats):
        _audit, observed = _snapshot_phases(root)
        manifest = observed["manifest_sha256"]
        if accepted_manifest is None:
            accepted_manifest = manifest
        elif manifest != accepted_manifest:
            raise BenchmarkError("repository_manifest_changed_between_repeats")
        if index >= warmup:
            samples.append(observed)

    timing_fields = (
        "repository_audit_ns",
        "content_load_ns",
        "second_validation_ns",
        "source_snapshot_pipeline_ns",
        "unattributed_pipeline_ns",
    )
    summaries = {
        field: _timing_summary([int(item[field]) for item in samples])
        for field in timing_fields
    }
    stable_fields = (
        "source_file_count",
        "source_bytes",
        "manifest_included_file_count",
        "manifest_included_bytes",
        "source_load_file_reads",
        "source_load_bytes_read",
        "source_validation_file_reads",
        "source_validation_bytes_read",
        "skipped_non_utf8_files",
    )
    stable = {}
    for field in stable_fields:
        values = [int(item[field]) for item in samples]
        if len(set(values)) != 1:
            raise BenchmarkError(f"unstable_source_accounting:{field}")
        stable[field] = values[0]

    report = {
        "schema_version": SCHEMA,
        "status": "passed",
        "workload": {
            "id": "repository_source_snapshot_integrity",
            "manifest_sha256": accepted_manifest,
            **stable,
        },
        "configuration": {
            "repeats": repeats,
            "warmup": warmup,
            "graph_construction": "excluded",
            "traversal_backend": "not_initialized",
            "timing_boundary": (
                "complete repository audit (inventory, manifest and static analysis), "
                "first source-content load, and second descriptor-identity/hash validation pass"
            ),
        },
        "measurements": {
            **summaries,
            "samples": [
                {field: int(item[field]) for field in timing_fields}
                | {
                    key: int(item[key]) for key in (
                        "source_load_file_reads",
                        "source_load_bytes_read",
                        "source_validation_file_reads",
                        "source_validation_bytes_read",
                    )
                }
                for item in samples
            ],
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "provenance": {
            "source_revision": os.environ.get("AE32C_SOURCE_REVISION"),
            "runner_revision": os.environ.get("AE32C_RUNNER_REVISION"),
            "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
            "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "workflow_name": os.environ.get("GITHUB_WORKFLOW"),
        },
        "authority": dict(AUTHORITY),
        "interpretation": (
            "Repository-specific source snapshot cost characterization. "
            "The production repository audit, first content load and second "
            "validation methods are timed separately; per-file read accounting "
            "is replayed outside the timed interval to avoid callback overhead. "
            "Graph construction and native backend setup are deliberately excluded. This does not "
            "establish atomic snapshot semantics, universal overhead, or "
            "production approval."
        ),
    }
    report["report_sha256"] = _digest(report)
    return report


def verify_report(
    report: dict[str, Any],
    repository: str | Path,
    *,
    expected_source_revision: str | None = None,
    expected_runner_revision: str | None = None,
) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA:
        raise BenchmarkError("unknown_report_schema")
    payload = dict(report)
    submitted = payload.pop("report_sha256", None)
    if submitted != _digest(payload):
        raise BenchmarkError("report_digest_mismatch")
    if payload.get("status") != "passed" or payload.get("authority") != AUTHORITY:
        raise BenchmarkError("report_authority_or_status_invalid")

    config = payload.get("configuration", {})
    repeats = config.get("repeats")
    warmup = config.get("warmup")
    if type(repeats) is not int or not 3 <= repeats <= 15:
        raise BenchmarkError("report_repeat_configuration_invalid")
    if type(warmup) is not int or not 0 <= warmup <= 5:
        raise BenchmarkError("report_warmup_configuration_invalid")
    samples = payload.get("measurements", {}).get("samples")
    if not isinstance(samples, list) or len(samples) != repeats:
        raise BenchmarkError("sample_count_mismatch")

    timing_fields = (
        "repository_audit_ns",
        "content_load_ns",
        "second_validation_ns",
        "source_snapshot_pipeline_ns",
        "unattributed_pipeline_ns",
    )
    for field in timing_fields:
        observations = [item.get(field) for item in samples]
        recomputed = _timing_summary(observations)
        supplied = payload["measurements"].get(field, {})
        if supplied.get("unit") != "ns" or supplied.get("observations_ns") != observations:
            raise BenchmarkError(f"timing_observations_mismatch:{field}")
        for key in ("median_ns", "minimum_ns", "maximum_ns", "mad_ns"):
            if supplied.get(key) != recomputed[key]:
                raise BenchmarkError(f"timing_aggregate_mismatch:{field}:{key}")

    workload = payload.get("workload", {})
    root = Path(repository).expanduser().resolve(strict=True)
    reconstructed = evidence_module.audit_repository(root)
    audit = reconstructed.get("audit", {})
    if (
        audit.get("manifest_sha256") != workload.get("manifest_sha256")
        or audit.get("included_file_count") != workload.get("manifest_included_file_count")
        or audit.get("included_bytes") != workload.get("manifest_included_bytes")
    ):
        raise BenchmarkError("source_manifest_reconstruction_mismatch")

    manifest_rows = reconstructed.get("source_manifest", [])
    expected_rows = [
        row for row in manifest_rows
        if row.get("status") == "included"
        and isinstance(row.get("path"), str)
        and not evidence_module._is_sensitive_path(row["path"])
    ]
    expected_source_count = len(expected_rows)
    expected_source_bytes = sum(int(row["size"]) for row in expected_rows)
    if (
        workload.get("source_file_count") != expected_source_count
        or workload.get("source_bytes") != expected_source_bytes
    ):
        raise BenchmarkError("source_read_accounting_does_not_match_manifest")

    source_files = workload.get("source_file_count")
    source_bytes = workload.get("source_bytes")
    for item in samples:
        if (
            item.get("source_load_file_reads") != source_files
            or item.get("source_validation_file_reads") != source_files
            or item.get("source_load_bytes_read") != source_bytes
            or item.get("source_validation_bytes_read") != source_bytes
        ):
            raise BenchmarkError("source_read_accounting_invalid")
        if item.get("source_snapshot_pipeline_ns") != (
            item.get("repository_audit_ns", 0)
            + item.get("content_load_ns", 0)
            + item.get("second_validation_ns", 0)
            + item.get("unattributed_pipeline_ns", 0)
        ):
            raise BenchmarkError("source_pipeline_time_decomposition_invalid")

    provenance = payload.get("provenance", {})
    for label, expected, actual in (
        ("source", expected_source_revision, provenance.get("source_revision")),
        ("runner", expected_runner_revision, provenance.get("runner_revision")),
    ):
        if expected is not None:
            if (
                not isinstance(expected, str)
                or len(expected) != 40
                or any(ch not in "0123456789abcdefABCDEF" for ch in expected)
                or actual != expected.lower()
            ):
                raise BenchmarkError(f"{label}_revision_provenance_mismatch")

    return {
        "status": "verified",
        "manifest_sha256": workload["manifest_sha256"],
        "repeats": repeats,
        "report_sha256": submitted,
        "source_revision": provenance.get("source_revision"),
        "runner_revision": provenance.get("runner_revision"),
        "atomic_snapshot_established": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--repository", required=True)
    run_parser.add_argument("--repeats", type=int, default=3)
    run_parser.add_argument("--warmup", type=int, default=1)
    run_parser.add_argument("--report", required=True)
    run_parser.add_argument("--expected-source-revision")
    run_parser.add_argument("--expected-runner-revision")
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--repository", required=True)
    verify_parser.add_argument("--report", required=True)
    verify_parser.add_argument("--expected-source-revision")
    verify_parser.add_argument("--expected-runner-revision")
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            report = make_report(
                args.repository, repeats=args.repeats, warmup=args.warmup,
            )
            path = Path(args.report)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(verify_report(
                report, args.repository,
                expected_source_revision=args.expected_source_revision,
                expected_runner_revision=args.expected_runner_revision,
            ), sort_keys=True))
        else:
            path = Path(args.report)
            report = json.loads(path.read_text(encoding="utf-8"))
            print(json.dumps(verify_report(
                report, args.repository,
                expected_source_revision=args.expected_source_revision,
                expected_runner_revision=args.expected_runner_revision,
            ), sort_keys=True))
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

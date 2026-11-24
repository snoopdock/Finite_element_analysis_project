#!/usr/bin/env python3
"""G4 source-snapshot integrity-cost benchmark.

Measures repository audit/manifest construction, the first source-content
load, the second source-validation pass, and total RepositoryEvidenceTools
construction separately. Uses the reference graph backend so native graph
backend setup does not contaminate source-snapshot timings.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
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

SCHEMA = "ae32c/m7-g4-source-snapshot-cost/v1"
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
        "p95_ns": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        "minimum_ns": ordered[0],
        "maximum_ns": ordered[-1],
        "mad_ns": statistics.median([abs(item - median) for item in ordered]),
    }


def _instrumented_construction(repository: Path) -> tuple[RepositoryEvidenceTools, dict[str, Any]]:
    """Measure the three source-inspection phases without production edits."""
    measurements: dict[str, Any] = {
        "repository_audit_ns": 0,
        "content_load_ns": 0,
        "second_validation_ns": 0,
        "source_load_file_reads": 0,
        "source_load_bytes_read": 0,
        "source_validation_file_reads": 0,
        "source_validation_bytes_read": 0,
    }
    phase: list[str | None] = [None]

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
        phase[0] = "load"
        started = perf_counter_ns()
        try:
            return original_load(self)
        finally:
            measurements["content_load_ns"] = max(0, perf_counter_ns() - started)
            phase[0] = None

    def timed_validate(self):
        phase[0] = "validation"
        started = perf_counter_ns()
        try:
            return original_validate(self)
        finally:
            measurements["second_validation_ns"] = max(0, perf_counter_ns() - started)
            phase[0] = None

    def counted_read(*args, **kwargs):
        data, identity = original_read(*args, **kwargs)
        current = phase[0]
        if current == "load":
            measurements["source_load_file_reads"] += 1
            measurements["source_load_bytes_read"] += len(data)
        elif current == "validation":
            measurements["source_validation_file_reads"] += 1
            measurements["source_validation_bytes_read"] += len(data)
        return data, identity

    started = perf_counter_ns()
    with (
        patch.object(evidence_module, "audit_repository", timed_audit),
        patch.object(RepositoryEvidenceTools, "_load_indexed_content", timed_load),
        patch.object(RepositoryEvidenceTools, "_validate_loaded_source_snapshot", timed_validate),
        patch.object(evidence_module, "_read_snapshot_file_with_identity", counted_read),
    ):
        instance = RepositoryEvidenceTools(repository, graph_backend="reference")
    measurements["constructor_total_ns"] = max(0, perf_counter_ns() - started)

    rows = [
        row for rel, row in instance.manifest_rows.items()
        if not evidence_module._is_sensitive_path(rel)
    ]
    measurements["indexed_file_count"] = len(rows)
    measurements["indexed_bytes"] = sum(int(row.get("size", 0)) for row in rows)
    measurements["remaining_constructor_ns"] = (
        measurements["constructor_total_ns"]
        - measurements["repository_audit_ns"]
        - measurements["content_load_ns"]
        - measurements["second_validation_ns"]
    )
    if measurements["remaining_constructor_ns"] < 0:
        raise BenchmarkError("instrumented_phase_time_exceeds_constructor_total")
    expected_files = measurements["indexed_file_count"]
    expected_bytes = measurements["indexed_bytes"]
    if (
        measurements["source_load_file_reads"] != expected_files
        or measurements["source_validation_file_reads"] != expected_files
        or measurements["source_load_bytes_read"] != expected_bytes
        or measurements["source_validation_bytes_read"] != expected_bytes
    ):
        raise BenchmarkError("source_snapshot_read_accounting_mismatch")
    measurements["manifest_sha256"] = instance.manifest_sha256
    measurements["manifest_included_file_count"] = int(
        instance.report.get("audit", {}).get("included_file_count", 0)
    )
    measurements["manifest_included_bytes"] = int(
        instance.report.get("audit", {}).get("included_bytes", 0)
    )
    measurements["evidence_index_status"] = instance.evidence_index_status
    return instance, measurements


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
        _instance, observed = _instrumented_construction(root)
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
        "constructor_total_ns",
        "remaining_constructor_ns",
    )
    summaries = {
        field: _timing_summary([int(item[field]) for item in samples])
        for field in timing_fields
    }
    stable_fields = (
        "indexed_file_count",
        "indexed_bytes",
        "manifest_included_file_count",
        "manifest_included_bytes",
        "source_load_file_reads",
        "source_load_bytes_read",
        "source_validation_file_reads",
        "source_validation_bytes_read",
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
            "graph_backend": "reference",
            "timing_boundary": (
                "repository audit, first content load, second source validation, "
                "and total RepositoryEvidenceTools construction"
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
            "source_revision": __import__("os").environ.get("AE32C_SOURCE_REVISION"),
            "workflow_run_id": __import__("os").environ.get("GITHUB_RUN_ID"),
            "workflow_run_attempt": __import__("os").environ.get("GITHUB_RUN_ATTEMPT"),
            "workflow_name": __import__("os").environ.get("GITHUB_WORKFLOW"),
        },
        "authority": dict(AUTHORITY),
        "interpretation": (
            "Repository-specific source snapshot cost characterization. "
            "The second pass is timed separately from manifest construction and "
            "first content loading. The reference graph backend avoids native "
            "backend setup. This does not establish atomic snapshot semantics, "
            "universal overhead, or production approval."
        ),
    }
    report["report_sha256"] = _digest(report)
    return report


def verify_report(report: dict[str, Any], repository: str | Path) -> dict[str, Any]:
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
    if type(repeats) is not int or not 3 <= repeats <= 15:
        raise BenchmarkError("report_repeat_configuration_invalid")
    samples = payload.get("measurements", {}).get("samples")
    if not isinstance(samples, list) or len(samples) != repeats:
        raise BenchmarkError("sample_count_mismatch")

    timing_fields = (
        "repository_audit_ns",
        "content_load_ns",
        "second_validation_ns",
        "constructor_total_ns",
        "remaining_constructor_ns",
    )
    for field in timing_fields:
        observations = [item.get(field) for item in samples]
        recomputed = _timing_summary(observations)
        supplied = payload["measurements"].get(field, {})
        for key in ("median_ns", "p95_ns", "minimum_ns", "maximum_ns", "mad_ns"):
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

    indexed_files = workload.get("indexed_file_count")
    indexed_bytes = workload.get("indexed_bytes")
    for item in samples:
        if (
            item.get("source_load_file_reads") != indexed_files
            or item.get("source_validation_file_reads") != indexed_files
            or item.get("source_load_bytes_read") != indexed_bytes
            or item.get("source_validation_bytes_read") != indexed_bytes
        ):
            raise BenchmarkError("source_read_accounting_invalid")
        if item.get("remaining_constructor_ns", -1) < 0:
            raise BenchmarkError("negative_remaining_constructor_time")
        if item.get("constructor_total_ns") != (
            item.get("repository_audit_ns", 0)
            + item.get("content_load_ns", 0)
            + item.get("second_validation_ns", 0)
            + item.get("remaining_constructor_ns", 0)
        ):
            raise BenchmarkError("constructor_time_decomposition_invalid")

    return {
        "status": "verified",
        "manifest_sha256": workload["manifest_sha256"],
        "repeats": repeats,
        "report_sha256": submitted,
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
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--repository", required=True)
    verify_parser.add_argument("--report", required=True)
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
            print(json.dumps(verify_report(report, args.repository), sort_keys=True))
        else:
            path = Path(args.report)
            report = json.loads(path.read_text(encoding="utf-8"))
            print(json.dumps(verify_report(report, args.repository), sort_keys=True))
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

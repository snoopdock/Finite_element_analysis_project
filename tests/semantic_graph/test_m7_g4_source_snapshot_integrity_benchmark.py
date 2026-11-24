"""G4 source snapshot integrity-cost benchmark contract tests."""
from copy import deepcopy

import pytest

from tools import gb06_source_snapshot_integrity_benchmark as benchmark


def _repository(root):
    (root / "src" / "sample_pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "README.md").write_text("# Snapshot fixture\n", encoding="utf-8")
    (root / "src" / "sample_pkg" / "__init__.py").write_text(
        '"""Fixture package."""\n', encoding="utf-8",
    )
    (root / "src" / "sample_pkg" / "core.py").write_text(
        "def add(left, right):\n    return left + right\n", encoding="utf-8",
    )
    (root / "tests" / "test_core.py").write_text(
        "from sample_pkg.core import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    return root


def _rehash(report):
    report["report_sha256"] = benchmark._digest({
        key: value for key, value in report.items()
        if key != "report_sha256"
    })
    return report


@pytest.fixture(scope="module")
def source_report(tmp_path_factory):
    root = _repository(tmp_path_factory.mktemp("source-snapshot") / "repo")
    return root, benchmark.make_report(root, repeats=3, warmup=0)


def test_source_snapshot_report_reconstructs_and_verifies(source_report):
    root, report = source_report
    verified = benchmark.verify_report(report, root)
    assert verified["status"] == "verified"
    assert verified["atomic_snapshot_established"] is False
    assert report["configuration"]["graph_construction"] == "excluded"
    assert report["configuration"]["traversal_backend"] == "not_initialized"
    assert report["workload"]["indexed_file_count"] >= 3
    assert report["workload"]["indexed_bytes"] > 0


def test_both_source_passes_read_every_indexed_file_and_byte(source_report):
    _root, report = source_report
    workload = report["workload"]
    for sample in report["measurements"]["samples"]:
        assert sample["source_load_file_reads"] == workload["indexed_file_count"]
        assert sample["source_validation_file_reads"] == workload["indexed_file_count"]
        assert sample["source_load_bytes_read"] == workload["indexed_bytes"]
        assert sample["source_validation_bytes_read"] == workload["indexed_bytes"]


def test_rehashed_second_validation_timing_forgery_is_rejected(source_report):
    root, report = source_report
    forged = deepcopy(report)
    forged["measurements"]["second_validation_ns"]["median_ns"] += 1
    _rehash(forged)
    with pytest.raises(benchmark.BenchmarkError, match="timing_aggregate_mismatch"):
        benchmark.verify_report(forged, root)


def test_rehashed_source_read_accounting_forgery_is_rejected(source_report):
    root, report = source_report
    forged = deepcopy(report)
    forged["measurements"]["samples"][0]["source_validation_file_reads"] += 1
    _rehash(forged)
    with pytest.raises(benchmark.BenchmarkError, match="source_read_accounting_invalid"):
        benchmark.verify_report(forged, root)


@pytest.mark.parametrize("repeats,warmup", [(2, 0), (16, 0), (3, -1), (3, 6), (True, 0)])
def test_invalid_source_benchmark_budget_is_rejected(tmp_path, repeats, warmup):
    root = _repository(tmp_path / "repo")
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.make_report(root, repeats=repeats, warmup=warmup)

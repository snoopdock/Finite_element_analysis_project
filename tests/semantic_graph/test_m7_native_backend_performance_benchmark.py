"""M7.1: parity-gated native backend benchmark scaffold tests."""
from copy import deepcopy

import pytest

from tools import gb05_native_backend_performance_benchmark as m7


def _rehash(report):
    report["report_sha256"] = m7._digest({
        key: value for key, value in report.items()
        if key != "report_sha256"
    })
    return report


@pytest.fixture(scope="module")
def networkx_report():
    return m7.make_report("networkx", repeats=3, warmup=0)


def test_networkx_m71_report_passes_independent_reference_replay(networkx_report):
    verified = m7.verify_report(networkx_report)
    assert verified["status"] == "verified"
    assert verified["backend"] == "networkx"
    assert verified["query_count"] == 7
    assert verified["winner_established"] is False


def test_every_timed_query_records_native_execution(networkx_report):
    assert networkx_report["native_query_mode"] == m7.NATIVE_MODES["networkx"]
    for query in networkx_report["measurements"]["queries"]:
        assert query["native_metrics_delta"]["native_adjacency_lookups"] >= 3
        assert query["native_metrics_delta"]["native_edge_occurrences_read"] > 0
        assert len(query["timing"]["observations_ns"]) == 3


def test_rehashed_result_forgery_is_rejected(networkx_report):
    forged = deepcopy(networkx_report)
    forged["measurements"]["queries"][0]["result_sha256"] = "0" * 64
    _rehash(forged)
    with pytest.raises(m7.BenchmarkError, match="reference_result_digest_mismatch"):
        m7.verify_report(forged)


def test_rehashed_aggregate_forgery_is_rejected(networkx_report):
    forged = deepcopy(networkx_report)
    forged["measurements"]["queries"][0]["timing"]["median_ns"] += 1
    _rehash(forged)
    with pytest.raises(m7.BenchmarkError, match="timing_aggregate_mismatch"):
        m7.verify_report(forged)


def test_authority_and_backend_selection_are_never_granted(networkx_report):
    forged = deepcopy(networkx_report)
    forged["authority"]["production_approval"] = True
    _rehash(forged)
    with pytest.raises(m7.BenchmarkError, match="authority_boundary"):
        m7.verify_report(forged)

    forged = deepcopy(networkx_report)
    forged["recommended_backend"] = "networkx"
    _rehash(forged)
    with pytest.raises(m7.BenchmarkError, match="must_not_select"):
        m7.verify_report(forged)


@pytest.mark.parametrize("backend", ["", "networkx ", "snap-worker", "auto"])
def test_unknown_backend_is_rejected(backend):
    with pytest.raises(m7.BenchmarkError, match="unknown_backend"):
        m7.make_report(backend, repeats=3, warmup=0)


@pytest.mark.parametrize("repeats,warmup", [(2, 0), (16, 0), (3, -1), (3, 6), (True, 0)])
def test_invalid_timing_budget_is_rejected(repeats, warmup):
    with pytest.raises(m7.BenchmarkError):
        m7.make_report("networkx", repeats=repeats, warmup=warmup)

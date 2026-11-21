"""M7.2: seeded task-suitability workload and report-integrity tests."""
from copy import deepcopy

import pytest

from tools import gb06_task_suitability_campaign as m72


@pytest.fixture(scope="module")
def networkx_report():
    return m72.make_report(
        "networkx", seeds=[20261101, 20261102], repeats=3, warmup=0,
        workload_ids=["parallel_evidence", "disconnected_components"],
    )


def _rehash(report):
    report["report_sha256"] = m72._digest({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    return report


def test_seeded_workloads_are_reproducible_and_seed_sensitive():
    first = m72._make_graph("hub_impact", 21)
    repeated = m72._make_graph("hub_impact", 21)
    changed = m72._make_graph("hub_impact", 22)
    assert m72._digest(first.to_dict()) == m72._digest(repeated.to_dict())
    assert m72._digest(first.to_dict()) != m72._digest(changed.to_dict())


def test_workload_families_encode_distinct_audit_shapes():
    sparse = m72._make_graph("sparse_dependency", 7)
    parallel = m72._make_graph("parallel_evidence", 7)
    disconnected = m72._make_graph("disconnected_components", 7)
    assert len(sparse.nodes) == 48
    assert len(sparse.edges) == 96
    endpoint_pairs = [(e.source_id, e.target_id) for e in parallel.edges]
    assert len(endpoint_pairs) > len(set(endpoint_pairs))
    assert all(
        int(edge.source_id.split("-")[1]) // 8
        == int(edge.target_id.split("-")[1]) // 8
        for edge in disconnected.edges
    )


def test_report_reconstructs_seeded_workloads_and_reference_results(networkx_report):
    result = m72.verify_report(networkx_report)
    assert result["status"] == "verified"
    assert result["backend"] == "networkx"
    assert result["case_count"] == 4
    assert result["seed_count"] == 2
    assert result["performance_winner_established"] is False
    assert result["task_suitability_decision_established"] is False


def test_every_query_has_native_path_and_requested_sample_count(networkx_report):
    for case in networkx_report["cases"]:
        assert case["native_execution"]["native_query_mode"] == m72.NATIVE_MODES["networkx"]
        assert case["native_execution"]["preflight_parity_failures"] == 0
        for query in case["measurements"]["queries"]:
            assert query["measured_calls"] == 3
            assert query["warmup_calls"] == 0
            assert len(query["timing"]["observations_ns"]) == 3
            assert query["native_metrics_delta"]["native_adjacency_lookups"] >= 3


def test_report_does_not_rank_libraries_or_decide_task_suitability(networkx_report):
    assert networkx_report["authority"] == m72.AUTHORITY
    assert "not competitors" in networkx_report["interpretation"]
    assert "recommended_backend" not in networkx_report
    assert "performance_winner" not in networkx_report


def test_rehashed_timing_aggregate_forgery_is_rejected(networkx_report):
    forged = deepcopy(networkx_report)
    forged["cases"][0]["measurements"]["queries"][0]["timing"]["median_ns"] += 1
    _rehash(forged)
    with pytest.raises(m72.BenchmarkError, match="timing_aggregate_mismatch"):
        m72.verify_report(forged)


def test_rehashed_workload_forgery_is_rejected(networkx_report):
    forged = deepcopy(networkx_report)
    forged["cases"][0]["workload"]["graph_sha256"] = "0" * 64
    _rehash(forged)
    with pytest.raises(m72.BenchmarkError, match="workload_reconstruction_mismatch"):
        m72.verify_report(forged)


def test_rehashed_authority_escalation_is_rejected(networkx_report):
    forged = deepcopy(networkx_report)
    forged["authority"]["production_approval"] = True
    _rehash(forged)
    with pytest.raises(m72.BenchmarkError, match="task_scope_or_authority"):
        m72.verify_report(forged)


@pytest.mark.parametrize("seeds", [[], [1], [1, 1], [2, 1], [-1, 2], [1.5, 2]])
def test_invalid_seed_sets_are_rejected(seeds):
    with pytest.raises(m72.BenchmarkError, match="seeds"):
        m72.make_report("networkx", seeds=seeds, workload_ids=["sparse_dependency"])


@pytest.mark.parametrize("repeats,warmup", [(2, 0), (16, 0), (3, -1), (3, 6), (True, 0)])
def test_invalid_measurement_budgets_are_rejected(repeats, warmup):
    with pytest.raises(m72.BenchmarkError):
        m72.make_report(
            "networkx", seeds=[1, 2], repeats=repeats, warmup=warmup,
            workload_ids=["sparse_dependency"],
        )


def test_unknown_backend_and_workload_are_rejected():
    with pytest.raises(m72.BenchmarkError, match="unknown_backend"):
        m72.make_report("auto", seeds=[1, 2])
    with pytest.raises(m72.BenchmarkError, match="invalid_workload"):
        m72.make_report("networkx", seeds=[1, 2], workload_ids=["unknown"])



def test_rehashed_mixed_environment_inside_backend_report_is_rejected(networkx_report):
    forged = deepcopy(networkx_report)
    forged["cases"][1]["environment"]["python"] = "0.0"
    _rehash(forged)
    with pytest.raises(m72.BenchmarkError, match="mixed_environment"):
        m72.verify_report(forged)


def test_rehashed_workload_description_forgery_is_rejected(networkx_report):
    forged = deepcopy(networkx_report)
    forged["cases"][0]["workload"]["purpose"] = "fabricated task"
    _rehash(forged)
    with pytest.raises(m72.BenchmarkError, match="workload_reconstruction_mismatch"):
        m72.verify_report(forged)

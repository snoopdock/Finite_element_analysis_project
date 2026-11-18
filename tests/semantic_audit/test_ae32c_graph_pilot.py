from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from audit_engine.semantic_audit.ae32c.graph_pilot import (
    _build_cost_estimator,
    _load_profile,
    build_scoped_snapshot,
)
from audit_engine.semantic_audit.ae32c.investigator import RepositoryInvestigator


class _Provider:
    model = "test-model"

    def get_stats(self):
        return {}


class _EvidenceTools:
    manifest_sha256 = "manifest"
    graph_fingerprint = "graph"
    manifest_rows = {}
    file_hashes = {}


def _investigator(tmp_path, *, graph_enabled=True, require_graph=False):
    return RepositoryInvestigator(
        tmp_path,
        _Provider(),
        evidence_tools=_EvidenceTools(),
        enable_graph_tools=graph_enabled,
        require_graph_interaction=require_graph,
        required_graph_target="symbol:target" if require_graph else None,
    )


def test_graph_tools_can_be_removed_for_matched_control(tmp_path):
    investigator = _investigator(tmp_path, graph_enabled=False)
    names = {item["function"]["name"] for item in investigator._tool_definitions}

    assert "graph_neighbors" not in names
    assert "graph_path" not in names
    coverage = investigator._graph_interaction_coverage()
    assert coverage["status"] == "disabled"
    assert coverage["tools_available"] is False
    assert coverage["graph_queries"] == []
    assert coverage["graph_derived_verified_read_paths"] == []



def test_graph_tool_ablation_changes_only_graph_tool_availability(tmp_path):
    control = _investigator(tmp_path, graph_enabled=False)
    treatment = _investigator(tmp_path, graph_enabled=True)
    control_names = {item["function"]["name"] for item in control._tool_definitions}
    treatment_names = {item["function"]["name"] for item in treatment._tool_definitions}
    graph_tools = {"graph_neighbors", "graph_path"}

    assert not (control_names & graph_tools)
    assert (treatment_names & graph_tools) == graph_tools
    assert (control_names - graph_tools) == (treatment_names - graph_tools)

def test_graph_interaction_requires_graph_tools_to_be_available(tmp_path):
    try:
        RepositoryInvestigator(
            tmp_path,
            _Provider(),
            evidence_tools=_EvidenceTools(),
            enable_graph_tools=False,
            require_graph_interaction=True,
            required_graph_target="symbol:target",
        )
    except ValueError as exc:
        assert "graph tools are disabled" in str(exc)
    else:
        raise AssertionError("required graph interaction accepted with graph tools disabled")


def test_graph_follow_through_counts_only_new_reads_after_query(tmp_path):
    investigator = _investigator(tmp_path, graph_enabled=True, require_graph=True)
    investigator._ledger = [
        SimpleNamespace(
            evidence_id="E0001",
            tool="read_source_file",
            arguments={"path": "target.py"},
            status="ok",
            response={"result": {
                "path": "target.py", "source_sha256": "target-hash",
                "source_range_complete": True, "requested_start_line": 1,
                "requested_end_line": 20, "start_line": 1, "end_line": 20,
                "total_lines": 20, "truncated": False, "end_clamped_to_eof": False,
            }},
        ),
        SimpleNamespace(
            evidence_id="E0002",
            tool="graph_neighbors",
            arguments={"node": "symbol:target"},
            status="ok",
            response={
                "result": {
                    "coverage_status": "complete_for_query",
                    "truncated": False,
                    "observed_relation_types": ["CALLS"],
                    "source_paths": ["target.py", "caller.py"],
                    "source_nodes": [
                        {"node_id": "node:target", "name": "target", "path": "target.py", "line": 1, "source_sha256": "target-hash"}
                    ],
                    "discovered_nodes": [
                        {"node_id": "node:caller", "name": "caller", "path": "caller.py", "line": 10, "source_sha256": "caller-hash"}
                    ],
                    "observations": [
                        {
                            "observation_id": "obs:1",
                            "subject_id": "node:caller",
                            "predicate": "CALLS",
                            "object_id": "node:target",
                            "evidence_ids": ["edge:1"],
                            "depth": 1,
                        }
                    ],
                    "evidence": [
                        {
                            "evidence_id": "edge:1",
                            "provenance": {
                                "edge_metadata": {
                                    "path": "caller.py",
                                    "line": 17,
                                    "source_sha256": "caller-hash",
                                    "observed_by": "python_ast_call_resolution",
                                    "resolution_kind": "name",
                                    "resolution_status": "statically_resolved",
                                }
                            },
                        }
                    ],
                }
            },
        ),
        SimpleNamespace(
            evidence_id="E0003",
            tool="read_source_file",
            arguments={"path": "target.py"},
            status="ok",
            response={"result": {
                "path": "target.py", "source_sha256": "target-hash",
                "source_range_complete": True, "requested_start_line": 1,
                "requested_end_line": 20, "start_line": 1, "end_line": 20,
                "total_lines": 20, "truncated": False, "end_clamped_to_eof": False,
            }},
        ),
        SimpleNamespace(
            evidence_id="E0004",
            tool="read_source_file",
            arguments={"path": "caller.py"},
            status="ok",
            response={"result": {
                "path": "caller.py", "source_sha256": "caller-hash",
                "source_range_complete": False, "requested_start_line": 1,
                "requested_end_line": 50, "start_line": 1, "end_line": 50,
                "total_lines": 100, "truncated": False, "end_clamped_to_eof": False,
            }},
        ),
    ]

    coverage = investigator._graph_interaction_coverage()

    assert coverage["status"] == "complete"
    assert coverage["graph_paths_already_read_before_query"] == ["target.py"]
    assert coverage["graph_derived_read_paths"] == ["caller.py"]
    assert coverage["graph_derived_verified_read_paths"] == ["caller.py"]
    assert coverage["graph_follow_through"] == [
        {
            "graph_query_evidence_id": "E0002",
            "graph_query_ledger_index": 1,
            "is_required_target_query": True,
            "read_evidence_id": "E0004",
            "read_ledger_index": 3,
            "path": "caller.py",
            "source_sha256": "caller-hash",
            "source_range_complete": False,
            "requested_range_complete": True,
            "requested_start_line": 1,
            "requested_end_line": 50,
            "returned_start_line": 1,
            "returned_end_line": 50,
            "truncated": False,
            "end_clamped_to_eof": False,
            "expected_graph_source_sha256": "caller-hash",
            "source_hash_matches_graph": True,
        }
    ]
    assert coverage["graph_observation_count"] == 1
    observation = coverage["graph_observations"][0]
    assert observation["predicate"] == "CALLS"
    assert observation["subject"]["name"] == "caller"
    assert observation["object"]["name"] == "target"
    assert observation["source_path"] == "caller.py"
    assert observation["source_line"] == 17
    assert observation["source_sha256"] == "caller-hash"
    assert observation["resolution_status"] == "statically_resolved"

    # A path is surfaced/read but does not count as verified follow-through if
    # the requested range is incomplete or the read hash differs from graph evidence.
    investigator._ledger[-1].response["result"]["truncated"] = True
    incomplete = investigator._graph_interaction_coverage()
    assert incomplete["status"] == "incomplete"
    assert incomplete["graph_derived_read_paths"] == ["caller.py"]
    assert incomplete["graph_derived_verified_read_paths"] == []

    investigator._ledger[-1].response["result"]["truncated"] = False
    investigator._ledger[-1].response["result"]["source_sha256"] = "different-hash"
    mismatched = investigator._graph_interaction_coverage()
    assert mismatched["status"] == "incomplete"
    assert mismatched["graph_derived_verified_read_paths"] == []



def test_followup_graph_queries_and_observations_are_preserved(tmp_path):
    investigator = _investigator(tmp_path, graph_enabled=True, require_graph=True)
    first_result = {
        "coverage_status": "complete_for_query",
        "truncated": False,
        "observed_relation_types": ["CALLS"],
        "source_paths": ["target.py"],
        "source_nodes": [{"node_id": "target", "name": "target", "path": "target.py", "source_sha256": "target-hash"}],
        "discovered_nodes": [],
        "observations": [{
            "observation_id": "obs-target", "subject_id": "caller", "predicate": "CALLS",
            "object_id": "target", "evidence_ids": ["edge-target"], "depth": 1,
        }],
        "evidence": [{
            "evidence_id": "edge-target",
            "provenance": {"edge_metadata": {
                "path": "target.py", "line": 4, "source_sha256": "target-hash",
                "observed_by": "python_ast_call_resolution",
                "resolution_kind": "name", "resolution_status": "statically_resolved",
            }},
        }],
    }
    second_result = {
        "coverage_status": "complete_for_query",
        "truncated": False,
        "observed_relation_types": ["CALLS"],
        "source_paths": ["caller.py", "deeper.py"],
        "source_nodes": [{"node_id": "caller", "name": "caller", "path": "caller.py", "source_sha256": "caller-hash"}],
        "discovered_nodes": [{"node_id": "deeper", "name": "deeper", "path": "deeper.py", "source_sha256": "deeper-hash"}],
        "observations": [{
            "observation_id": "obs-deeper", "subject_id": "caller", "predicate": "CALLS",
            "object_id": "deeper", "evidence_ids": ["edge-deeper"], "depth": 1,
        }],
        "evidence": [{
            "evidence_id": "edge-deeper",
            "provenance": {"edge_metadata": {
                "path": "caller.py", "line": 27, "source_sha256": "caller-hash",
                "observed_by": "python_ast_call_resolution",
                "resolution_kind": "name", "resolution_status": "statically_resolved",
            }},
        }],
    }
    complete_read = {
        "path": "deeper.py", "source_sha256": "deeper-hash",
        "requested_start_line": 1, "requested_end_line": 20,
        "start_line": 1, "end_line": 20, "total_lines": 20,
        "truncated": False, "end_clamped_to_eof": False,
    }
    investigator._ledger = [
        SimpleNamespace(evidence_id="E0001", tool="graph_neighbors",
                        arguments={"node": "symbol:target"}, status="ok",
                        response={"result": first_result}),
        SimpleNamespace(evidence_id="E0002", tool="graph_neighbors",
                        arguments={"node": "symbol:caller"}, status="ok",
                        response={"result": second_result}),
        SimpleNamespace(evidence_id="E0003", tool="read_source_file",
                        arguments={"path": "deeper.py"}, status="ok",
                        response={"result": complete_read}),
    ]

    coverage = investigator._graph_interaction_coverage()

    assert coverage["status"] == "complete"
    assert coverage["graph_tool_call_count"] == 2
    assert coverage["successful_graph_tool_call_count"] == 2
    assert coverage["required_target_successful_graph_query_count"] == 1
    assert coverage["graph_observation_count"] == 2
    assert {item["observation_id"] for item in coverage["graph_observations"]} == {
        "obs-target", "obs-deeper"
    }
    assert coverage["graph_derived_verified_read_paths"] == ["deeper.py"]
    assert coverage["graph_follow_through"][0]["is_required_target_query"] is False

def test_ae32c_core_profile_builds_bounded_real_repository_scope(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    profile = _load_profile("ae32c_core", repo_root / "evaluation/ae32c/graph_pilot_profiles.json")
    manifest = build_scoped_snapshot(repo_root, tmp_path / "scope", profile)

    assert manifest["file_count"] <= profile["max_files"] == 100
    assert manifest["total_bytes"] <= profile["max_bytes"] == 2_000_000
    paths = {item["path"] for item in manifest["files"]}
    assert "audit_engine/semantic_audit/ae32c/live_evaluation.py" in paths
    assert "providers/factory.py" in paths
    assert profile["graph_target"] == "symbol:audit_engine.semantic_audit.ae32c.live_evaluation::main"


def test_provider_model_cost_profiles_are_generic_and_extensible(monkeypatch):
    monkeypatch.setenv("TEST_INPUT_RATE", "1.0")
    profile = {
        "input_usd_per_million_tokens": {"env": "TEST_INPUT_RATE", "default": 0.5},
        "output_usd_per_million_tokens": {"env": "TEST_OUTPUT_RATE", "default": 2.0},
        "output_reservation_multiplier": 2,
        "uncertainty_margin": 0.1,
    }
    estimator = _build_cost_estimator("future-provider", "future-model-v1", profile)
    assert estimator is not None
    assert estimator("future-provider", "future-model-v1", 400, 100) > 0
    assert estimator.pricing_metadata["provider"] == "future-provider"
    assert estimator.pricing_metadata["model"] == "future-model-v1"
    assert _build_cost_estimator("future-provider", "unpriced-model", {}) is None

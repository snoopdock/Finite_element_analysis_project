from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from audit_engine.semantic_audit.ae32c.tool_policy import GRAPH_DERIVED_TOOL_NAMES
from audit_engine.semantic_audit.ae32c.graph_pilot import (
    _graph_tool_isolation,
    _graph_derived_tool_calls,
    _apply_model_runtime_limits,
    _build_cost_estimator,
    _load_profile,
    _inter_condition_cooldown_seconds,
    build_scoped_snapshot,
)
from audit_engine.semantic_audit.ae32c.investigator import (
    InvestigationLimits,
    RepositoryInvestigator,
)


class _Provider:
    model = "test-model"

    def get_stats(self):
        return {}


class _EvidenceTools:
    manifest_sha256 = "manifest"
    graph_fingerprint = "graph"
    manifest_rows = {}
    file_hashes = {}


def _investigator(
    tmp_path, *, graph_enabled=True, require_graph=False, min_cross_module_reads=0,
    graph_query_max_depth=None, graph_query_max_results=None,
):
    return RepositoryInvestigator(
        tmp_path,
        _Provider(),
        evidence_tools=_EvidenceTools(),
        enable_graph_tools=graph_enabled,
        require_graph_interaction=require_graph,
        required_graph_target="symbol:target" if require_graph else None,
        required_graph_min_cross_module_reads=min_cross_module_reads,
        graph_query_max_depth=graph_query_max_depth,
        graph_query_max_results=graph_query_max_results,
    )


def test_graph_tools_can_be_removed_for_matched_control(tmp_path):
    investigator = _investigator(tmp_path, graph_enabled=False)
    names = {item["function"]["name"] for item in investigator._tool_definitions}

    assert not (names & GRAPH_DERIVED_TOOL_NAMES)
    assert "graph_neighbors" not in names
    assert "graph_path" not in names
    assert "trace_execution_context" not in names
    assert "find_related_tests" not in names
    assert "find_workflow_context" not in names
    coverage = investigator._graph_interaction_coverage()
    assert coverage["status"] == "disabled"
    assert coverage["tools_available"] is False
    assert coverage["graph_queries"] == []
    assert coverage["graph_derived_verified_read_paths"] == []





def test_graph_derived_tool_usage_counts_all_five_tools_including_discovery_helpers(tmp_path):
    investigator = _investigator(tmp_path, graph_enabled=True, require_graph=False)
    investigator._ledger = [
        SimpleNamespace(evidence_id="E0001", tool="trace_execution_context", arguments={"node": "symbol:entry"}, status="ok"),
        SimpleNamespace(evidence_id="E0002", tool="find_related_tests", arguments={"path": "tests/test_entry.py"}, status="error"),
        SimpleNamespace(evidence_id="E0003", tool="find_workflow_context", arguments={"query": "entry"}, status="ok"),
    ]
    coverage = investigator._graph_interaction_coverage()
    usage = coverage["graph_derived_tool_usage"]
    assert set(usage) == set(GRAPH_DERIVED_TOOL_NAMES)
    assert usage["trace_execution_context"]["attempt_count"] == 1
    assert usage["trace_execution_context"]["successful_call_count"] == 1
    assert usage["find_related_tests"]["failed_call_count"] == 1
    assert usage["find_workflow_context"]["distinct_target_count"] == 1
    assert usage["graph_neighbors"]["attempt_count"] == 0


def test_graph_tool_ablation_changes_only_graph_tool_availability(tmp_path):
    control = _investigator(tmp_path, graph_enabled=False)
    treatment = _investigator(tmp_path, graph_enabled=True)
    control_names = {item["function"]["name"] for item in control._tool_definitions}
    treatment_names = {item["function"]["name"] for item in treatment._tool_definitions}
    graph_tools = set(GRAPH_DERIVED_TOOL_NAMES)

    assert not (control_names & graph_tools)
    assert (treatment_names & graph_tools) == graph_tools
    assert (control_names - graph_tools) == (treatment_names - graph_tools)


def test_graph_tool_isolation_helper_rejects_any_graph_derived_control_leak():
    non_graph = {"repository_summary", "search_repository", "search_symbols", "read_source_file"}
    expected = set(GRAPH_DERIVED_TOOL_NAMES)
    valid = _graph_tool_isolation(non_graph, non_graph | expected)
    assert valid["isolated"] is True
    assert valid["non_graph_tool_sets_match"] is True
    assert valid["control_graph_derived_tools"] == []
    assert set(valid["treatment_graph_derived_tools"]) == expected

    leaked = _graph_tool_isolation(non_graph | {"trace_execution_context"}, non_graph | expected)
    assert leaked["isolated"] is False
    assert leaked["unexpected_control_graph_derived_tools"] == ["trace_execution_context"]

def test_graph_derived_tool_call_ledger_detects_relationship_tool_leaks():
    assert _graph_derived_tool_calls([
        {"tool": "read_source_file"},
        {"tool": "trace_execution_context"},
        {"tool": "graph_neighbors"},
        {"tool": "trace_execution_context"},
    ]) == ["graph_neighbors", "trace_execution_context"]
    assert _graph_derived_tool_calls([{"tool": "search_repository"}]) == []


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
    assert coverage["cross_module_graph_source_paths"] == ["caller.py"]
    assert coverage["cross_module_graph_derived_verified_read_paths"] == ["caller.py"]
    assert coverage["minimum_cross_module_reads_met"] is True
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

    assert manifest["file_count"] <= profile["max_files"] == 110
    assert manifest["total_bytes"] <= profile["max_bytes"] == 2_000_000
    paths = {item["path"] for item in manifest["files"]}
    assert "audit_engine/semantic_audit/ae32c/live_evaluation.py" in paths
    assert "providers/factory.py" in paths
    assert profile["graph_target"] == "symbol:audit_engine.semantic_audit.ae32c.live_evaluation::main"
    assert profile["graph_min_cross_module_reads"] == 3
    assert profile["graph_query_depth"] == 2


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



def test_graph_pilot_pins_model_graph_queries_to_preflight_bounds(tmp_path):
    investigator = _investigator(
        tmp_path,
        graph_enabled=True,
        require_graph=True,
        min_cross_module_reads=3,
        graph_query_max_depth=2,
        graph_query_max_results=30,
    )
    neighbors = investigator._tool_schemas["graph_neighbors"]["parameters"]
    properties = neighbors["properties"]
    assert set(("node", "direction", "relation_types", "max_depth", "max_results")).issubset(
        set(neighbors["required"])
    )
    assert properties["direction"]["enum"] == ["outgoing"]
    assert properties["relation_types"]["items"]["enum"] == ["CALLS"]
    assert properties["max_depth"]["enum"] == [2]
    assert properties["max_results"]["enum"] == [30]

    graph_path = investigator._tool_schemas["graph_path"]["parameters"]
    path_properties = graph_path["properties"]
    assert path_properties["direction"]["enum"] == ["outgoing"]
    assert path_properties["relation_types"]["items"]["enum"] == ["CALLS"]
    assert path_properties["max_depth"]["enum"] == [2]

    try:
        investigator._validate_tool_action({
            "action": "tool_call",
            "tool": "graph_neighbors",
            "arguments": {
                "node": "symbol:target", "direction": "outgoing", "relation_types": ["CALLS"],
                "max_depth": 4, "max_results": 50,
            },
            "reason": "Attempt an unbounded graph query.",
        })
    except Exception as exc:
        assert "tool_arguments_schema_invalid" in str(exc)
    else:
        raise AssertionError("over-wide graph query was accepted")


def test_graph_required_contract_states_exact_query_and_class_root_rule(tmp_path):
    investigator = _investigator(
        tmp_path, graph_enabled=True, require_graph=True, min_cross_module_reads=3,
        graph_query_max_depth=2, graph_query_max_results=30,
    )
    summary = SimpleNamespace(
        evidence_id="E0001", tool="repository_summary", status="ok",
        response_sha256="summary-hash", provenance={},
        response={"result": {"audit_status": "complete"}}, summary="audit_status=complete",
    )
    messages = investigator._initial_messages("Trace the live evaluation call chain.", summary)
    payload = json.loads(messages[1]["content"])
    contract = payload["graph_investigation_contract"]
    assert contract["graph_query_limits"] == {
        "direction": "outgoing", "max_depth": 2, "max_results": 30, "relation_types": ["CALLS"]
    }
    assert "max_depth=2" in contract["instructions"]
    assert "max_results=30" in contract["instructions"]
    assert "do not query class symbols" in contract["instructions"]


def test_graph_neighbors_model_view_prioritizes_cross_module_edges(tmp_path):
    investigator = _investigator(tmp_path, graph_enabled=True)
    source_nodes = [{
        "node_id": "root",
        "name": "main",
        "qualified_name": "main",
        "module": "audit_engine.semantic_audit.ae32c.live_evaluation",
        "path": "audit_engine/semantic_audit/ae32c/live_evaluation.py",
        "line": 322,
        "kind": "function",
        "source_sha256": "root-hash",
    }]
    discovered_nodes = []
    observations = []
    evidence = []
    root_path = source_nodes[0]["path"]

    # Deliberately put same-module edges first: the model view must still
    # prioritize cross-module endpoints instead of truncating to list order.
    for index in range(14):
        node_id = f"local-{index}"
        path = root_path
        discovered_nodes.append({
            "node_id": node_id, "name": f"helper_{index}",
            "qualified_name": f"helper_{index}",
            "module": "audit_engine.semantic_audit.ae32c.live_evaluation",
            "path": path, "line": 20 + index, "kind": "function",
            "source_sha256": "root-hash",
        })
        edge_id = f"edge-local-{index}"
        observations.append({
            "observation_id": f"obs-local-{index}",
            "subject_id": "root", "predicate": "CALLS",
            "object_id": node_id, "evidence_ids": [edge_id], "depth": 1,
        })
        evidence.append({
            "evidence_id": edge_id,
            "provenance": {"edge_metadata": {
                "path": root_path, "line": 400 + index,
                "source_sha256": "root-hash",
                "observed_by": "python_ast_call_resolution",
                "resolution_kind": "name",
                "resolution_status": "statically_resolved",
            }},
        })

    external_paths = [
        "providers/factory.py",
        "audit_engine/semantic_audit/ae32b/evidence_tools.py",
        "audit_engine/semantic_audit/ae32c/investigator.py",
    ]
    for index, path in enumerate(external_paths):
        node_id = f"external-{index}"
        module = path.removesuffix(".py").replace("/", ".")
        discovered_nodes.append({
            "node_id": node_id, "name": f"cross_module_{index}",
            "qualified_name": f"{module}.cross_module_{index}",
            "module": module, "path": path, "line": 50 + index,
            "kind": "function", "source_sha256": f"hash-{index}",
        })
        edge_id = f"edge-external-{index}"
        observations.append({
            "observation_id": f"obs-external-{index}",
            "subject_id": "root", "predicate": "CALLS",
            "object_id": node_id, "evidence_ids": [edge_id], "depth": 1,
        })
        evidence.append({
            "evidence_id": edge_id,
            "provenance": {"edge_metadata": {
                "path": root_path, "line": 500 + index,
                "source_sha256": "root-hash",
                "observed_by": "python_ast_call_resolution",
                "resolution_kind": "name",
                "resolution_status": "statically_resolved",
            }},
        })

    entry = SimpleNamespace(
        evidence_id="E0002",
        tool="graph_neighbors",
        status="ok",
        response_sha256="response-hash",
        provenance={"graph_fingerprint": "graph"},
        arguments={"direction": "outgoing", "node": "symbol:target"},
        response={
            "schema_version": "evidence-tool/v1",
            "tool": "graph_neighbors",
            "status": "ok",
            "result": {
                "status": "completed",
                "coverage_status": "complete_for_query",
                "truncated": False,
                "observed_relation_types": ["CALLS"],
                "source_paths": [root_path, *external_paths],
                "source_nodes": source_nodes,
                "discovered_nodes": discovered_nodes,
                "observations": observations,
                "evidence": evidence,
            },
        },
    )

    view = investigator._model_view(entry)
    result = view["response"]["result"]

    assert result["observation_count"] == 17
    assert 3 <= result["observations_included"] <= 8
    assert set(result["cross_module_source_paths"]) == set(external_paths)
    assert {item["path"] for item in result["priority_source_targets"]} == set(external_paths)
    assert {
        item["cross_module_path"] for item in result["observations"][:3]
    } == set(external_paths)
    assert len(view["response"]["result"]["observations"]) <= 8
    assert len(json.dumps(view)) <= investigator.limits.max_tool_context_chars


def test_graph_interaction_enforces_minimum_distinct_cross_module_reads(tmp_path):
    investigator = _investigator(
        tmp_path, graph_enabled=True, require_graph=True, min_cross_module_reads=2
    )
    root_path = "entry.py"
    external = {
        "a.py": "hash-a",
        "b.py": "hash-b",
        "c.py": "hash-c",
    }
    nodes = [
        {"node_id": "root", "name": "entry", "path": root_path, "source_sha256": "hash-root"}
    ]
    nodes.extend(
        {"node_id": f"node-{path}", "name": path[:-3], "path": path, "source_sha256": digest}
        for path, digest in external.items()
    )
    observations = []
    evidence = []
    for index, (path, digest) in enumerate(external.items()):
        edge_id = f"edge-{index}"
        observations.append({
            "observation_id": f"obs-{index}",
            "subject_id": "root",
            "predicate": "CALLS",
            "object_id": f"node-{path}",
            "evidence_ids": [edge_id],
            "depth": 1,
        })
        evidence.append({
            "evidence_id": edge_id,
            "provenance": {"edge_metadata": {
                "path": root_path, "line": 10 + index,
                "source_sha256": "hash-root",
                "observed_by": "python_ast_call_resolution",
                "resolution_kind": "name",
                "resolution_status": "statically_resolved",
            }},
        })
    graph_result = {
        "coverage_status": "complete_for_query",
        "truncated": False,
        "observed_relation_types": ["CALLS"],
        "source_paths": [root_path, *external.keys()],
        "source_nodes": [nodes[0]],
        "discovered_nodes": nodes[1:],
        "observations": observations,
        "evidence": evidence,
    }
    investigator._ledger = [
        SimpleNamespace(
            evidence_id="E0001", tool="graph_neighbors",
            arguments={"node": "symbol:target"}, status="ok",
            response={"result": graph_result},
        ),
    ]

    def add_read(evidence_id, path, digest):
        investigator._ledger.append(SimpleNamespace(
            evidence_id=evidence_id,
            tool="read_source_file",
            arguments={"path": path},
            status="ok",
            response={"result": {
                "path": path, "source_sha256": digest,
                "requested_start_line": 1, "requested_end_line": 50,
                "start_line": 1, "end_line": 50, "total_lines": 100,
                "source_range_complete": False, "truncated": False,
                "end_clamped_to_eof": False,
            }},
        ))

    add_read("E0002", "a.py", "hash-a")
    one_read = investigator._graph_interaction_coverage()
    assert one_read["status"] == "incomplete"
    assert one_read["cross_module_graph_derived_verified_read_paths"] == ["a.py"]
    assert one_read["minimum_cross_module_reads_met"] is False
    assert one_read["graph_follow_through_complete"] is False

    add_read("E0003", "b.py", "hash-b")
    two_reads = investigator._graph_interaction_coverage()
    assert two_reads["status"] == "complete"
    assert two_reads["cross_module_graph_derived_verified_read_paths"] == ["a.py", "b.py"]
    assert two_reads["minimum_cross_module_reads_met"] is True
    assert two_reads["graph_follow_through_complete"] is True


def test_model_runtime_limits_are_provider_model_profile_driven():
    base = InvestigationLimits()
    tuned = _apply_model_runtime_limits(base, {
        "max_rounds": 13,
        "max_tool_calls": 16,
        "max_tokens_per_call": 2048,
        "finalization_max_tokens_per_call": 12000,
        "max_total_tokens": 200000,
        "max_total_prompt_chars": 500000,
        "max_elapsed_seconds": 600,
        "finalization_rounds_reserved": 3,
        "max_finalization_invalid_json_retries": 2,
        "max_provider_transport_retries": 1,
    })

    assert tuned.max_rounds == 13
    assert tuned.max_tool_calls == 16
    assert tuned.max_tokens_per_call == 2048
    assert tuned.finalization_max_tokens_per_call == 12000
    assert tuned.max_total_tokens == 200000
    assert tuned.max_total_prompt_chars == 500000
    assert tuned.max_elapsed_seconds == 600
    assert tuned.finalization_rounds_reserved == 3
    assert tuned.max_provider_transport_retries == 1

    try:
        _apply_model_runtime_limits(base, {"not_a_limit": 100})
    except Exception as exc:
        assert "unsupported_model_runtime_limit" in str(exc)
    else:
        raise AssertionError("unknown model runtime limit was accepted")


def test_nemotron_and_qwen_profiles_keep_separate_runtime_budgets():
    repo_root = Path(__file__).resolve().parents[2]
    config = json.loads((repo_root / "evaluation/ae32c/provider_model_profiles.json").read_text())
    nemotron = config["providers"]["openrouter"]["models"]["nvidia/nemotron-3-ultra-550b-a55b:free"]
    qwen = config["providers"]["cloudflare"]["models"]["@cf/qwen/qwen3.8-27b"]

    assert nemotron["runtime_limits"]["finalization_max_tokens_per_call"] == 12000
    assert nemotron["runtime_limits"]["max_rounds"] == 13
    assert nemotron["runtime_limits"]["max_total_tokens"] == 200000
    assert nemotron["runtime_limits"]["max_total_prompt_chars"] == 500000
    assert nemotron["runtime_limits"]["max_provider_transport_retries"] == 1
    assert _inter_condition_cooldown_seconds(nemotron) == 60
    assert nemotron["pricing"]["input_usd_per_million_tokens"]["default"] == 0.0
    assert qwen["runtime_limits"]["finalization_max_tokens_per_call"] == 6144
    assert qwen["runtime_limits"]["max_rounds"] == 11


def test_core_profile_documents_control_trace_module_target_and_nonoverlapping_reads():
    profile = _load_profile("ae32c_core")
    problem = profile["problem_statement"]
    assert "audit_engine/semantic_audit/ae32c/live_evaluation.py" in problem
    assert "function-symbol identifiers" in problem
    assert "non-overlapping line range" in problem


def test_graph_required_finalization_context_includes_graph_coverage(tmp_path):
    investigator = _investigator(tmp_path, graph_enabled=True, require_graph=True)
    messages = investigator._finalization_context_messages(
        problem="Inspect the live evaluation call chain.",
        summary=None,
        round_number=1,
        notice={"finalization_mode": {"required_action": "final"}},
        string_limit=120,
        list_limit=3,
        candidate_limit=20,
        include_responses=True,
        feedback=None,
    )

    payload = json.loads(messages[1]["content"])
    assert payload["graph_interaction_coverage"]["enabled"] is True
    assert payload["graph_investigation_contract"]["enabled"] is True
    assert payload["graph_investigation_contract"]["required_graph_target"] == "symbol:target"

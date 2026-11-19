from audit_engine.semantic_audit.ae32c.runtime_architecture import build_runtime_architecture_report


def test_runtime_report_distinguishes_available_graph_libraries_from_active_backend():
    report = build_runtime_architecture_report(
        audit_report={"audit": {"status": "complete", "manifest_sha256": "a" * 64,
                               "included_file_count": 10, "python_file_count": 8}},
        repository_summary={
            "graph_node_count": 12,
            "graph_edge_count": 20,
            "graph_fingerprint": "graph:test",
            "graph_projection_version": "projection/v1",
            "graph_relation_counts": {"CALLS": 7},
            "call_graph": {"candidate_call_sites": 9, "resolved_call_edges": 7,
                           "unresolved_call_sites": 2, "ambiguous_call_sites": 0},
            "static_finding_count": 1,
        },
        provider_name="fake-provider",
        model_name="fake-model",
        provider_stats={"usage": {"total_tokens": 42}},
        available_tool_names=["repository_summary", "graph_neighbors", "read_source_file"],
    )
    graph = report["graph_engine"]
    assert graph["canonical_semantic_model"] == "SemanticGraph"
    assert graph["active_computation_backend"] == "python_reference_traversal"
    assert graph["active_algorithm"] == "deterministic_breadth_first_search"
    assert graph["backend_pipeline_wired_into_ae32b_query_path"] is False
    assert all(item["active_in_ae32b_query_path"] is False for item in graph["external_backend_adapters"].values())
    assert report["llm_driver"]["total_tokens"] == 42
    assert report["llm_driver"]["credential_value_in_report"] is False
    assert report["deterministic_action_boundary"]["model_can_modify_repository_files"] is False
    assert report["deterministic_action_boundary"]["registered_verification_orchestration_invoked_by_ae32c"] is False

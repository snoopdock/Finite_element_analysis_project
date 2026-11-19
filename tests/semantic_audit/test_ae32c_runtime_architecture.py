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
        graph_runtime={
            "active_computation_backend": "networkx",
            "active_traversal_algorithm": "deterministic_breadth_first_search",
            "backend_library": "networkx",
            "backend_library_version": "3.6.1",
            "backend_projection_type": "MultiDiGraph",
            "backend_parity_mode": "strict_per_query_reference_comparison",
            "backend_pipeline_wired_into_ae32b_query_path": True,
            "external_backend_adapters_active": ["networkx"],
            "backend_execution": {"queries_attempted": 3, "queries_succeeded": 3,
                                  "queries_failed": 0, "parity_verified_queries": 3,
                                  "parity_failures": 0},
        },
    )
    graph = report["graph_engine"]
    assert graph["canonical_semantic_model"] == "SemanticGraph"
    assert graph["active_computation_backend"] == "networkx"
    assert graph["active_algorithm"] == "deterministic_breadth_first_search"
    assert graph["backend_library"] == "networkx"
    assert graph["backend_projection_type"] == "MultiDiGraph"
    assert graph["backend_pipeline_wired_into_ae32b_query_path"] is True
    assert graph["backend_execution"]["parity_verified_queries"] == 3
    assert graph["external_backend_adapters"]["networkx"]["active_in_ae32b_query_path"] is True
    assert all(not graph["external_backend_adapters"][name]["active_in_ae32b_query_path"]
               for name in ("scipy", "igraph", "graph-tool", "snap"))
    assert report["schema_version"] == "ae32c/runtime-architecture/v2"
    assert report["llm_driver"]["total_tokens"] == 42
    assert report["llm_driver"]["credential_value_in_report"] is False
    assert report["deterministic_action_boundary"]["model_can_modify_repository_files"] is False
    assert report["deterministic_action_boundary"]["registered_verification_orchestration_invoked_by_ae32c"] is False

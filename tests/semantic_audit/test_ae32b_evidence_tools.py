from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32b import EvidenceToolError, RepositoryEvidenceTools, build_tool_definitions


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repo(root: Path) -> Path:
    _write(root, "src/pkg/__init__.py", "")
    _write(root, "src/pkg/a.py", "from src.pkg.b import B\n\ndef target_function():\n    return B()\n")
    _write(root, "src/pkg/b.py", "class B:\n    pass\n")
    _write(root, "src/pkg/__main__.py", "from src.pkg.a import target_function\n\nif __name__ == '__main__':\n    target_function()\n")
    _write(root, "tests/test_a.py", "from src.pkg.a import target_function\n\ndef test_target_function():\n    assert target_function()\n")
    _write(root, ".github/workflows/check.yml", "name: check\non:\n  workflow_dispatch:\njobs:\n  test:\n    steps:\n      - run: python -m src.pkg.a\n")
    _write(root, ".github/workflows/package.yml", "name: package\non:\n  workflow_dispatch:\njobs:\n  test:\n    steps:\n      - run: python -m src.pkg\n")
    _write(root, "docs/audit-engine/incident-notes.md", "Prior incident: provider counter contract mismatch.\n")
    _write(root, "decision_memory/decisions/DEC-001.yaml", "id: DEC-001\ndecision:\n  title: provider interface decision\n  statement: preserve provider contract evidence\n")
    _write(root, "decision_memory/actions/ACTION-001.yaml", "id: ACTION-001\ntriggered_by:\n  decision: DEC-001\ndecision_refs:\n  - DEC-001\naction:\n  description: add a regression test\n")
    _write(root, "decision_memory/outcomes/OUTCOME-001.yaml", "id: OUTCOME-001\naction_id:\n  - ACTION-001\nresult:\n  status: successful\n  summary: regression passed\n")
    _write(root, "config.yaml", 'api_token: "test-secret-value-12345"\nmode: test\n')
    _write(root, "settings.json", '{"OPENROUTER_TOKEN": "test-json-secret-value-12345", "mode": "test"}\n')
    _write(root, "src/pkg/empty.txt", "")
    return root


def _server(tmp_path: Path) -> RepositoryEvidenceTools:
    return RepositoryEvidenceTools(_repo(tmp_path))


def test_catalog_is_openai_compatible_and_contains_bounded_read_only_tools():
    tools = build_tool_definitions()
    names = [item["function"]["name"] for item in tools]
    assert names == [
        "repository_summary", "search_repository", "read_source_file", "search_symbols",
        "graph_neighbors", "graph_path", "find_related_tests", "trace_execution_context",
        "discover_case_context", "find_workflow_context",
        "search_decision_history",
    ]
    for item in tools:
        assert item["type"] == "function"
        assert item["function"]["parameters"]["additionalProperties"] is False


def test_summary_reports_graph_and_provenance_without_claiming_runtime_execution(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("repository_summary", {})
    assert response["status"] == "ok"
    result = response["result"]
    assert result["indexed_file_count"] >= 7
    assert result["graph_node_count"] > result["indexed_file_count"]
    assert result["graph_edge_count"] > 0
    assert result["graph_runtime"]["canonical_model"] == "SemanticGraph"
    assert result["graph_runtime"]["active_traversal_algorithm"] == "deterministic_breadth_first_search"
    assert result["graph_runtime"]["external_backend_adapters_active"] == []
    assert result["repository_code_executed"] is False
    assert result["network_calls_performed"] is False
    assert response["provenance"]["source_manifest_sha256"]
    assert response["provenance"]["graph_fingerprint"]


def test_graph_neighbors_uses_existing_semantic_graph_analysis_service(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("graph_neighbors", {
        "node": "module:src.pkg.a", "direction": "outgoing", "relation_types": ["IMPORTS"],
        "max_depth": 1,
    })
    assert response["status"] == "ok"
    result = response["result"]
    assert "module:src.pkg.b" in result["discovered_entities"]
    assert result["evidence"]
    assert any(item["predicate"] == "IMPORTS" for item in result["observations"])
    assert result["graph_fingerprint"] == response["provenance"]["graph_fingerprint"]


def test_graph_path_returns_observed_path_not_semantic_validity_claim(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("graph_path", {
        "source": "src/pkg/a.py", "target": "src/pkg/b.py", "direction": "both",
        "max_depth": 5,
    })
    assert response["status"] == "ok"
    result = response["result"]
    assert result["path_found"] is True
    assert result["path"]
    assert all("relation" in item and "from" in item and "to" in item for item in result["path"])


def test_search_symbols_returns_exact_file_and_line(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("search_symbols", {"query": "target_function", "kind": "function"})
    assert response["status"] == "ok"
    symbols = response["result"]["symbols"]
    assert symbols[0]["path"] == "src/pkg/a.py"
    assert symbols[0]["line"] == 3
    assert symbols[0]["source_sha256"]


def test_related_tests_finds_importing_test_with_static_evidence(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("find_related_tests", {"target": "module:src.pkg.a"})
    assert response["status"] == "ok"
    tests = response["result"]["tests"]
    assert any(item["path"] == "tests/test_a.py" and item["relationship"] == "static_import" for item in tests)
    candidate = next(item for item in tests if item["path"] == "tests/test_a.py")
    assert candidate["pytest_static_assessment"]["classification"] == "pytest_collection_candidate"
    assert candidate["pytest_static_assessment"]["execution_status"] == "not_executed_static_analysis_only"
    assert response["result"]["coverage_status"] == "complete_for_query"


def test_trace_execution_context_reports_static_callers_dependencies_and_entrypoints(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("trace_execution_context", {
        "target": "module:src.pkg.a", "max_depth": 3, "max_results": 20,
    })
    assert response["status"] == "ok"
    result = response["result"]
    assert result["coverage_status"] == "complete_for_query"
    assert result["truncated"] is False
    assert "src/pkg/__main__.py" in result["static_caller_paths"]
    assert "tests/test_a.py" in result["static_caller_paths"]
    assert "src/pkg/b.py" in result["static_dependency_paths"]
    assert "src/pkg/__main__.py" in result["python_entrypoint_paths"]
    assert any(item["path"] == ".github/workflows/check.yml" for item in result["active_workflow_paths"])
    assert result["limitations"] and "do not prove runtime execution" in result["limitations"][0]


def test_discover_case_context_returns_hash_bound_line_numbered_preview(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("discover_case_context", {"max_results": 10})
    assert response["status"] == "ok"
    result = response["result"]
    candidate = next(item for item in result["metadata_candidates"] if item["path"] == "docs/audit-engine/incident-notes.md")
    assert candidate["content_complete"] is True
    assert candidate["content_omitted"] is False
    assert candidate["preview_line_numbered"] is True
    assert candidate["source_sha256"] == server.file_hashes[candidate["path"]]
    assert candidate["line_numbered_preview"][0].startswith("1: ")
    assert result["coverage_status"] == "complete_for_query"


def test_context_discovery_reports_result_limit_truncation(tmp_path):
    root = _repo(tmp_path)
    _write(root, "incidents/incident.json", '{"case_id": "SECOND"}\n')
    server = RepositoryEvidenceTools(root)
    response = server.invoke("discover_case_context", {"max_results": 1})
    assert response["status"] == "ok"
    assert response["result"]["candidate_count"] >= 2
    assert response["result"]["returned_count"] == 1
    assert response["result"]["truncated"] is True
    assert response["result"]["coverage_status"] == "partial"


def test_execution_context_reports_truncation_when_workflow_results_are_limited(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("trace_execution_context", {
        "target": "module:src.pkg.a", "max_depth": 3, "max_results": 1,
    })
    assert response["status"] == "ok"
    assert response["result"]["truncated"] is True
    assert response["result"]["coverage_status"] == "partial"


def test_pytest_static_assessment_respects_visible_custom_python_files_pattern(tmp_path):
    root = _repo(tmp_path)
    _write(root, "pyproject.toml", "[tool.pytest.ini_options]\npython_files = [\"spec_*.py\"]\n")
    _write(root, "tests/spec_a.py", "from src.pkg.a import target_function\n")
    server = RepositoryEvidenceTools(root)
    response = server.invoke("find_related_tests", {"target": "module:src.pkg.a"})
    assert response["status"] == "ok"
    assessments = {item["path"]: item["pytest_static_assessment"] for item in response["result"]["tests"]}
    assert assessments["tests/spec_a.py"]["classification"] == "pytest_collection_candidate"
    assert assessments["tests/spec_a.py"]["matched_python_files_pattern"] == "spec_*.py"
    assert assessments["tests/test_a.py"]["classification"] == "helper_only_not_default_collected"


def test_malformed_pytest_configuration_produces_unknown_classification(tmp_path):
    root = _repo(tmp_path)
    _write(root, "pyproject.toml", "[tool.pytest.ini_options\npython_files = [\"spec_*.py\"]\n")
    server = RepositoryEvidenceTools(root)
    response = server.invoke("find_related_tests", {"target": "module:src.pkg.a"})
    assert response["status"] == "ok"
    candidate = next(item for item in response["result"]["tests"] if item["path"] == "tests/test_a.py")
    assert candidate["pytest_static_assessment"]["classification"] == "unknown"
    assert candidate["pytest_static_assessment"]["collection_status"] == "unknown"


def test_workflow_context_finds_static_invocation(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("find_workflow_context", {"target": "module:src.pkg.a"})
    assert response["status"] == "ok"
    assert any(item["path"] == ".github/workflows/check.yml" for item in response["result"]["workflows"])



def test_workflow_context_resolves_module_and_file_targets(tmp_path):
    server = _server(tmp_path)
    module_response = server.invoke("find_workflow_context", {"target": "module:src.pkg.a"})
    file_response = server.invoke("find_workflow_context", {"target": "src/pkg/a.py"})
    assert module_response["status"] == "ok"
    assert file_response["status"] == "ok"
    assert any(item["path"] == ".github/workflows/check.yml" for item in module_response["result"]["workflows"])
    assert any(item["path"] == ".github/workflows/check.yml" for item in file_response["result"]["workflows"])
    assert any(item["path"] == ".github/workflows/package.yml" and item["relationship"] == "transitive_static_path"
               for item in file_response["result"]["workflows"])
    assert file_response["result"]["workflows"][0]["graph_evidence"]


def test_decision_history_search_is_scoped_and_returns_line_evidence(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("search_decision_history", {"query": "provider interface decision"})
    assert response["status"] == "ok"
    paths = {item["path"] for item in response["result"]["matches"]}
    assert "decision_memory/decisions/DEC-001.yaml" in paths
    assert "src/pkg/a.py" not in paths



def test_decision_memory_records_and_cross_references_are_in_the_graph(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("graph_neighbors", {
        "node": "decision_record:decision:DEC-001", "direction": "both",
        "relation_types": ["CONTAINS_RECORD", "REFERENCES_DECISION"], "max_depth": 1,
    })
    assert response["status"] == "ok"
    nodes = response["result"]["discovered_nodes"]
    assert any(item.get("record_id") == "ACTION-001" for item in nodes)
    assert any(item.get("path") == "decision_memory/decisions/DEC-001.yaml" for item in nodes)


def test_read_source_file_is_bounded_and_redacts_secret_like_literals(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("read_source_file", {"path": "config.yaml"})
    assert response["status"] == "ok"
    content = response["result"]["content"]
    assert "test-secret-value-12345" not in content
    assert "<redacted>" in content
    assert response["result"]["source_sha256"]
    assert response["result"]["redaction_applied"] is True
    json_response = server.invoke("read_source_file", {"path": "settings.json"})
    assert json_response["status"] == "ok"
    assert "test-json-secret-value-12345" not in json_response["result"]["content"]


def test_empty_file_can_be_read_without_index_error(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("read_source_file", {"path": "src/pkg/empty.txt"})
    assert response["status"] == "ok"
    assert response["result"]["total_lines"] == 0
    assert response["result"]["content"] == ""


def test_path_traversal_and_sensitive_paths_fail_closed(tmp_path):
    server = _server(tmp_path)
    traversal = server.invoke("read_source_file", {"path": "../outside.py"})
    sensitive = server.invoke("read_source_file", {"path": ".env"})
    assert traversal["status"] == "error"
    assert traversal["error"]["code"] == "invalid_path"
    assert sensitive["status"] == "error"
    assert sensitive["error"]["code"] == "sensitive_path_blocked"


def test_unknown_tools_and_unknown_arguments_are_rejected(tmp_path):
    server = _server(tmp_path)
    unknown = server.invoke("run_shell", {"command": "echo unsafe"})
    extra = server.invoke("repository_summary", {"path": "src/pkg/a.py"})
    assert unknown["status"] == "error" and unknown["error"]["code"] == "unknown_tool"
    assert extra["status"] == "error" and extra["error"]["code"] == "unknown_argument"


def test_query_bounds_are_enforced(tmp_path):
    server = _server(tmp_path)
    too_deep = server.invoke("graph_neighbors", {"node": "module:src.pkg.a", "max_depth": 99})
    too_many = server.invoke("search_repository", {"query": "a", "max_results": 999})
    assert too_deep["status"] == "error" and too_deep["error"]["code"] == "argument_out_of_range"
    assert too_many["status"] == "error" and too_many["error"]["code"] == "argument_out_of_range"


def test_repository_code_is_not_executed_and_source_is_not_modified(tmp_path):
    root = _repo(tmp_path)
    marker = root / "executed.txt"
    _write(root, "src/pkg/side_effect.py", f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\nraise RuntimeError('must not run')\n")
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    server = RepositoryEvidenceTools(root)
    assert server.invoke("repository_summary", {})["status"] == "ok"
    after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert not marker.exists()
    assert before == after


def test_graph_and_manifest_are_deterministic_for_same_snapshot(tmp_path):
    root = _repo(tmp_path)
    first = RepositoryEvidenceTools(root)
    second = RepositoryEvidenceTools(root)
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.graph_fingerprint == second.graph_fingerprint
    assert first.graph.to_dict() == second.graph.to_dict()



def test_source_change_between_manifest_scan_and_index_fails_closed(monkeypatch, tmp_path):
    import audit_engine.semantic_audit.ae32b.evidence_tools as module

    root = _repo(tmp_path)
    original = module.audit_repository

    def scan_then_change(*args, **kwargs):
        report = original(*args, **kwargs)
        (root / "src/pkg/a.py").write_text("def changed_after_scan():\n    return True\n", encoding="utf-8")
        return report

    monkeypatch.setattr(module, "audit_repository", scan_then_change)
    with pytest.raises(EvidenceToolError, match="Indexed source changed"):
        RepositoryEvidenceTools(root)


def test_cli_module_source_parses():
    from audit_engine.semantic_audit.ae32b import evidence_tools
    import audit_engine.semantic_audit.ae32b.__main__ as cli
    ast.parse(Path(evidence_tools.__file__).read_text(encoding="utf-8"))
    assert callable(cli.main)


def test_read_source_file_clamps_end_line_to_eof_and_reports_requested_range(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("read_source_file", {
        "path": "src/pkg/b.py", "start_line": 1, "end_line": 999,
    })
    assert response["status"] == "ok"
    result = response["result"]
    assert result["total_lines"] == 2
    assert result["requested_start_line"] == 1
    assert result["requested_end_line"] == 999
    assert result["start_line"] == 1
    assert result["end_line"] == 2
    assert result["truncated"] is True
    assert "1: class B:" in result["content"]
    assert "2:     pass" in result["content"]


def test_read_source_file_rejects_start_after_eof_and_end_before_start(tmp_path):
    server = _server(tmp_path)
    invalid_start = server.invoke("read_source_file", {
        "path": "src/pkg/b.py", "start_line": 3, "end_line": 999,
    })
    invalid_order = server.invoke("read_source_file", {
        "path": "src/pkg/b.py", "start_line": 2, "end_line": 1,
    })
    assert invalid_start["status"] == "error"
    assert invalid_start["error"]["code"] == "argument_out_of_range"
    assert invalid_order["status"] == "error"
    assert invalid_order["error"]["code"] == "argument_out_of_range"


def test_empty_source_end_range_clamps_to_zero_lines(tmp_path):
    server = _server(tmp_path)
    response = server.invoke("read_source_file", {
        "path": "src/pkg/empty.txt", "start_line": 1, "end_line": 50,
    })
    assert response["status"] == "ok"
    assert response["result"]["total_lines"] == 0
    assert response["result"]["requested_end_line"] == 50
    assert response["result"]["end_line"] == 0
    assert response["result"]["content"] == ""
    assert response["result"]["truncated"] is True


def test_conservative_call_graph_resolves_local_imported_and_self_method_calls(tmp_path: Path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/provider.py",
        "class Provider:\n"
        "    def chat(self):\n"
        "        return self.finish()\n"
        "    def finish(self):\n"
        "        return 'ok'\n",
    )
    _write(
        tmp_path,
        "pkg/service.py",
        "from pkg.provider import Provider\n"
        "def build():\n"
        "    return Provider()\n"
        "def run():\n"
        "    return build()\n",
    )
    server = RepositoryEvidenceTools(tmp_path)
    call_edges = [edge for edge in server.graph.edges if edge.relation_type == "CALLS"]
    assert call_edges
    pairs = {
        (edge.source_id, edge.target_id)
        for edge in call_edges
    }
    symbols = {
        (item["module"], item["qualified_name"]): item["node_id"]
        for item in server.symbols
    }
    assert (symbols[("pkg.service", "run")], symbols[("pkg.service", "build")]) in pairs
    assert (symbols[("pkg.service", "build")], symbols[("pkg.provider", "Provider")]) in pairs
    assert (symbols[("pkg.provider", "Provider.chat")], symbols[("pkg.provider", "Provider.finish")]) in pairs


def test_call_graph_does_not_promote_dynamic_attribute_calls(tmp_path: Path):
    _write(
        tmp_path,
        "pkg.py",
        "def run(obj):\n"
        "    return obj.method()\n"
        "def helper():\n"
        "    return 1\n",
    )
    server = RepositoryEvidenceTools(tmp_path)
    calls = [
        edge for edge in server.graph.edges
        if edge.relation_type == "CALLS"
    ]
    assert not calls
    assert server.call_graph_stats["runtime_execution"] is False
    assert server.call_graph_stats["unresolved_call_sites"] >= 1


def test_graph_neighbors_exposes_call_edges_with_source_paths(tmp_path: Path):
    _write(tmp_path, "pkg.py", "def helper():\n    return 1\n\ndef run():\n    return helper()\n")
    server = RepositoryEvidenceTools(tmp_path)
    run_symbol = next(item for item in server.symbols if item["qualified_name"] == "run")
    response = server.invoke(
        "graph_neighbors",
        {
            "node": run_symbol["node_id"],
            "direction": "outgoing",
            "relation_types": ["CALLS"],
            "max_depth": 1,
            "max_results": 10,
        },
    )
    assert response["status"] == "ok"
    result = response["result"]
    assert result["observed_relation_types"] == ["CALLS"]
    assert "pkg.py" in result["source_paths"]
    assert any(item["predicate"] == "CALLS" for item in result["observations"])
    evidence = result["evidence"]
    assert evidence
    assert evidence[0]["provenance"]["edge_metadata"]["observed_by"] == "python_ast_call_resolution"


def test_repository_summary_reports_call_graph_resolution_policy(tmp_path: Path):
    _write(tmp_path, "pkg.py", "def run():\n    return helper()\n\ndef helper():\n    return 1\n")
    server = RepositoryEvidenceTools(tmp_path)
    result = server.invoke("repository_summary", {})["result"]
    assert result["call_graph"]["resolution_policy"] == "conservative_ast_v1"
    assert result["call_graph"]["resolved_call_edges"] >= 1
    assert result["graph_relation_counts"]["CALLS"] >= 1

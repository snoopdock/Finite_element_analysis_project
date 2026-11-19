from __future__ import annotations

from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32b import EvidenceToolError, RepositoryEvidenceTools


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repository(root: Path) -> Path:
    _write(root, "src/pkg/__init__.py", "")
    _write(root, "src/pkg/a.py", "from src.pkg.b import helper\n\ndef run():\n    return helper()\n")
    _write(root, "src/pkg/b.py", "def helper():\n    return 7\n")
    return root


def test_ae32b_default_query_path_uses_networkx_and_counts_real_queries(tmp_path):
    server = RepositoryEvidenceTools(_repository(tmp_path))
    before = server.graph_runtime_report()
    assert before["active_computation_backend"] == "networkx"
    assert before["backend_pipeline"]["backend"] == "networkx"
    assert before["backend_execution"]["queries_attempted"] == 0

    response = server.invoke("graph_neighbors", {
        "node": "module:src.pkg.a",
        "direction": "outgoing",
        "relation_types": ["IMPORTS"],
        "max_depth": 1,
    })
    assert response["status"] == "ok"
    assert "module:src.pkg.b" in response["result"]["discovered_entities"]

    after = server.graph_runtime_report()
    assert after["backend_execution"]["queries_attempted"] == 1
    assert after["backend_execution"]["queries_succeeded"] == 1
    assert after["backend_execution"]["queries_failed"] == 0
    assert after["backend_execution"]["parity_verified_queries"] == 1
    assert after["backend_execution"]["parity_failures"] == 0


def test_ae32b_runtime_summary_reflects_backend_execution_after_query(tmp_path):
    server = RepositoryEvidenceTools(_repository(tmp_path))
    server.invoke("graph_neighbors", {
        "node": "module:src.pkg.a", "direction": "outgoing",
        "relation_types": ["IMPORTS"], "max_depth": 1,
    })
    summary = server.invoke("repository_summary", {})["result"]
    runtime = summary["graph_runtime"]
    assert runtime["active_computation_backend"] == "networkx"
    assert runtime["backend_execution"]["queries_attempted"] == 1
    assert runtime["backend_execution"]["parity_verified_queries"] == 1
    assert runtime["repository_code_executed"] is False
    assert runtime["network_calls_performed"] is False
    assert runtime["source_files_modified"] is False


def test_reference_backend_is_explicit_and_not_llm_selectable(tmp_path):
    server = RepositoryEvidenceTools(_repository(tmp_path), graph_backend="reference")
    summary = server.invoke("repository_summary", {})["result"]
    assert summary["graph_runtime"]["active_computation_backend"] == "python_reference_traversal"
    assert summary["graph_runtime"]["external_backend_adapters_active"] == []
    tool_names = {item["function"]["name"] for item in server.list_tools()}
    assert "select_graph_backend" not in tool_names


def test_unsupported_backend_configuration_fails_closed(tmp_path):
    with pytest.raises(EvidenceToolError, match="trusted configuration"):
        RepositoryEvidenceTools(_repository(tmp_path), graph_backend="arbitrary-model-choice")


def test_ae32b_scipy_backend_is_selected_by_trusted_configuration_and_observed(tmp_path):
    server = RepositoryEvidenceTools(_repository(tmp_path), graph_backend="scipy")
    before = server.graph_runtime_report()
    assert before["active_computation_backend"] == "scipy"
    assert before["backend_pipeline"]["backend"] == "scipy"
    assert before["external_backend_adapters_active"] == ["scipy"]
    response = server.invoke("graph_neighbors", {
        "node": "module:src.pkg.a",
        "direction": "outgoing",
        "relation_types": ["IMPORTS"],
        "max_depth": 1,
    })
    assert response["status"] == "ok"
    assert "module:src.pkg.b" in response["result"]["discovered_entities"]
    after = server.graph_runtime_report()
    assert after["backend_execution"]["queries_attempted"] == 1
    assert after["backend_execution"]["parity_verified_queries"] == 1
    assert after["backend_execution"]["parity_failures"] == 0
    assert after["backend_pipeline"]["lossless"] is False

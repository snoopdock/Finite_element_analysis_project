from __future__ import annotations

from pathlib import Path

from audit_engine.semantic_audit.ae32b import RepositoryEvidenceTools


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repository(root: Path) -> Path:
    _write(root, "src/pkg/__init__.py", "")
    _write(root, "src/pkg/lib.py", "def helper():\n    return 7\n")
    _write(root, "src/pkg/app.py", "from src.pkg.lib import helper\n\ndef run():\n    return helper()\n")
    _write(root, "src/pkg/consumer.py", "from src.pkg.app import run\n\ndef main():\n    return run()\n")
    _write(root, "tests/test_app.py", "from src.pkg.app import run\n\ndef test_run():\n    assert run() == 7\n")
    _write(root, ".github/workflows/ci.yml", "name: CI\n")
    return root


def test_graph_dependencies_reports_direct_and_transitive_nodes(tmp_path):
    tools = RepositoryEvidenceTools(_repository(tmp_path))
    response = tools.invoke("graph_neighbors", {
        "node": "module:src.pkg.app",
        "direction": "dependencies",
        "max_depth": 2,
        "relation_types": ["IMPORTS"],
    })
    assert response["status"] == "ok"
    result = response["result"]
    assert [item["node_id"] for item in result["direct_dependencies"]] == ["module:src.pkg.lib"]
    assert result["transitive_dependencies"] == []
    assert result["dependency_semantics"] == "dependencies"
    assert result["coverage_status"] == "complete_for_query"
    assert result["evidence"]


def test_graph_impact_finds_consumers_and_related_tests(tmp_path):
    tools = RepositoryEvidenceTools(_repository(tmp_path))
    response = tools.invoke("graph_neighbors", {
        "node": "file:src/pkg/lib.py",
        "direction": "impact",
        "max_depth": 3,
        "max_results": 30,
    })
    assert response["status"] == "ok"
    result = response["result"]
    ids = {item["node_id"] for item in result["discovered_nodes"]}
    assert "module:src.pkg.app" in ids
    assert "module:src.pkg.consumer" in ids
    assert "file:tests/test_app.py" in ids
    assert result["impact_candidates"]
    assert result["coverage_status"] == "complete_for_query"
    assert result["source_paths"]
    assert "runtime execution" in result["impact_semantics"]


def test_graph_impact_is_registered_as_graph_derived_tool(tmp_path):
    tools = RepositoryEvidenceTools(_repository(tmp_path))
    names = {item["function"]["name"] for item in tools.list_tools()}
    assert "graph_neighbors" in names
    schema = next(item["function"]["parameters"] for item in tools.list_tools()
                  if item["function"]["name"] == "graph_neighbors")
    assert {"dependencies", "dependents", "impact"}.issubset(
        set(schema["properties"]["direction"]["enum"])
    )
    from audit_engine.semantic_audit.ae32c.tool_policy import GRAPH_DERIVED_TOOL_NAMES
    assert "graph_neighbors" in GRAPH_DERIVED_TOOL_NAMES

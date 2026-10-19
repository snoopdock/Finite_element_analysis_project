from __future__ import annotations

from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32a.audit import (
    _component_for_path,
    _component_inventory,
    _configured_python_source_roots,
    _module_index,
    _parse_python,
    _workflow_inventory,
)
from audit_engine.semantic_audit.ae32b import RepositoryEvidenceTools
from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis import GraphTraversalEngine


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def test_alphanumeric_ae_component_names_are_discovered_and_sorted():
    paths = {
        "audit_engine/semantic_audit/ae32a/audit.py": {"source": "", "functions": [], "calls": [], "imports": []},
        "audit_engine/semantic_audit/ae32b/evidence_tools.py": {"source": "", "functions": [], "calls": [], "imports": []},
        "audit_engine/semantic_audit/ae32c/engine.py": {"source": "", "functions": [], "calls": [], "imports": []},
    }
    assert _component_for_path("audit_engine/semantic_audit/ae32c/engine.py") == "ae32c"
    rows = _component_inventory(paths, [])
    assert [row["component"] for row in rows] == ["ae32a", "ae32b", "ae32c"]


@pytest.mark.parametrize(
    ("trigger", "expected"),
    [
        ("workflow_dispatch", {"workflow_dispatch"}),
        ("[push, workflow_dispatch]", {"push", "workflow_dispatch"}),
        ("\n  push:\n  workflow_dispatch:\n", {"push", "workflow_dispatch"}),
    ],
)
def test_workflow_trigger_forms_are_parsed_from_yaml(trigger: str, expected: set[str]):
    text = f"""name: validation\non: {trigger}\njobs:\n  test:\n    steps:\n      - run: echo safe\n"""
    workflows, edges, issues = _workflow_inventory({".github/workflows/check.yml": text.encode()}, {})
    observed = {item["detail"] for item in workflows[0]["trigger_evidence"]}
    assert observed == expected
    assert workflows[0]["trigger_status"] == "parsed"
    assert edges == []
    assert issues == []


def test_workflow_commands_ignore_comments_and_echo_strings():
    text = '''name: validation
on: [push, workflow_dispatch]
jobs:
  test:
    steps:
      - run: echo "python -m pkg.echo"
      - run: |
          # python -m pkg.comment
          echo "python -m pkg.echo"
          python -m pkg.real
          python scripts/entry.py
'''
    contents = {
        ".github/workflows/check.yml": text.encode(),
        "pkg/real.py": b"def real():\n    return True\n",
        "scripts/entry.py": b"def main():\n    return True\n",
    }
    parsed = {
        "pkg/real.py": {"module": "pkg.real"},
        "scripts/entry.py": {"module": "scripts.entry"},
    }
    workflows, edges, issues = _workflow_inventory(contents, parsed)
    commands = workflows[0]["commands"]
    assert [(item["kind"], item["target"]) for item in commands] == [
        ("module_command", "pkg.real"),
        ("script_command", "scripts/entry.py"),
    ]
    assert {(edge["kind"], edge["target"]) for edge in edges} == {
        ("workflow_invokes_module", "pkg.real"),
        ("workflow_invokes_script", "scripts/entry.py"),
    }
    assert issues == []



def test_dynamic_working_directory_does_not_create_confirmed_invocation_edge():
    text = """name: validation
on: workflow_dispatch
jobs:
  test:
    steps:
      - working-directory: ${{ matrix.package_root }}
        run: python -m pkg.dynamic
"""
    workflows, edges, issues = _workflow_inventory({".github/workflows/check.yml": text.encode()}, {})
    assert workflows[0]["commands"][0]["evidence_status"] == "unresolved_dynamic_working_directory"
    assert edges == []
    assert issues == []


def test_non_root_working_directory_does_not_create_module_invocation_edge():
    text = """name: validation
on: workflow_dispatch
jobs:
  test:
    steps:
      - working-directory: src
        run: python -m pkg.module
"""
    contents = {
        ".github/workflows/check.yml": text.encode(),
        "src/pkg/module.py": b"def main():\n    return True\n",
    }
    parsed = {"src/pkg/module.py": {"module": "src.pkg.module"}}
    workflows, edges, issues = _workflow_inventory(contents, parsed)
    assert workflows[0]["commands"][0]["evidence_status"] == "unresolved_non_root_working_directory"
    assert edges == []
    assert issues == []

def test_src_layout_configuration_resolves_modules_and_relative_imports():
    contents = {
        "pyproject.toml": b'[tool.setuptools.package-dir]\n"" = "src"\n[tool.setuptools.packages.find]\nwhere = ["src"]\n',
        "src/pkg/__init__.py": b"",
        "src/pkg/a.py": b"from .b import B\n",
        "src/pkg/b.py": b"class B:\n    pass\n",
    }
    roots, root_issues = _configured_python_source_roots(contents)
    modules, packages = _module_index(
        [path for path in contents if path.lower().endswith(".py")], roots
    )
    parsed, import_edges, parse_issues = _parse_python(contents, modules, packages, roots)
    assert roots == ["src"]
    assert root_issues == []
    assert "pkg.a" in modules and "pkg.b" in modules
    assert "src.pkg.a" not in modules
    assert parsed["src/pkg/a.py"]["module"] == "pkg.a"
    assert any(edge["source"] == "pkg.a" and edge["target"] == "pkg.b" for edge in import_edges)
    assert parse_issues == []


def test_import_execution_context_is_preserved():
    contents = {
        "pkg/__init__.py": b"",
        "pkg/mod.py": (
            b"from typing import TYPE_CHECKING\n"
            b"import pkg.top\n"
            b"if TYPE_CHECKING:\n    import pkg.heavy\n"
            b"def run():\n    import pkg.lazy\n"
        ),
        "pkg/top.py": b"",
        "pkg/heavy.py": b"",
        "pkg/lazy.py": b"",
    }
    python_paths = [path for path in contents if path.lower().endswith(".py")]
    modules, packages = _module_index(python_paths)
    parsed, import_edges, parse_issues = _parse_python(contents, modules, packages)
    contexts = {
        (edge["target"], edge["execution_context"])
        for edge in import_edges
        if edge["source"] == "pkg.mod"
    }
    assert ("pkg.top", "module_level") in contexts
    assert ("pkg.heavy", "type_checking_only") in contexts
    assert ("pkg.lazy", "function_local") in contexts
    assert parsed["pkg/mod.py"]["imports"]
    assert parse_issues == []


def test_uppercase_python_extension_is_analyzed_consistently(tmp_path: Path):
    _write(tmp_path, "pkg/Module.PY", "def hidden_symbol():\n    return True\n")
    server = RepositoryEvidenceTools(tmp_path)
    response = server.invoke("search_symbols", {"query": "hidden_symbol", "kind": "function"})
    assert response["status"] == "ok"
    assert response["result"]["symbols"][0]["path"] == "pkg/Module.PY"
    assert response["result"]["symbols"][0]["module"] == "pkg.Module"


def test_duplicate_module_sources_and_symbol_occurrences_are_explicit(tmp_path: Path):
    _write(tmp_path, "foo.py", "def shared():\n    return 'module'\n")
    _write(tmp_path, "foo/__init__.py", "def shared():\n    return 'package'\n")
    server = RepositoryEvidenceTools(tmp_path)
    response = server.invoke("search_symbols", {"query": "shared", "kind": "function"})
    symbols = response["result"]["symbols"]
    assert len(symbols) == 2
    assert len({item["occurrence_id"] for item in symbols}) == 2
    assert len({item["symbol_id"] for item in symbols}) == 1
    assert server.module_identity_issues
    assert server.invoke("graph_neighbors", {"node": "symbol:foo::shared"})["error"]["code"] == "ambiguous_symbol_identity"


def test_related_test_search_does_not_match_module_name_prefixes(tmp_path: Path):
    _write(tmp_path, "src/pkg/a.py", "def target():\n    return 1\n")
    _write(tmp_path, "src/pkg/ab.py", "def other():\n    return 2\n")
    _write(tmp_path, "tests/test_ab.py", "from src.pkg.ab import other\n\ndef test_other():\n    assert other() == 2\n")
    server = RepositoryEvidenceTools(tmp_path)
    response = server.invoke("find_related_tests", {"target": "module:src.pkg.a"})
    assert response["status"] == "ok"
    assert not any(item["path"] == "tests/test_ab.py" for item in response["result"]["tests"])


def test_unicode_line_separator_does_not_shift_source_citations(tmp_path: Path):
    _write(tmp_path, "module.py", 'VALUE = """alpha\u2028beta"""\ndef target():\n    return 1\n')
    server = RepositoryEvidenceTools(tmp_path)
    symbols = server.invoke("search_symbols", {"query": "target", "kind": "function"})["result"]["symbols"]
    assert symbols[0]["line"] == 2
    source = server.invoke("read_source_file", {"path": "module.py", "start_line": 2, "end_line": 2})
    assert source["status"] == "ok"
    assert source["result"]["content"] == "2: def target():"


def test_workflow_context_follows_normalized_script_module_to_transitive_import(tmp_path: Path):
    _write(tmp_path, "main.py", "import pkg.service\n")
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/service.py", "import pkg.helper\n")
    _write(tmp_path, "pkg/helper.py", "def helper():\n    return True\n")
    _write(tmp_path, ".github/workflows/check.yml", """name: check
on:
  workflow_dispatch:
jobs:
  test:
    steps:
      - run: python main.py
""")
    server = RepositoryEvidenceTools(tmp_path)
    response = server.invoke("find_workflow_context", {"target": "module:pkg.helper"})
    assert response["status"] == "ok"
    assert any(item["path"] == ".github/workflows/check.yml" for item in response["result"]["workflows"])


def test_search_truncation_is_false_when_result_count_equals_limit(tmp_path: Path):
    _write(tmp_path, "one.txt", "MATCH\nother\n")
    server = RepositoryEvidenceTools(tmp_path)
    response = server.invoke("search_repository", {"query": "MATCH", "mode": "content", "max_results": 1})
    assert response["status"] == "ok"
    assert len(response["result"]["matches"]) == 1
    assert response["result"]["truncated"] is False


def test_graph_traversal_budget_reports_incomplete_coverage():
    graph = SemanticGraph()
    for node_id in ("A", "B", "C"):
        graph.add_node(SemanticNode(node_id, "Node"))
    graph.add_edge(SemanticEdge("A", "B", "IMPORTS"))
    graph.add_edge(SemanticEdge("A", "C", "IMPORTS"))
    result = GraphTraversalEngine(graph).walk(
        "A", relation_types=("IMPORTS",), max_depth=3, max_visited_nodes=2
    )
    assert result.truncated is True
    assert result.stop_reason == "max_visited_nodes"
    assert result.visited_nodes == ("B",)
    assert result.examined_edges == 2


def test_graph_traversal_step_budget_reports_incomplete_coverage():
    graph = SemanticGraph()
    for node_id in ("A", "B", "C"):
        graph.add_node(SemanticNode(node_id, "Node"))
    graph.add_edge(SemanticEdge("A", "B", "IMPORTS"))
    graph.add_edge(SemanticEdge("A", "C", "IMPORTS"))
    result = GraphTraversalEngine(graph).walk(
        "A", relation_types=("IMPORTS",), max_depth=3, max_steps=1
    )
    assert result.truncated is True
    assert result.stop_reason == "max_traversal_steps"
    assert result.examined_edges == 1

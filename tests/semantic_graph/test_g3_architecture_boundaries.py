import ast
from pathlib import Path


FORBIDDEN_BACKEND_ROOTS = {"networkx", "scipy", "igraph", "graph_tool"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_analysis_and_query_layers_do_not_import_graph_backends():
    roots = Path("audit_engine/semantic_audit/graph")
    paths = list((roots / "analysis").glob("*.py")) + list((roots / "queries").glob("*.py"))
    violations = {
        str(path): sorted(_imports(path) & FORBIDDEN_BACKEND_ROOTS)
        for path in paths
        if _imports(path) & FORBIDDEN_BACKEND_ROOTS
    }
    assert violations == {}


def test_analysis_layer_does_not_import_audit_findings_or_reports():
    roots = Path("audit_engine/semantic_audit/graph/analysis")
    forbidden_text = ("SemanticFinding", "reports.json_report")
    violations = []
    for path in roots.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(value in text for value in forbidden_text):
            violations.append(str(path))
    assert violations == []

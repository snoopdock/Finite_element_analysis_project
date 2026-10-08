
import ast
from pathlib import Path


FORBIDDEN_BACKEND_ROOTS = {"networkx", "scipy", "igraph", "graph_tool"}


def _import_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def test_verification_rules_and_findings_do_not_import_graph_backends():
    roots = [
        Path("audit_engine/semantic_audit/verification"),
        Path("audit_engine/semantic_audit/rules"),
        Path("audit_engine/semantic_audit/findings"),
    ]
    violations = {}
    for root in roots:
        for path in root.glob("*.py"):
            imported = _import_modules(path)
            backend = sorted(
                value for value in imported
                if value.split(".")[0] in FORBIDDEN_BACKEND_ROOTS
            )
            if backend:
                violations[str(path)] = backend
    assert violations == {}


def test_graph_analysis_does_not_depend_on_verification_rules_or_findings():
    forbidden = (
        "audit_engine.semantic_audit.verification",
        "audit_engine.semantic_audit.rules",
        "audit_engine.semantic_audit.findings",
    )
    violations = {}
    for path in Path("audit_engine/semantic_audit/graph/analysis").glob("*.py"):
        imported = _import_modules(path)
        hits = sorted(value for value in imported if value.startswith(forbidden))
        if hits:
            violations[str(path)] = hits
    assert violations == {}


def test_verification_layer_does_not_import_findings_or_rules():
    violations = {}
    for path in Path("audit_engine/semantic_audit/verification").glob("*.py"):
        imported = _import_modules(path)
        hits = sorted(
            value for value in imported
            if value.startswith("audit_engine.semantic_audit.findings")
            or value.startswith("audit_engine.semantic_audit.rules")
        )
        if hits:
            violations[str(path)] = hits
    assert violations == {}


def test_candidate_knowledge_has_no_canonical_graph_mutation_api():
    path = Path("audit_engine/semantic_audit/verification/candidates.py")
    text = path.read_text(encoding="utf-8")
    assert "add_edge(" not in text
    assert "SemanticGraph" not in text

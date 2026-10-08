import ast
from pathlib import Path

ROOT = Path("audit_engine/semantic_audit/evolution")


def imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def test_execution_layer_has_no_backend_graph_dependency():
    names = []
    for filename in ("replay.py", "reconciliation.py", "execution.py", "execution_memory.py"):
        names.extend(imports(ROOT / filename))
    assert not any(name == "networkx" or name.startswith("networkx.") for name in names)
    assert not any(name == "scipy" or name.startswith("scipy.") for name in names)


def test_reconciliation_has_no_graph_mutation_or_promotion_dependency():
    names = imports(ROOT / "reconciliation.py")
    assert not any("promotion" in name for name in names)
    assert not any("semantic_graph" in name for name in names)


def test_execution_does_not_write_long_term_memory_implicitly():
    text = (ROOT / "execution.py").read_text(encoding="utf-8")
    assert "AuditLongTermMemory" not in text
    assert "append_artifact(" not in text

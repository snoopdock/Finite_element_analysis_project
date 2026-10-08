import ast
from pathlib import Path


ROOT = Path("audit_engine/semantic_audit")


def imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.append(node.module)
    return values


def test_domain_rule_layer_does_not_import_networkx_or_scipy():
    files = list((ROOT / "rules").glob("*.py")) + list((ROOT / "verification").glob("*.py"))
    imports = [name for path in files for name in imported_modules(path)]
    assert not any(name == "networkx" or name.startswith("networkx.") for name in imports)
    assert not any(name == "scipy" or name.startswith("scipy.") for name in imports)


def test_domain_verifiers_do_not_import_findings_or_rule_policy():
    imports = imported_modules(ROOT / "verification" / "domain.py")
    assert not any("findings" in name for name in imports)
    assert not any("semantic_audit.rules" in name for name in imports)


def test_promotion_layer_does_not_import_llm_provider_or_backend_graph_libraries():
    imports = [
        name
        for path in (ROOT / "promotion").glob("*.py")
        for name in imported_modules(path)
    ]
    forbidden = ("providers", "networkx", "scipy")
    assert not any(any(name == item or name.startswith(item + ".") for item in forbidden) for name in imports)

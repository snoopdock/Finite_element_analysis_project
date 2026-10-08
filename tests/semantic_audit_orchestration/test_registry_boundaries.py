import ast
from pathlib import Path

from audit_engine.semantic_audit.verification import VerifierRegistry

from .conftest import CheapConfirmVerifier, ExpensiveConfirmVerifier


def test_registry_compatible_returns_all_supported_verifiers(observation_obligation):
    registry = VerifierRegistry()
    registry.register(ExpensiveConfirmVerifier())
    registry.register(CheapConfirmVerifier())
    assert [v.descriptor.verifier_id for v in registry.compatible(observation_obligation)] == [
        "cheap-confirm", "expensive-confirm"
    ]


def test_registry_cost_awareness_does_not_leak_into_verification_layer():
    root = Path("audit_engine/semantic_audit/verification")
    forbidden = "audit_engine.semantic_audit.orchestration"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(name.startswith(forbidden) for name in imports), path


def test_orchestration_layer_does_not_import_findings_rules_or_memory():
    root = Path("audit_engine/semantic_audit/orchestration")
    forbidden = (
        "audit_engine.semantic_audit.findings",
        "audit_engine.semantic_audit.rules",
        "audit_engine.semantic_audit.evolution.memory",
    )
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(name.startswith(forbidden) for name in imports), (path, imports)

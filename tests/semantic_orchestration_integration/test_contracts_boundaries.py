import ast
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_core_layers_do_not_depend_back_on_integration_layer():
    roots = [
        ROOT / "audit_engine/semantic_audit/graph",
        ROOT / "audit_engine/semantic_audit/verification",
        ROOT / "audit_engine/semantic_audit/evolution",
        ROOT / "audit_engine/semantic_audit/orchestration",
        ROOT / "audit_engine/semantic_audit/rules",
        ROOT / "audit_engine/semantic_audit/findings",
        ROOT / "audit_engine/semantic_audit/promotion",
    ]
    forbidden = "audit_engine.semantic_audit.integration"
    for root in roots:
        for path in root.rglob("*.py"):
            assert not any(name.startswith(forbidden) for name in _imports(path)), path


def test_integration_layer_does_not_import_backend_graph_or_promotion_authority():
    root = ROOT / "audit_engine/semantic_audit/integration"
    forbidden = (
        "audit_engine.semantic_audit.graph.backend",
        "audit_engine.semantic_audit.promotion",
    )
    for path in root.glob("*.py"):
        imports = _imports(path)
        assert not any(any(name.startswith(prefix) for prefix in forbidden) for name in imports), path


def test_g332_contracts_and_schemas_parse():
    for rel in (
        "specs/contracts/semantic_reverification_orchestration_bridge_contract.yaml",
        "specs/contracts/semantic_orchestration_reconciliation_contract.yaml",
        "specs/contracts/semantic_orchestration_memory_commit_contract.yaml",
        "specs/contracts/semantic_budget_aware_reverification_contract.yaml",
    ):
        payload = yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))
        assert payload["status"] == "normative"
    for rel in (
        "specs/schemas/semantic_reverification_orchestration_preparation.schema.json",
        "specs/schemas/semantic_reverification_orchestration_reconciliation.schema.json",
        "specs/schemas/semantic_orchestration_memory_commit.schema.json",
        "specs/schemas/semantic_budget_aware_reverification.schema.json",
    ):
        payload = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        assert payload["$schema"].endswith("2020-12/schema")


def test_g3_workflows_05_through_13_are_manual_only():
    workflow_dir = ROOT / ".github/workflows"
    for number in range(5, 14):
        matches = sorted(workflow_dir.glob(f"{number:02d}_*.yml"))
        assert len(matches) == 1, number
        text = matches[0].read_text(encoding="utf-8")
        assert "on:\n  workflow_dispatch:\n" in text, matches[0]
        assert "\n  push:" not in text, matches[0]
        assert "\n  pull_request:" not in text, matches[0]


def test_new_workflow_runs_full_regression_and_validator():
    text = (ROOT / ".github/workflows/13_semantic_reverification_orchestration_integration_validation.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "pytest -q" in text
    assert "validate_semantic_reverification_orchestration_integration.py" in text

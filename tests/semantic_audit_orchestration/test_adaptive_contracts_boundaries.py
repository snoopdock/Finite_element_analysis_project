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


def test_adaptive_layer_does_not_import_findings_rules_memory_or_promotion():
    for rel in (
        "audit_engine/semantic_audit/orchestration/replanning.py",
        "audit_engine/semantic_audit/orchestration/adaptive.py",
    ):
        imports = _imports(ROOT / rel)
        forbidden = (
            "audit_engine.semantic_audit.findings",
            "audit_engine.semantic_audit.rules",
            "audit_engine.semantic_audit.evolution.memory",
            "audit_engine.semantic_audit.promotion",
        )
        assert not any(any(item.startswith(prefix) for prefix in forbidden) for item in imports)


def test_g331_contracts_and_schemas_parse():
    for rel in (
        "specs/contracts/semantic_adaptive_replanning_contract.yaml",
        "specs/contracts/semantic_adaptive_orchestration_session_contract.yaml",
        "specs/contracts/manual_g3_validation_workflow_contract.yaml",
    ):
        payload = yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))
        assert payload["status"] == "normative"
    for rel in (
        "specs/schemas/semantic_adaptive_replan.schema.json",
        "specs/schemas/semantic_adaptive_orchestration_session.schema.json",
    ):
        payload = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        assert payload["$schema"].endswith("2020-12/schema")


def test_g3_validation_workflows_are_manual_only():
    workflow_dir = ROOT / ".github" / "workflows"
    names = [
        "05_semantic_graph_analysis_validation.yml",
        "06_semantic_verification_validation.yml",
        "07_semantic_domain_verification_validation.yml",
        "08_semantic_graph_evolution_validation.yml",
        "09_semantic_incremental_reverification_validation.yml",
        "10_semantic_reverification_execution_validation.yml",
        "11_semantic_audit_orchestration_validation.yml",
        "12_semantic_adaptive_orchestration_validation.yml",
    ]
    for name in names:
        text = (workflow_dir / name).read_text(encoding="utf-8")
        assert "on:\n  workflow_dispatch:\n" in text, name
        assert "\n  push:" not in text, name
        assert "\n  pull_request:" not in text, name


def test_new_workflow_runs_full_regression_and_validator():
    text = (ROOT / ".github/workflows/12_semantic_adaptive_orchestration_validation.yml").read_text(
        encoding="utf-8"
    )
    assert "pytest -q" in text
    assert "validate_semantic_adaptive_orchestration.py" in text
    assert "workflow_dispatch:" in text

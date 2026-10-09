from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml


CONTRACTS = (
    "cnf_rup_unsat_proof_contract.yaml",
    "unsat_proof_checker_registry_contract.yaml",
    "proof_carrying_external_solver_contract.yaml",
)
SCHEMAS = (
    "cnf_rup_unsat_proof.schema.json",
    "unsat_proof_check.schema.json",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_g343_contracts_parse():
    for name in CONTRACTS:
        payload = yaml.safe_load((Path("specs/contracts") / name).read_text(encoding="utf-8"))
        assert payload["status"] == "normative"


def test_g343_schemas_parse():
    for name in SCHEMAS:
        payload = json.loads((Path("specs/schemas") / name).read_text(encoding="utf-8"))
        assert payload["type"] == "object"


def test_unsat_proof_checker_has_no_subprocess_or_external_execution_dependency():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/unsat_proof.py"))
    assert "subprocess" not in imports
    assert not any(name.endswith("external_process") for name in imports)


def test_unsat_proof_checker_does_not_import_placeholder_formal_layer():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/unsat_proof.py"))
    assert not any(name == "formal" or name.startswith("formal.") for name in imports)


def test_subprocess_remains_confined_to_external_process_boundary():
    root = Path("audit_engine/semantic_audit/high_assurance")
    importing = []
    for path in root.glob("*.py"):
        imports = _imports(path)
        if any(name == "subprocess" or name.startswith("subprocess.") for name in imports):
            importing.append(path.name)
    assert importing == ["external_process.py"]


def test_formal_router_still_inactive():
    text = Path("formal/router.py").read_text(encoding="utf-8")
    assert "Formal layer is not yet active" in text


def test_workflow_17_is_manual_only():
    text = Path(".github/workflows/17_semantic_proof_carrying_unsat_validation.yml").read_text(encoding="utf-8")
    assert "on:\n  workflow_dispatch:\n" in text
    assert "\n  push:" not in text
    assert "\n  pull_request:" not in text


def test_g3_workflows_05_through_17_are_manual_only():
    folder = Path(".github/workflows")
    for number in range(5, 18):
        matches = list(folder.glob(f"{number:02d}_*.yml"))
        assert len(matches) == 1, number
        text = matches[0].read_text(encoding="utf-8")
        assert "on:\n  workflow_dispatch:\n" in text
        assert "\n  push:" not in text
        assert "\n  pull_request:" not in text


def test_new_workflow_runs_full_regression_and_g343_validator():
    text = Path(".github/workflows/17_semantic_proof_carrying_unsat_validation.yml").read_text(encoding="utf-8")
    assert "pytest -q" in text
    assert "validate_semantic_proof_carrying_unsat.py" in text

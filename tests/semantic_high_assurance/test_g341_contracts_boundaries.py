from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml


CONTRACTS = (
    "high_assurance_explicit_activation_contract.yaml",
    "bounded_cnf_solver_contract.yaml",
    "registered_executable_witness_contract.yaml",
    "solver_certificate_contract.yaml",
)
SCHEMAS = (
    "bounded_cnf_solver_certificate.schema.json",
    "registered_executable_witness_trace.schema.json",
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


def test_g341_contracts_are_parseable():
    for name in CONTRACTS:
        assert yaml.safe_load((Path("specs/contracts") / name).read_text(encoding="utf-8"))


def test_g341_json_schemas_are_parseable():
    for name in SCHEMAS:
        payload = json.loads((Path("specs/schemas") / name).read_text(encoding="utf-8"))
        assert payload["type"] == "object"


def test_cnf_solver_does_not_import_inactive_formal_layer():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/cnf_solver.py"))
    assert not any(name == "formal" or name.startswith("formal.") for name in imports)


def test_executable_witness_has_no_subprocess_shell_or_network_imports():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/executable_witness.py"))
    forbidden = {"subprocess", "socket", "requests", "urllib", "os.system"}
    assert not any(name in forbidden or name.startswith("subprocess.") for name in imports)


def test_existing_formal_router_remains_inactive():
    text = Path("formal/router.py").read_text(encoding="utf-8")
    assert "Formal layer is not yet active" in text


def test_workflow_15_is_manual_only():
    payload = Path(".github/workflows/15_semantic_solver_witness_validation.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in payload
    assert "push:" not in payload
    assert "pull_request:" not in payload

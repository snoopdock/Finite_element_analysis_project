from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml


CONTRACTS = (
    "external_process_containment_contract.yaml",
    "external_solver_protocol_contract.yaml",
    "solver_certificate_validation_contract.yaml",
    "controlled_external_cnf_solver_contract.yaml",
)
SCHEMAS = (
    "external_process_transcript.schema.json",
    "external_solver_response.schema.json",
    "solver_certificate_validation.schema.json",
    "semantic_validation_envelope.schema.json",
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


def test_g342_contracts_are_parseable():
    for name in CONTRACTS:
        assert yaml.safe_load((Path("specs/contracts") / name).read_text(encoding="utf-8"))


def test_g342_schemas_are_parseable():
    for name in SCHEMAS:
        payload = json.loads((Path("specs/schemas") / name).read_text(encoding="utf-8"))
        assert payload["type"] == "object"


def test_subprocess_import_is_confined_to_external_process_boundary():
    root = Path("audit_engine/semantic_audit/high_assurance")
    importing = []
    for path in root.glob("*.py"):
        imports = _imports(path)
        if any(name == "subprocess" or name.startswith("subprocess.") for name in imports):
            importing.append(path.name)
    assert importing == ["external_process.py"]


def test_core_controlled_executor_still_has_no_subprocess_api():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/execution.py"))
    assert "subprocess" not in imports


def test_external_solver_does_not_import_placeholder_formal_layer():
    for name in ("external_process.py", "external_solver.py", "certificate_validation.py"):
        imports = _imports(Path("audit_engine/semantic_audit/high_assurance") / name)
        assert not any(item == "formal" or item.startswith("formal.") for item in imports)


def test_formal_router_remains_inactive():
    text = Path("formal/router.py").read_text(encoding="utf-8")
    assert "Formal layer is not yet active" in text


def test_workflow_16_is_manual_only():
    text = Path(".github/workflows/16_semantic_external_solver_validation.yml").read_text(encoding="utf-8")
    assert "on:\n  workflow_dispatch:\n" in text
    assert "\n  push:" not in text
    assert "\n  pull_request:" not in text


def test_g3_workflows_05_through_16_are_manual_only():
    workflow_dir = Path(".github/workflows")
    for n in range(5, 17):
        matches = list(workflow_dir.glob(f"{n:02d}_*.yml"))
        assert len(matches) == 1, n
        text = matches[0].read_text(encoding="utf-8")
        assert "on:\n  workflow_dispatch:\n" in text
        assert "\n  push:" not in text
        assert "\n  pull_request:" not in text


def test_validation_envelope_schema_allows_certificate_complete_scope():
    payload = json.loads(Path("specs/schemas/semantic_validation_envelope.schema.json").read_text(encoding="utf-8"))
    values = payload["properties"]["completeness"]["enum"]
    assert "certificate_complete_within_scope" in values

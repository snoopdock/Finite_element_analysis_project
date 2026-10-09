from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml


CONTRACTS = (
    "cnf_drat_unsat_proof_contract.yaml",
    "drat_deletion_semantics_contract.yaml",
    "drat_resource_limit_contract.yaml",
)
SCHEMAS = (
    "cnf_drat_unsat_proof.schema.json",
    "drat_proof_check.schema.json",
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


def test_g344_contracts_parse():
    for name in CONTRACTS:
        payload = yaml.safe_load((Path("specs/contracts") / name).read_text(encoding="utf-8"))
        assert payload["status"] == "normative"


def test_g344_schemas_parse():
    for name in SCHEMAS:
        payload = json.loads((Path("specs/schemas") / name).read_text(encoding="utf-8"))
        assert payload["type"] == "object"


def test_drat_checker_has_no_subprocess_or_external_process_dependency():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/drat_proof.py"))
    assert "subprocess" not in imports
    assert not any(name.endswith("external_process") for name in imports)


def test_drat_checker_has_no_placeholder_formal_dependency():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/drat_proof.py"))
    assert not any(name == "formal" or name.startswith("formal.") for name in imports)


def test_drat_checker_does_not_import_findings_rules_graph_mutators_or_memory():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/drat_proof.py"))
    forbidden_fragments = ("findings", "rules", "promotion", "memory")
    assert not any(any(fragment in name for fragment in forbidden_fragments) for name in imports)


def test_external_process_boundary_remains_unique_subprocess_owner():
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


def test_workflow_18_is_manual_only():
    text = Path(".github/workflows/18_semantic_drat_proof_validation.yml").read_text(encoding="utf-8")
    assert "on:\n  workflow_dispatch:\n" in text
    assert "\n  push:" not in text
    assert "\n  pull_request:" not in text


def test_g3_workflows_05_through_18_are_manual_only():
    folder = Path(".github/workflows")
    for number in range(5, 19):
        matches = list(folder.glob(f"{number:02d}_*.yml"))
        assert len(matches) == 1, number
        text = matches[0].read_text(encoding="utf-8")
        assert "on:\n  workflow_dispatch:\n" in text
        assert "\n  push:" not in text
        assert "\n  pull_request:" not in text


def test_new_workflow_runs_full_regression_and_g344_validator():
    text = Path(".github/workflows/18_semantic_drat_proof_validation.yml").read_text(encoding="utf-8")
    assert "pytest -q" in text
    assert "validate_semantic_drat_proof_checking.py" in text

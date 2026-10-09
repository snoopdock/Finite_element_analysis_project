from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml


CONTRACTS = (
    "detached_proof_artifact_reference_contract.yaml",
    "content_addressed_proof_store_contract.yaml",
    "streaming_cnf_proof_checking_contract.yaml",
    "detached_unsat_proof_validation_contract.yaml",
)
SCHEMAS = (
    "detached_proof_artifact_reference.schema.json",
    "streaming_cnf_proof_header.schema.json",
    "streaming_cnf_proof_step.schema.json",
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


def test_g345_contracts_parse():
    for name in CONTRACTS:
        payload = yaml.safe_load((Path("specs/contracts") / name).read_text(encoding="utf-8"))
        assert payload["status"] == "normative"


def test_g345_schemas_parse():
    for name in SCHEMAS:
        payload = json.loads((Path("specs/schemas") / name).read_text(encoding="utf-8"))
        assert payload["type"] == "object"


def test_proof_artifact_layer_has_no_subprocess_network_or_external_process_dependency():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/proof_artifact.py"))
    assert "subprocess" not in imports
    assert not any(name.startswith("urllib") or name.startswith("http") for name in imports)
    assert not any(name.endswith("external_process") for name in imports)


def test_streaming_checker_has_no_subprocess_formal_or_audit_judgment_dependency():
    imports = _imports(Path("audit_engine/semantic_audit/high_assurance/streaming_proof.py"))
    assert "subprocess" not in imports
    assert not any(name == "formal" or name.startswith("formal.") for name in imports)
    forbidden = ("findings", "rules", "promotion", "memory")
    assert not any(any(fragment in name for fragment in forbidden) for name in imports)


def test_external_process_boundary_remains_unique_subprocess_owner():
    root = Path("audit_engine/semantic_audit/high_assurance")
    importing = []
    for path in root.glob("*.py"):
        imports = _imports(path)
        if any(name == "subprocess" or name.startswith("subprocess.") for name in imports):
            importing.append(path.name)
    assert importing == ["external_process.py"]


def test_detached_reference_code_contains_no_location_authority_fields():
    text = Path("audit_engine/semantic_audit/high_assurance/proof_artifact.py").read_text(encoding="utf-8")
    assert '"path"' not in text.split("allowed =", 1)[1].split("}", 1)[0]
    assert '"url"' not in text.split("allowed =", 1)[1].split("}", 1)[0]


def test_formal_router_still_inactive():
    text = Path("formal/router.py").read_text(encoding="utf-8")
    assert "Formal layer is not yet active" in text


def test_workflow_19_is_manual_only():
    text = Path(".github/workflows/19_semantic_detached_proof_artifact_validation.yml").read_text(encoding="utf-8")
    assert "on:\n  workflow_dispatch:\n" in text
    assert "\n  push:" not in text
    assert "\n  pull_request:" not in text


def test_g3_workflows_05_through_19_are_manual_only():
    folder = Path(".github/workflows")
    for number in range(5, 20):
        matches = list(folder.glob(f"{number:02d}_*.yml"))
        assert len(matches) == 1, number
        text = matches[0].read_text(encoding="utf-8")
        assert "on:\n  workflow_dispatch:\n" in text
        assert "\n  push:" not in text
        assert "\n  pull_request:" not in text


def test_workflow_19_runs_full_regression_and_g345_validator():
    text = Path(".github/workflows/19_semantic_detached_proof_artifact_validation.yml").read_text(encoding="utf-8")
    assert "pytest -q" in text
    assert "validate_semantic_detached_proof_artifacts.py" in text

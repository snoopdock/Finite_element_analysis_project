from __future__ import annotations

import json
from pathlib import Path

import yaml

from audit_engine.semantic_audit.high_assurance import (
    ControlledHighAssuranceExecutor,
    builtin_high_assurance_adapter_registry,
)
from audit_engine.semantic_audit.high_assurance.serialization import write_high_assurance_execution
from audit_engine.semantic_audit.verification.models import VerificationContext

from .conftest import static_import_obligation


CONTRACTS = (
    "high_assurance_verifier_contract.yaml",
    "high_assurance_validation_envelope_contract.yaml",
    "high_assurance_witness_contract.yaml",
    "high_assurance_execution_contract.yaml",
    "controlled_high_assurance_policy_contract.yaml",
)
SCHEMAS = (
    "semantic_high_assurance_execution.schema.json",
    "semantic_validation_envelope.schema.json",
    "semantic_verification_witness.schema.json",
)


def test_g340_contracts_parse():
    for name in CONTRACTS:
        payload = yaml.safe_load((Path("specs/contracts") / name).read_text(encoding="utf-8"))
        assert payload


def test_g340_json_schemas_parse():
    for name in SCHEMAS:
        payload = json.loads((Path("specs/schemas") / name).read_text(encoding="utf-8"))
        assert payload["type"] == "object"


def test_execution_record_writer(analysis_result, semantic_graph, tmp_path):
    obligation = static_import_obligation(analysis_result, "import os\n")
    record = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry()).execute(
        obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="python-static-import"
    )
    target = write_high_assurance_execution(record, tmp_path / "record.json")
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["execution_id"] == record.execution_id
    assert "source_text" in payload["request"]["parameter_keys"]
    assert "import os" not in target.read_text(encoding="utf-8")

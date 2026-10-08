
import json
from pathlib import Path

import yaml

from audit_engine.semantic_audit.verification import (
    ObservationContractVerifier,
    VerificationArtifactSerializer,
    VerificationObligation,
    VerificationService,
    VerifierRegistry,
)


def _verified(result):
    obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type="observation_contract",
        parameters={"subject_id": "A", "predicate": "DEPENDS_ON", "object_id": "B"},
    )
    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    return obligation, VerificationService(registry).verify(obligation, result)


def test_verification_bundle_json_serializable(dependency_result):
    obligation, receipt = _verified(dependency_result)
    payload = VerificationArtifactSerializer.bundle_to_dict([obligation], [receipt])
    encoded = json.dumps(payload, sort_keys=True)
    assert "semantic_verification_bundle/v1" in encoded
    assert '"decision": "confirmed"' in encoded


def test_verification_bundle_writer(tmp_path, dependency_result):
    obligation, receipt = _verified(dependency_result)
    path = VerificationArtifactSerializer.write_bundle(
        [obligation], [receipt], tmp_path / "verification.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["receipt_count"] == 1


def test_g31_yaml_contracts_are_parseable():
    names = [
        "semantic_verification_contract.yaml",
        "verifier_contract.yaml",
        "semantic_audit_rule_contract.yaml",
        "audit_finding_contract.yaml",
        "candidate_knowledge_contract.yaml",
        "semantic_graph_analysis_contract.yaml",
    ]
    for name in names:
        payload = yaml.safe_load(Path("specs/contracts", name).read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert payload["version"] >= 1


def test_g31_json_schemas_are_parseable():
    for name in ("semantic_verification_schema.json", "audit_finding_schema.json"):
        payload = json.loads(Path("docs/schemas", name).read_text(encoding="utf-8"))
        assert payload["$schema"].endswith("2020-12/schema")

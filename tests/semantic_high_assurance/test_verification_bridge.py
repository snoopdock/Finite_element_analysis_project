from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import register_builtin_high_assurance_verifiers
from audit_engine.semantic_audit.verification import VerificationDecision, VerificationService, VerifierRegistry

from .conftest import digest_obligation, static_import_obligation


def service_with_high_assurance():
    registry = VerifierRegistry()
    register_builtin_high_assurance_verifiers(registry)
    return VerificationService(registry), registry


def test_high_assurance_verifier_seals_standard_receipt(analysis_result, semantic_graph):
    service, _ = service_with_high_assurance()
    obligation = static_import_obligation(analysis_result, "import os\n")
    receipt = service.verify(obligation, analysis_result, semantic_graph=semantic_graph)
    assert receipt.decision is VerificationDecision.CONFIRMED
    assert receipt.evidence_state is VerificationStatus.VALIDATED
    assert receipt.verifier_id == "python-static-import"
    execution = receipt.details["high_assurance_execution"]
    assert execution["result"]["validation_envelope"]["completeness"] == "exhaustive_within_scope"


def test_high_assurance_receipt_contains_witness_ids(analysis_result, semantic_graph):
    service, _ = service_with_high_assurance()
    receipt = service.verify(static_import_obligation(analysis_result, "import networkx\n"), analysis_result, semantic_graph=semantic_graph)
    witnesses = receipt.details["high_assurance_execution"]["result"]["witnesses"]
    assert witnesses
    assert all(value["witness_id"].startswith("verification-witness:") for value in witnesses)


def test_digest_high_assurance_verifier_is_registered(analysis_result, semantic_graph):
    service, registry = service_with_high_assurance()
    assert registry.get("artifact-digest-integrity") is not None
    receipt = service.verify(digest_obligation(analysis_result, "artifact"), analysis_result, semantic_graph=semantic_graph)
    assert receipt.decision is VerificationDecision.CONFIRMED


def test_requested_verifier_authority_is_preserved(analysis_result, semantic_graph):
    service, registry = service_with_high_assurance()
    obligation = static_import_obligation(analysis_result, "import os\n")
    compatible = registry.compatible(obligation)
    assert tuple(v.descriptor.verifier_id for v in compatible) == ("python-static-import",)


def test_policy_denial_does_not_promote_evidence_state(analysis_result, semantic_graph):
    from audit_engine.semantic_audit.high_assurance import HighAssurancePolicy
    registry = VerifierRegistry()
    register_builtin_high_assurance_verifiers(registry, policy=HighAssurancePolicy(max_timeout_ms=10))
    obligation = static_import_obligation(analysis_result, "import os\n")
    # helper requests timeout 1000, deliberately above policy
    receipt = VerificationService(registry).verify(obligation, analysis_result, semantic_graph=semantic_graph)
    assert receipt.decision is VerificationDecision.ERROR
    assert receipt.evidence_state is VerificationStatus.PROPOSED
    assert receipt.error == "timeout_exceeds_policy_limit"

from __future__ import annotations

import hashlib

from audit_engine.semantic_audit.high_assurance import ControlledHighAssuranceExecutor, builtin_high_assurance_adapter_registry
from audit_engine.semantic_audit.verification.models import VerificationContext, VerificationDecision

from .conftest import digest_obligation


def test_digest_adapter_confirms_matching_digest(analysis_result, semantic_graph):
    obligation = digest_obligation(analysis_result, "artifact")
    executor = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry())
    result = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="artifact-digest-integrity").result
    assert result.decision is VerificationDecision.CONFIRMED
    witness = result.witnesses[0]
    assert witness.details["actual_sha256"] == hashlib.sha256(b"artifact").hexdigest()


def test_digest_adapter_refutes_mismatch(analysis_result, semantic_graph):
    obligation = digest_obligation(analysis_result, "artifact", "0" * 64)
    executor = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry())
    result = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="artifact-digest-integrity").result
    assert result.decision is VerificationDecision.REFUTED


def test_digest_adapter_rejects_invalid_expected_digest(analysis_result, semantic_graph):
    obligation = digest_obligation(analysis_result, "artifact", "g" * 64)
    executor = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry())
    record = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="artifact-digest-integrity")
    assert record.status.value == "adapter_error"
    assert "expected_sha256" in record.denial_reason

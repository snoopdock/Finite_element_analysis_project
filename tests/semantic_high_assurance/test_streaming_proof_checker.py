from __future__ import annotations

import json
from pathlib import Path

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import (
    DRAT_PROOF_FORMAT,
    LocalContentAddressedProofStore,
    PROOF_ARTIFACT_FORMAT,
    ProofArtifactReference,
    ProofArtifactStoreRegistry,
    RUP_PROOF_FORMAT,
    StreamingDetachedProofChecker,
    StreamingProofCheckLimits,
    ValidationCompleteness,
    validate_external_cnf_certificate,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import cnf_digest


def _bytes(proof_format: str, digest: str, steps) -> bytes:
    payloads = [
        {"artifact_format": PROOF_ARTIFACT_FORMAT, "proof_format": proof_format, "cnf_digest": digest},
        *steps,
    ]
    return b"".join((json.dumps(item, separators=(",", ":")) + "\n").encode() for item in payloads)


def _registry(tmp_path: Path, proof_format: str, digest: str, steps):
    store = LocalContentAddressedProofStore(tmp_path, store_id="proofs")
    reference = store.put_bytes(_bytes(proof_format, digest, steps), proof_format=proof_format, cnf_digest=digest)
    registry = ProofArtifactStoreRegistry()
    registry.register(store)
    return registry, reference


def test_streaming_rup_accepts_detached_empty_clause(tmp_path: Path):
    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)
    registry, reference = _registry(tmp_path, RUP_PROOF_FORMAT, digest, [{"op": "add", "clause": []}])
    result = StreamingDetachedProofChecker(registry).check(
        reference=reference,
        variable_count=13,
        clauses=clauses,
        subject_digest=digest,
    )
    assert result.accepted
    assert result.witness is not None
    assert result.witness.details["streaming"] is True
    assert result.witness.details["proof_steps_materialized"] is False
    assert result.witness.details["artifact_sha256"] == reference.artifact_sha256


def test_streaming_drat_checks_non_vacuous_rat(tmp_path: Path):
    clauses = ((1, 2), (1, 3), (1, -2), (2, -1), (-1, -2))
    digest = cnf_digest(13, clauses)
    registry, reference = _registry(
        tmp_path,
        DRAT_PROOF_FORMAT,
        digest,
        [
            {"op": "add", "clause": [-3]},
            {"op": "add", "clause": []},
        ],
    )
    result = StreamingDetachedProofChecker(registry).check(
        reference=reference,
        variable_count=13,
        clauses=clauses,
        subject_digest=digest,
    )
    assert result.accepted
    assert result.witness is not None
    assert result.witness.details["rat_additions"] == 1
    assert result.witness.details["rat_resolvents_checked"] >= 1


def test_streaming_drat_applies_deletion_to_proof_state_only(tmp_path: Path):
    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)
    registry, reference = _registry(
        tmp_path,
        DRAT_PROOF_FORMAT,
        digest,
        [
            {"op": "add", "clause": [2]},
            {"op": "delete", "clause": [2]},
            {"op": "add", "clause": []},
        ],
    )
    result = StreamingDetachedProofChecker(registry).check(
        reference=reference,
        variable_count=13,
        clauses=clauses,
        subject_digest=digest,
    )
    assert result.accepted
    assert result.witness.details["deletions"] == 1
    assert clauses == ((1,), (-1,))


def test_streaming_checker_rejects_wrong_header_binding(tmp_path: Path):
    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)
    store = LocalContentAddressedProofStore(tmp_path, store_id="proofs")
    data = _bytes(RUP_PROOF_FORMAT, "0" * 64, [{"op": "add", "clause": []}])
    reference = store.put_bytes(data, proof_format=RUP_PROOF_FORMAT, cnf_digest=digest)
    registry = ProofArtifactStoreRegistry(); registry.register(store)
    result = StreamingDetachedProofChecker(registry).check(
        reference=reference, variable_count=13, clauses=clauses, subject_digest=digest
    )
    assert not result.accepted
    assert result.diagnostics == ("detached_proof_header_cnf_digest_mismatch",)


def test_streaming_resource_limit_is_not_proof_acceptance(tmp_path: Path):
    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)
    registry, reference = _registry(tmp_path, RUP_PROOF_FORMAT, digest, [{"op": "add", "clause": []}])
    result = StreamingDetachedProofChecker(
        registry,
        limits=StreamingProofCheckLimits(max_artifact_bytes=8),
    ).check(reference=reference, variable_count=13, clauses=clauses, subject_digest=digest)
    assert not result.accepted
    assert result.diagnostics[0].startswith("detached_proof_artifact_error:")


def test_external_validation_promotes_valid_detached_large_unsat(tmp_path: Path):
    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)
    registry, reference = _registry(tmp_path, DRAT_PROOF_FORMAT, digest, [{"op": "add", "clause": []}])
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate=reference.to_dict(),
        variable_count=13,
        clauses=clauses,
        subject_digest=digest,
        independent_unsat_max_variables=12,
        proof_artifact_stores=registry,
    )
    assert result.certificate_accepted
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE
    assert result.witness is not None
    assert result.witness.details["artifact_sha256"] == reference.artifact_sha256


def test_external_validation_without_registered_store_stays_observed(tmp_path: Path):
    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)
    _, reference = _registry(tmp_path, RUP_PROOF_FORMAT, digest, [{"op": "add", "clause": []}])
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate=reference.to_dict(),
        variable_count=13,
        clauses=clauses,
        subject_digest=digest,
        independent_unsat_max_variables=12,
    )
    assert not result.certificate_accepted
    assert result.evidence_state == VerificationStatus.OBSERVED
    assert result.completeness == ValidationCompleteness.PARTIAL
    assert "detached_unsat_proof_store_registry_not_configured" in result.diagnostics


def test_reference_metadata_tamper_cannot_select_arbitrary_path(tmp_path: Path):
    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)
    registry, reference = _registry(tmp_path, RUP_PROOF_FORMAT, digest, [{"op": "add", "clause": []}])
    payload = reference.to_dict()
    payload["path"] = "/etc/passwd"
    result = validate_external_cnf_certificate(
        verdict="unsat",
        certificate=payload,
        variable_count=13,
        clauses=clauses,
        subject_digest=digest,
        independent_unsat_max_variables=12,
        proof_artifact_stores=registry,
    )
    assert result.evidence_state == VerificationStatus.OBSERVED
    assert result.diagnostics[0].startswith("invalid_detached_unsat_proof_reference:")

"""Deterministic artifact-integrity verifier."""

from __future__ import annotations

import hashlib

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationContext, VerificationDecision

from .adapter import HighAssuranceAdapterDescriptor
from .models import (
    AssuranceMechanism,
    ContainmentMode,
    HighAssuranceRequest,
    HighAssuranceResult,
    ValidationCompleteness,
    ValidationEnvelope,
    VerificationWitness,
    WitnessKind,
)


ARTIFACT_DIGEST_OBLIGATION = "artifact_digest_match"


class ArtifactDigestAdapter:
    descriptor = HighAssuranceAdapterDescriptor(
        adapter_id="artifact-digest-integrity",
        version="1.0.0",
        supported_obligation_types=(ARTIFACT_DIGEST_OBLIGATION,),
        mechanism=AssuranceMechanism.ARTIFACT_INTEGRITY,
        containment_mode=ContainmentMode.IN_PROCESS_READ_ONLY,
        maximum_evidence_state=VerificationStatus.VALIDATED,
        deterministic=True,
        side_effect_free=True,
        requires_network=False,
        produces_witness=True,
    )

    def execute(
        self,
        request: HighAssuranceRequest,
        context: VerificationContext,
    ) -> HighAssuranceResult:
        content = request.parameters.get("content")
        expected = request.parameters.get("expected_sha256")
        if not isinstance(content, str):
            raise ValueError("artifact_digest_match requires string content.")
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("expected_sha256 must be a 64-character hexadecimal digest.")
        try:
            int(expected, 16)
        except ValueError as exc:
            raise ValueError("expected_sha256 must be hexadecimal.") from exc
        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        envelope = ValidationEnvelope.create(
            subject_digest=actual,
            tool_id="sha256-integrity",
            tool_version="1.0.0",
            checked_scope=("utf8_content_sha256",),
            assumptions=("content string is the complete artifact representation under audit",),
            excluded_scope=("artifact semantics", "external storage integrity before content acquisition"),
            completeness=ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE,
            environment={"digest_algorithm": "sha256", "text_encoding": "utf-8"},
        )
        witness = VerificationWitness.create(
            kind=WitnessKind.INTEGRITY_DIGEST,
            subject_digest=actual,
            summary="Computed SHA-256 digest for the provided artifact representation.",
            reproducible=True,
            details={"actual_sha256": actual, "expected_sha256": expected.lower()},
        )
        return HighAssuranceResult.create(
            request=request,
            adapter_version=self.descriptor.version,
            decision=(
                VerificationDecision.CONFIRMED
                if actual == expected.lower()
                else VerificationDecision.REFUTED
            ),
            evidence_state=VerificationStatus.VALIDATED,
            validation_envelope=envelope,
            witnesses=(witness,),
        )

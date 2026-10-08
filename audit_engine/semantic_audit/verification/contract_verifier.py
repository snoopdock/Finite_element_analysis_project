
"""Deterministic verification of explicit semantic observation contracts."""

from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus

from .models import VerificationAttempt, VerificationContext, VerificationDecision
from .verifier import VerifierDescriptor


class ObservationContractVerifier:
    """Verify an explicit expected subject/predicate/object observation pattern.

    This verifier confirms or refutes only the stated observation contract. It
    does not infer architectural or scientific policy from graph structure.
    """

    descriptor = VerifierDescriptor(
        verifier_id="observation-contract",
        version="1.0.0",
        supported_obligation_types=("observation_contract",),
    )

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        observations = context.selected_observations(obligation)
        expected = {
            key: obligation.parameters.get(key)
            for key in ("subject_id", "predicate", "object_id")
            if obligation.parameters.get(key) is not None
        }
        if not expected or not observations:
            return VerificationAttempt.create(
                obligation_id=obligation.obligation_id,
                verifier_id=self.descriptor.verifier_id,
                verifier_version=self.descriptor.version,
                decision=VerificationDecision.INCONCLUSIVE,
                evidence_state=VerificationStatus.INCONCLUSIVE,
                evidence_ids=obligation.evidence_ids,
                details={"expected": expected, "matched_observation_ids": []},
            )

        matches = []
        for observation in observations:
            actual = {
                "subject_id": observation.subject_id,
                "predicate": observation.predicate,
                "object_id": observation.object_id,
            }
            if all(actual[key] == str(value) for key, value in expected.items()):
                matches.append(observation.observation_id)

        if matches:
            decision = VerificationDecision.CONFIRMED
            state = VerificationStatus.VALIDATED
        else:
            decision = VerificationDecision.REFUTED
            state = VerificationStatus.VALIDATED

        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=decision,
            evidence_state=state,
            evidence_ids=obligation.evidence_ids,
            details={
                "expected": expected,
                "matched_observation_ids": sorted(matches),
            },
        )

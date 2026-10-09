"""Verifier orchestration profile catalog and built-in profile declarations."""

from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.registry import VerifierRegistry

from .models import ExecutionMode, VerifierOrchestrationProfile, VerificationMethod


class VerifierProfileCatalog:
    def __init__(self) -> None:
        self._profiles: dict[str, VerifierOrchestrationProfile] = {}

    def register(self, profile: VerifierOrchestrationProfile) -> None:
        if profile.verifier_id in self._profiles:
            raise ValueError(f"Verifier orchestration profile already registered: {profile.verifier_id}")
        self._profiles[profile.verifier_id] = profile

    def get(self, verifier_id: str) -> VerifierOrchestrationProfile | None:
        return self._profiles.get(verifier_id)

    def validate_against_registry(self, registry: VerifierRegistry) -> None:
        for verifier_id, profile in self._profiles.items():
            verifier = registry.get(verifier_id)
            if verifier is None:
                # Catalogs may contain profiles for verifiers that are not active
                # in a particular registry. Only active verifier/profile pairs
                # participate in planning and require version agreement.
                continue
            if verifier.descriptor.version != profile.verifier_version:
                raise ValueError(
                    f"Profile version mismatch for {verifier_id}: "
                    f"profile={profile.verifier_version}, verifier={verifier.descriptor.version}"
                )

    def profiles(self) -> tuple[VerifierOrchestrationProfile, ...]:
        """Return a deterministic read-only view of registered profiles."""
        return tuple(self._profiles[key] for key in sorted(self._profiles))

    def __len__(self) -> int:
        return len(self._profiles)


def builtin_profile_catalog() -> VerifierProfileCatalog:
    """Profiles for the deterministic G3.1 verifier implementations.

    Cost units are deliberately small relative policy units and are versioned by
    the orchestration policy. They are not wall-clock measurements.
    """

    catalog = VerifierProfileCatalog()
    profiles = (
        VerifierOrchestrationProfile(
            "observation-contract", "1.0.0", VerificationMethod.CONTRACT, 1,
            VerificationStatus.VALIDATED,
        ),
        VerifierOrchestrationProfile(
            "evidence-corroboration", "1.0.0", VerificationMethod.CORROBORATION, 2,
            VerificationStatus.CORROBORATED,
        ),
        VerifierOrchestrationProfile(
            "graph-attribute-constraint", "1.0.0", VerificationMethod.GRAPH_CONSTRAINT, 2,
            VerificationStatus.VALIDATED,
        ),
        VerifierOrchestrationProfile(
            "required-relationship", "1.0.0", VerificationMethod.GRAPH_CONSTRAINT, 2,
            VerificationStatus.VALIDATED,
        ),
        VerifierOrchestrationProfile(
            "provenance-completeness", "1.0.0", VerificationMethod.PROVENANCE, 2,
            VerificationStatus.VALIDATED,
        ),
    )
    for profile in profiles:
        catalog.register(profile)
    return catalog

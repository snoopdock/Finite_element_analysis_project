
"""Deterministic verifier registry."""

from __future__ import annotations

from .models import VerificationObligation
from .verifier import Verifier


class VerifierRegistry:
    def __init__(self) -> None:
        self._verifiers: dict[str, Verifier] = {}

    def register(self, verifier: Verifier) -> None:
        descriptor = verifier.descriptor
        if descriptor.verifier_id in self._verifiers:
            raise ValueError(f"Verifier already registered: {descriptor.verifier_id}")
        self._verifiers[descriptor.verifier_id] = verifier

    def get(self, verifier_id: str) -> Verifier | None:
        return self._verifiers.get(verifier_id)

    def compatible(self, obligation: VerificationObligation) -> tuple[Verifier, ...]:
        """Return compatible verifiers without selecting semantic authority.

        Requested verifier restrictions remain authoritative. The orchestration
        layer may rank this deterministic candidate set using separate resource
        profiles, but the registry itself never reasons about cost or priority.
        """
        requested = obligation.requested_verifier_ids
        if requested:
            missing = [value for value in requested if value not in self._verifiers]
            if missing:
                raise LookupError(
                    "Requested verifier(s) are not registered: " + ", ".join(missing)
                )
        candidates = (
            [self._verifiers[value] for value in requested]
            if requested
            else [self._verifiers[key] for key in sorted(self._verifiers)]
        )
        return tuple(
            verifier
            for verifier in candidates
            if obligation.obligation_type in verifier.descriptor.supported_obligation_types
        )

    def resolve(self, obligation: VerificationObligation) -> Verifier:
        candidates = self.compatible(obligation)
        if candidates:
            return candidates[0]
        raise LookupError(
            f"No registered verifier supports obligation type {obligation.obligation_type!r}."
        )

    def __len__(self) -> int:
        return len(self._verifiers)

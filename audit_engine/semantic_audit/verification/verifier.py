
"""Verifier interface and capability descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .models import VerificationAttempt, VerificationContext, VerificationObligation


@dataclass(frozen=True)
class VerifierDescriptor:
    verifier_id: str
    version: str
    supported_obligation_types: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.verifier_id.strip():
            raise ValueError("verifier_id must be non-empty.")
        if not self.version.strip():
            raise ValueError("verifier version must be non-empty.")
        if not self.supported_obligation_types:
            raise ValueError("A verifier must declare at least one supported obligation type.")


@runtime_checkable
class Verifier(Protocol):
    @property
    def descriptor(self) -> VerifierDescriptor:
        ...

    def verify(
        self,
        obligation: VerificationObligation,
        context: VerificationContext,
    ) -> VerificationAttempt:
        ...

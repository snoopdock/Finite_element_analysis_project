"""Adapter contracts for bounded high-assurance verification mechanisms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationContext

from .models import AssuranceMechanism, ContainmentMode, HighAssuranceRequest, HighAssuranceResult


@dataclass(frozen=True)
class HighAssuranceAdapterDescriptor:
    adapter_id: str
    version: str
    supported_obligation_types: tuple[str, ...]
    mechanism: AssuranceMechanism
    containment_mode: ContainmentMode
    maximum_evidence_state: VerificationStatus
    deterministic: bool = True
    side_effect_free: bool = True
    requires_network: bool = False
    produces_witness: bool = True

    def __post_init__(self) -> None:
        if not self.adapter_id.strip() or not self.version.strip():
            raise ValueError("adapter_id and version must be non-empty.")
        if not self.supported_obligation_types:
            raise ValueError("High-assurance adapters must declare supported obligation types.")
        if self.maximum_evidence_state not in {
            VerificationStatus.OBSERVED,
            VerificationStatus.CORROBORATED,
            VerificationStatus.VALIDATED,
        }:
            raise ValueError("maximum_evidence_state must be an affirmative evidence state.")


@runtime_checkable
class HighAssuranceAdapter(Protocol):
    @property
    def descriptor(self) -> HighAssuranceAdapterDescriptor:
        ...

    def execute(
        self,
        request: HighAssuranceRequest,
        context: VerificationContext,
    ) -> HighAssuranceResult:
        ...

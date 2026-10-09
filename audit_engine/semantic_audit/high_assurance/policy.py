"""Execution policy for controlled high-assurance adapters."""

from __future__ import annotations

from dataclasses import dataclass

from .adapter import HighAssuranceAdapterDescriptor
from .models import AssuranceMechanism, ContainmentMode, HighAssuranceRequest


HIGH_ASSURANCE_POLICY_VERSION = "controlled_high_assurance_policy/v2"


@dataclass(frozen=True)
class HighAssurancePolicy:
    policy_version: str = HIGH_ASSURANCE_POLICY_VERSION
    allowed_mechanisms: tuple[AssuranceMechanism, ...] = (
        AssuranceMechanism.STATIC_ANALYSIS,
        AssuranceMechanism.ARTIFACT_INTEGRITY,
    )
    allowed_containment_modes: tuple[ContainmentMode, ...] = (
        ContainmentMode.IN_PROCESS_READ_ONLY,
    )
    max_timeout_ms: int = 5000
    allow_network: bool = False
    allow_side_effects: bool = False
    require_witness_for_validated: bool = True
    require_exhaustive_envelope_for_validated: bool = True
    explicit_activation_required: tuple[AssuranceMechanism, ...] = (
        AssuranceMechanism.SOLVER,
        AssuranceMechanism.EXECUTABLE_WITNESS,
        AssuranceMechanism.THEOREM_PROVER,
    )
    activated_adapter_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty.")
        if self.max_timeout_ms < 1:
            raise ValueError("max_timeout_ms must be at least 1.")

    def denial_reason(
        self,
        request: HighAssuranceRequest,
        descriptor: HighAssuranceAdapterDescriptor,
    ) -> str | None:
        if request.mechanism != descriptor.mechanism:
            return "request_mechanism_does_not_match_adapter"
        if descriptor.mechanism not in self.allowed_mechanisms:
            return "mechanism_not_allowed"
        if (
            descriptor.mechanism in self.explicit_activation_required
            and descriptor.adapter_id not in self.activated_adapter_ids
        ):
            return "adapter_not_explicitly_activated"
        if descriptor.containment_mode not in self.allowed_containment_modes:
            return "containment_mode_not_allowed"
        if descriptor.requires_network and not self.allow_network:
            return "network_access_not_allowed"
        if not descriptor.side_effect_free and not self.allow_side_effects:
            return "side_effecting_adapter_not_allowed"
        if request.timeout_ms > self.max_timeout_ms:
            return "timeout_exceeds_policy_limit"
        return None

"""Controlled registry-backed executable witnesses for G3.4.1.

No source string, import path, shell command, or arbitrary executable may be
supplied by an audit artifact.  A witness can execute only a callable that was
pre-registered by trusted application code under a stable descriptor.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Mapping

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


REGISTERED_EXECUTABLE_WITNESS_OBLIGATION = "registered_executable_witness"
REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID = "registered-executable-witness"
REGISTERED_EXECUTABLE_WITNESS_ADAPTER_VERSION = "1.0.0"


def _canonical_json_digest(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Executable witness inputs and outputs must be JSON-serializable.") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutableHarnessDescriptor:
    harness_id: str
    version: str
    deterministic: bool = True
    side_effect_free: bool = True
    requires_network: bool = False

    def __post_init__(self) -> None:
        if not self.harness_id.strip() or not self.version.strip():
            raise ValueError("harness_id and version must be non-empty.")
        if not self.deterministic:
            raise ValueError("G3.4.1 executable witness harnesses must be deterministic.")
        if not self.side_effect_free:
            raise ValueError("G3.4.1 executable witness harnesses must be declared side-effect-free.")
        if self.requires_network:
            raise ValueError("G3.4.1 executable witness harnesses may not require network access.")


@dataclass(frozen=True)
class RegisteredExecutableHarness:
    descriptor: ExecutableHarnessDescriptor
    function: Callable[[Mapping[str, Any]], Any]


class ExecutableHarnessRegistry:
    def __init__(self) -> None:
        self._harnesses: dict[str, RegisteredExecutableHarness] = {}

    def register(self, harness: RegisteredExecutableHarness) -> None:
        harness_id = harness.descriptor.harness_id
        if harness_id in self._harnesses:
            raise ValueError(f"Executable harness already registered: {harness_id}")
        self._harnesses[harness_id] = harness

    def require(self, harness_id: str) -> RegisteredExecutableHarness:
        try:
            return self._harnesses[harness_id]
        except KeyError as exc:
            raise KeyError(f"Unknown executable witness harness: {harness_id}") from exc

    def harnesses(self) -> tuple[RegisteredExecutableHarness, ...]:
        return tuple(self._harnesses[key] for key in sorted(self._harnesses))


class RegisteredExecutableWitnessAdapter:
    """Execute only pre-registered deterministic read-only witness harnesses."""

    descriptor = HighAssuranceAdapterDescriptor(
        adapter_id=REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
        version=REGISTERED_EXECUTABLE_WITNESS_ADAPTER_VERSION,
        supported_obligation_types=(REGISTERED_EXECUTABLE_WITNESS_OBLIGATION,),
        mechanism=AssuranceMechanism.EXECUTABLE_WITNESS,
        containment_mode=ContainmentMode.IN_PROCESS_READ_ONLY,
        maximum_evidence_state=VerificationStatus.VALIDATED,
        deterministic=True,
        side_effect_free=True,
        requires_network=False,
        produces_witness=True,
    )

    def __init__(self, harness_registry: ExecutableHarnessRegistry) -> None:
        self.harness_registry = harness_registry

    def execute(
        self,
        request: HighAssuranceRequest,
        context: VerificationContext,
    ) -> HighAssuranceResult:
        harness_id = request.parameters.get("harness_id")
        expected_version = request.parameters.get("harness_version")
        inputs = request.parameters.get("inputs")
        expected_output = request.parameters.get("expected_output")
        if not isinstance(harness_id, str) or not harness_id.strip():
            raise ValueError("registered_executable_witness requires harness_id.")
        if not isinstance(expected_version, str) or not expected_version.strip():
            raise ValueError("registered_executable_witness requires harness_version.")
        if not isinstance(inputs, Mapping):
            raise ValueError("registered_executable_witness inputs must be a mapping.")

        harness = self.harness_registry.require(harness_id)
        if harness.descriptor.version != expected_version:
            raise ValueError(
                f"Executable harness version mismatch: requested={expected_version}, "
                f"registered={harness.descriptor.version}"
            )

        input_digest = _canonical_json_digest(dict(inputs))
        expected_digest = _canonical_json_digest(expected_output)
        subject_digest = hashlib.sha256(
            f"{harness_id}:{expected_version}:{input_digest}:{expected_digest}".encode("utf-8")
        ).hexdigest()

        actual_output = harness.function(dict(inputs))
        actual_digest = _canonical_json_digest(actual_output)
        matched = actual_output == expected_output
        envelope = ValidationEnvelope.create(
            subject_digest=subject_digest,
            tool_id=f"registered-harness:{harness.descriptor.harness_id}",
            tool_version=harness.descriptor.version,
            checked_scope=(
                "single_registered_harness_execution",
                "exact_json_value_equality",
            ),
            assumptions=(
                "registered harness implementation corresponds to its declared harness identity and version",
                "provided input mapping represents the intended witness input",
            ),
            excluded_scope=(
                "unregistered callables",
                "arbitrary source execution",
                "shell commands",
                "network access",
                "behavior outside the supplied input",
            ),
            completeness=ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE,
            environment={
                "harness_id": harness.descriptor.harness_id,
                "harness_version": harness.descriptor.version,
                "input_digest": input_digest,
            },
        )
        witness = VerificationWitness.create(
            kind=WitnessKind.EXECUTION_TRACE,
            subject_digest=subject_digest,
            summary="Registered deterministic witness harness executed for one explicit input.",
            reproducible=True,
            details={
                "harness_id": harness.descriptor.harness_id,
                "harness_version": harness.descriptor.version,
                "input_digest": input_digest,
                "expected_output_digest": expected_digest,
                "actual_output_digest": actual_digest,
                "matched": matched,
            },
        )
        return HighAssuranceResult.create(
            request=request,
            adapter_version=self.descriptor.version,
            decision=VerificationDecision.CONFIRMED if matched else VerificationDecision.REFUTED,
            evidence_state=VerificationStatus.VALIDATED,
            validation_envelope=envelope,
            witnesses=(witness,),
        )

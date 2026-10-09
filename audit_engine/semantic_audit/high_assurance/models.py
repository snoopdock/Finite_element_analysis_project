"""Controlled high-assurance verification artifacts for G3.4.0.

These models describe *how* a strong verification was performed and what its
bounded validation envelope covers.  They do not create findings, mutate the
semantic graph, or assert correctness outside the declared scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationDecision


HIGH_ASSURANCE_REQUEST_SCHEMA_VERSION = "semantic_high_assurance_request/v1"
HIGH_ASSURANCE_RESULT_SCHEMA_VERSION = "semantic_high_assurance_result/v1"
HIGH_ASSURANCE_EXECUTION_SCHEMA_VERSION = "semantic_high_assurance_execution/v1"
VALIDATION_ENVELOPE_SCHEMA_VERSION = "semantic_validation_envelope/v1"
VERIFICATION_WITNESS_SCHEMA_VERSION = "semantic_verification_witness/v1"


class AssuranceMechanism(str, Enum):
    STATIC_ANALYSIS = "static_analysis"
    ARTIFACT_INTEGRITY = "artifact_integrity"
    SOLVER = "solver"
    EXECUTABLE_WITNESS = "executable_witness"
    THEOREM_PROVER = "theorem_prover"


class ContainmentMode(str, Enum):
    IN_PROCESS_READ_ONLY = "in_process_read_only"
    SANDBOXED_SUBPROCESS = "sandboxed_subprocess"
    CONTROLLED_EXTERNAL = "controlled_external"


class ValidationCompleteness(str, Enum):
    PARTIAL = "partial"
    EXHAUSTIVE_WITHIN_SCOPE = "exhaustive_within_scope"


class WitnessKind(str, Enum):
    STATIC_FACT = "static_fact"
    INTEGRITY_DIGEST = "integrity_digest"
    COUNTEREXAMPLE = "counterexample"
    SOLVER_CERTIFICATE = "solver_certificate"
    EXECUTION_TRACE = "execution_trace"
    FORMAL_PROOF = "formal_proof"


class HighAssuranceExecutionStatus(str, Enum):
    EXECUTED = "executed"
    DENIED = "denied"
    ADAPTER_ERROR = "adapter_error"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ValidationEnvelope:
    """Explicit scope/assumption boundary of a verification result."""

    envelope_id: str
    subject_digest: str
    tool_id: str
    tool_version: str
    checked_scope: tuple[str, ...]
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    excluded_scope: tuple[str, ...] = field(default_factory=tuple)
    completeness: ValidationCompleteness = ValidationCompleteness.PARTIAL
    environment: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = VALIDATION_ENVELOPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.subject_digest.strip():
            raise ValueError("subject_digest must be non-empty.")
        if not self.tool_id.strip() or not self.tool_version.strip():
            raise ValueError("tool identity and version must be non-empty.")
        if not self.checked_scope:
            raise ValueError("Validation envelopes must declare a non-empty checked_scope.")
        object.__setattr__(self, "environment", _freeze_mapping(self.environment))

    @classmethod
    def create(
        cls,
        *,
        subject_digest: str,
        tool_id: str,
        tool_version: str,
        checked_scope: Sequence[str],
        assumptions: Sequence[str] = (),
        excluded_scope: Sequence[str] = (),
        completeness: ValidationCompleteness = ValidationCompleteness.PARTIAL,
        environment: Mapping[str, Any] | None = None,
    ) -> "ValidationEnvelope":
        payload = {
            "subject_digest": subject_digest,
            "tool_id": tool_id,
            "tool_version": tool_version,
            "checked_scope": list(checked_scope),
            "assumptions": list(assumptions),
            "excluded_scope": list(excluded_scope),
            "completeness": completeness.value,
            "environment": dict(environment or {}),
        }
        return cls(
            envelope_id=deterministic_id("validation-envelope", payload, length=24),
            subject_digest=subject_digest,
            tool_id=tool_id,
            tool_version=tool_version,
            checked_scope=tuple(checked_scope),
            assumptions=tuple(assumptions),
            excluded_scope=tuple(excluded_scope),
            completeness=completeness,
            environment=dict(environment or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "envelope_id": self.envelope_id,
            "subject_digest": self.subject_digest,
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "checked_scope": list(self.checked_scope),
            "assumptions": list(self.assumptions),
            "excluded_scope": list(self.excluded_scope),
            "completeness": self.completeness.value,
            "environment": _jsonable(self.environment),
        }


@dataclass(frozen=True)
class VerificationWitness:
    witness_id: str
    kind: WitnessKind
    subject_digest: str
    summary: str
    reproducible: bool
    details: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = VERIFICATION_WITNESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.subject_digest.strip() or not self.summary.strip():
            raise ValueError("Witness subject_digest and summary must be non-empty.")
        object.__setattr__(self, "details", _freeze_mapping(self.details))

    @classmethod
    def create(
        cls,
        *,
        kind: WitnessKind,
        subject_digest: str,
        summary: str,
        reproducible: bool,
        details: Mapping[str, Any] | None = None,
    ) -> "VerificationWitness":
        payload = {
            "kind": kind.value,
            "subject_digest": subject_digest,
            "summary": summary,
            "reproducible": bool(reproducible),
            "details": dict(details or {}),
        }
        return cls(
            witness_id=deterministic_id("verification-witness", payload, length=24),
            kind=kind,
            subject_digest=subject_digest,
            summary=summary,
            reproducible=bool(reproducible),
            details=dict(details or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "witness_id": self.witness_id,
            "kind": self.kind.value,
            "subject_digest": self.subject_digest,
            "summary": self.summary,
            "reproducible": self.reproducible,
            "details": _jsonable(self.details),
        }


@dataclass(frozen=True)
class HighAssuranceRequest:
    request_id: str
    obligation_id: str
    adapter_id: str
    mechanism: AssuranceMechanism
    graph_fingerprint: str
    semantic_context_fingerprint: str
    timeout_ms: int
    parameters: Mapping[str, Any] = field(default_factory=dict, repr=False)
    parameter_digest: str = ""
    schema_version: str = HIGH_ASSURANCE_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.timeout_ms < 1:
            raise ValueError("timeout_ms must be at least 1.")
        if not self.obligation_id.strip() or not self.adapter_id.strip():
            raise ValueError("obligation_id and adapter_id must be non-empty.")
        frozen = _freeze_mapping(self.parameters)
        object.__setattr__(self, "parameters", frozen)
        expected = _sha256_json(dict(frozen))
        if self.parameter_digest and self.parameter_digest != expected:
            raise ValueError("parameter_digest does not match runtime parameters.")
        object.__setattr__(self, "parameter_digest", expected)

    @classmethod
    def create(
        cls,
        *,
        obligation_id: str,
        adapter_id: str,
        mechanism: AssuranceMechanism,
        graph_fingerprint: str,
        semantic_context_fingerprint: str,
        timeout_ms: int,
        parameters: Mapping[str, Any],
    ) -> "HighAssuranceRequest":
        parameter_digest = _sha256_json(parameters)
        payload = {
            "obligation_id": obligation_id,
            "adapter_id": adapter_id,
            "mechanism": mechanism.value,
            "graph_fingerprint": graph_fingerprint,
            "semantic_context_fingerprint": semantic_context_fingerprint,
            "timeout_ms": timeout_ms,
            "parameter_digest": parameter_digest,
        }
        return cls(
            request_id=deterministic_id("high-assurance-request", payload, length=24),
            obligation_id=obligation_id,
            adapter_id=adapter_id,
            mechanism=mechanism,
            graph_fingerprint=graph_fingerprint,
            semantic_context_fingerprint=semantic_context_fingerprint,
            timeout_ms=timeout_ms,
            parameters=dict(parameters),
            parameter_digest=parameter_digest,
        )

    def to_dict(self) -> dict[str, Any]:
        # Raw parameters may contain source code or other large/sensitive input.
        # Receipts preserve only their digest and names.
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "obligation_id": self.obligation_id,
            "adapter_id": self.adapter_id,
            "mechanism": self.mechanism.value,
            "graph_fingerprint": self.graph_fingerprint,
            "semantic_context_fingerprint": self.semantic_context_fingerprint,
            "timeout_ms": self.timeout_ms,
            "parameter_digest": self.parameter_digest,
            "parameter_keys": sorted(self.parameters),
        }


@dataclass(frozen=True)
class HighAssuranceResult:
    result_id: str
    request_id: str
    adapter_id: str
    adapter_version: str
    decision: VerificationDecision
    evidence_state: VerificationStatus
    validation_envelope: ValidationEnvelope
    witnesses: tuple[VerificationWitness, ...]
    diagnostics: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None
    schema_version: str = HIGH_ASSURANCE_RESULT_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        request: HighAssuranceRequest,
        adapter_version: str,
        decision: VerificationDecision,
        evidence_state: VerificationStatus,
        validation_envelope: ValidationEnvelope,
        witnesses: Sequence[VerificationWitness],
        diagnostics: Sequence[str] = (),
        error: str | None = None,
    ) -> "HighAssuranceResult":
        payload = {
            "request_id": request.request_id,
            "adapter_id": request.adapter_id,
            "adapter_version": adapter_version,
            "decision": decision.value,
            "evidence_state": evidence_state.value,
            "validation_envelope": validation_envelope.to_dict(),
            "witnesses": [item.to_dict() for item in witnesses],
            "diagnostics": list(diagnostics),
            "error": error,
        }
        return cls(
            result_id=deterministic_id("high-assurance-result", payload, length=24),
            request_id=request.request_id,
            adapter_id=request.adapter_id,
            adapter_version=adapter_version,
            decision=decision,
            evidence_state=evidence_state,
            validation_envelope=validation_envelope,
            witnesses=tuple(witnesses),
            diagnostics=tuple(diagnostics),
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "request_id": self.request_id,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "decision": self.decision.value,
            "evidence_state": self.evidence_state.value,
            "validation_envelope": self.validation_envelope.to_dict(),
            "witnesses": [item.to_dict() for item in self.witnesses],
            "diagnostics": list(self.diagnostics),
            "error": self.error,
        }


@dataclass(frozen=True)
class HighAssuranceExecutionRecord:
    execution_id: str
    request: HighAssuranceRequest
    policy_version: str
    status: HighAssuranceExecutionStatus
    result: HighAssuranceResult | None = None
    denial_reason: str | None = None
    schema_version: str = HIGH_ASSURANCE_EXECUTION_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        request: HighAssuranceRequest,
        policy_version: str,
        status: HighAssuranceExecutionStatus,
        result: HighAssuranceResult | None = None,
        denial_reason: str | None = None,
    ) -> "HighAssuranceExecutionRecord":
        payload = {
            "request": request.to_dict(),
            "policy_version": policy_version,
            "status": status.value,
            "result": result.to_dict() if result else None,
            "denial_reason": denial_reason,
        }
        return cls(
            execution_id=deterministic_id("high-assurance-execution", payload, length=24),
            request=request,
            policy_version=policy_version,
            status=status,
            result=result,
            denial_reason=denial_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "request": self.request.to_dict(),
            "policy_version": self.policy_version,
            "status": self.status.value,
            "result": self.result.to_dict() if self.result else None,
            "denial_reason": self.denial_reason,
        }

"""Strict JSON protocol models for controlled external solver responses."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


EXTERNAL_SOLVER_PROTOCOL_VERSION = "semantic_external_solver/v1"
_ALLOWED_RESPONSE_KEYS = {
    "protocol_version",
    "request_id",
    "input_digest",
    "solver_id",
    "solver_version",
    "verdict",
    "certificate",
    "diagnostics",
}
_ALLOWED_VERDICTS = {"sat", "unsat", "unknown"}


@dataclass(frozen=True)
class ExternalSolverResponse:
    protocol_version: str
    request_id: str
    input_digest: str
    solver_id: str
    solver_version: str
    verdict: str
    certificate: Mapping[str, Any] | None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.protocol_version != EXTERNAL_SOLVER_PROTOCOL_VERSION:
            raise ValueError("external solver protocol version mismatch")
        for field_name, value in (
            ("request_id", self.request_id),
            ("input_digest", self.input_digest),
            ("solver_id", self.solver_id),
            ("solver_version", self.solver_version),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.verdict not in _ALLOWED_VERDICTS:
            raise ValueError(f"unsupported external solver verdict: {self.verdict}")
        if self.certificate is not None:
            object.__setattr__(self, "certificate", MappingProxyType(dict(self.certificate)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExternalSolverResponse":
        unknown = set(payload) - _ALLOWED_RESPONSE_KEYS
        if unknown:
            raise ValueError(f"unknown external solver response fields: {sorted(unknown)}")
        required = {
            "protocol_version",
            "request_id",
            "input_digest",
            "solver_id",
            "solver_version",
            "verdict",
        }
        missing = required - set(payload)
        if missing:
            raise ValueError(f"missing external solver response fields: {sorted(missing)}")
        certificate = payload.get("certificate")
        if certificate is not None and not isinstance(certificate, Mapping):
            raise ValueError("external solver certificate must be an object or null")
        diagnostics = payload.get("diagnostics", ())
        if not isinstance(diagnostics, (list, tuple)) or not all(
            isinstance(item, str) for item in diagnostics
        ):
            raise ValueError("external solver diagnostics must be a sequence of strings")
        return cls(
            protocol_version=str(payload["protocol_version"]),
            request_id=str(payload["request_id"]),
            input_digest=str(payload["input_digest"]),
            solver_id=str(payload["solver_id"]),
            solver_version=str(payload["solver_version"]),
            verdict=str(payload["verdict"]),
            certificate=certificate,
            diagnostics=tuple(diagnostics),
        )

    def validate_binding(
        self,
        *,
        request_id: str,
        input_digest: str,
        solver_id: str,
        solver_version: str,
    ) -> None:
        if self.request_id != request_id:
            raise ValueError("external solver response is bound to a different request")
        if self.input_digest != input_digest:
            raise ValueError("external solver response input digest mismatch")
        if self.solver_id != solver_id or self.solver_version != solver_version:
            raise ValueError("external solver identity mismatch")

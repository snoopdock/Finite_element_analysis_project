from __future__ import annotations

import pytest

from audit_engine.semantic_audit.high_assurance.external_solver_protocol import (
    EXTERNAL_SOLVER_PROTOCOL_VERSION,
    ExternalSolverResponse,
)


def _payload():
    return {
        "protocol_version": EXTERNAL_SOLVER_PROTOCOL_VERSION,
        "request_id": "req-1",
        "input_digest": "digest-1",
        "solver_id": "solver-a",
        "solver_version": "1.2.3",
        "verdict": "sat",
        "certificate": {"kind": "sat_model", "assignment": {"1": True}},
        "diagnostics": [],
    }


def test_external_solver_protocol_rejects_unknown_fields():
    payload = _payload()
    payload["evidence_state"] = "validated"
    with pytest.raises(ValueError, match="unknown external solver response fields"):
        ExternalSolverResponse.from_mapping(payload)


def test_external_solver_protocol_rejects_unknown_verdict():
    payload = _payload()
    payload["verdict"] = "probably-sat"
    with pytest.raises(ValueError, match="unsupported external solver verdict"):
        ExternalSolverResponse.from_mapping(payload)


def test_external_solver_response_binding_is_exact():
    response = ExternalSolverResponse.from_mapping(_payload())
    with pytest.raises(ValueError, match="input digest mismatch"):
        response.validate_binding(
            request_id="req-1",
            input_digest="other",
            solver_id="solver-a",
            solver_version="1.2.3",
        )


def test_external_solver_response_diagnostics_must_be_strings():
    payload = _payload()
    payload["diagnostics"] = [1]
    with pytest.raises(ValueError, match="sequence of strings"):
        ExternalSolverResponse.from_mapping(payload)

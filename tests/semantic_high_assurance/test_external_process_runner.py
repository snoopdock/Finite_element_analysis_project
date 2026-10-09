from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest

from audit_engine.semantic_audit.high_assurance.external_process import (
    ControlledJsonSubprocessRunner,
    ExternalProcessError,
    ExternalProcessRiskAcknowledgement,
    ExternalProcessSpec,
)


FIXTURE = (Path(__file__).parent / "fixtures" / "external_cnf_solver_fixture.py").resolve()


def _digest(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _runner(mode="solve", *, ack=True, digest=None, stdout_limit=256 * 1024):
    executable = Path(sys.executable).resolve()
    spec = ExternalProcessSpec(
        process_id="fixture-cnf-process",
        process_version="0.1.0",
        executable_path=str(executable),
        executable_sha256=digest or _digest(executable),
        arguments=(str(FIXTURE), mode),
    )
    acknowledgement = (
        ExternalProcessRiskAcknowledgement(True, True)
        if ack
        else ExternalProcessRiskAcknowledgement()
    )
    return ControlledJsonSubprocessRunner(
        spec,
        risk_acknowledgement=acknowledgement,
        max_stdout_bytes=stdout_limit,
    )


def _payload():
    return {
        "protocol_version": "semantic_external_solver/v1",
        "request_id": "request-1",
        "input_digest": "input-digest",
        "variable_count": 1,
        "clauses": [[1]],
    }


def test_external_process_requires_explicit_risk_acknowledgement():
    with pytest.raises(ExternalProcessError, match="network isolation"):
        _runner(ack=False).run(_payload(), timeout_ms=1000)


def test_external_process_verifies_executable_digest_before_run():
    with pytest.raises(ExternalProcessError, match="digest mismatch"):
        _runner(digest="0" * 64).run(_payload(), timeout_ms=1000)


def test_external_process_round_trip_records_digests_not_raw_payload():
    result = _runner().run(_payload(), timeout_ms=1000)
    assert result.payload["verdict"] == "sat"
    trace = result.transcript.to_dict()
    assert trace["shell_used"] is False
    assert trace["network_isolation_enforced"] is False
    assert trace["filesystem_isolation_enforced"] is False
    assert "clauses" not in str(trace)
    assert len(trace["stdout_sha256"]) == 64


def test_external_process_rejects_malformed_json():
    with pytest.raises(ExternalProcessError, match="JSON"):
        _runner("malformed").run(_payload(), timeout_ms=1000)


def test_external_process_timeout_is_explicit():
    with pytest.raises(ExternalProcessError, match="timeout"):
        _runner("sleep").run(_payload(), timeout_ms=25)


def test_external_process_enforces_configured_stdout_limit_after_capture():
    with pytest.raises(ExternalProcessError, match="stdout exceeds"):
        _runner("oversize", stdout_limit=1024).run(_payload(), timeout_ms=1000)


def test_external_process_spec_requires_absolute_executable_path():
    with pytest.raises(ValueError, match="absolute"):
        ExternalProcessSpec(
            "x", "1", "python", "0" * 64, arguments=(),
        )


def test_external_process_spec_rejects_invalid_digest():
    with pytest.raises(ValueError, match="SHA-256"):
        ExternalProcessSpec(
            "x", "1", str(Path(sys.executable).resolve()), "not-a-digest", arguments=(),
        )

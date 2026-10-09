from __future__ import annotations

import pytest

from audit_engine.semantic_audit.high_assurance import (
    AssuranceMechanism,
    HighAssuranceRequest,
    ValidationCompleteness,
    ValidationEnvelope,
    VerificationWitness,
    WitnessKind,
)


def test_validation_envelope_requires_scope():
    with pytest.raises(ValueError, match="checked_scope"):
        ValidationEnvelope.create(
            subject_digest="abc", tool_id="x", tool_version="1", checked_scope=()
        )


def test_validation_envelope_identity_is_deterministic():
    kwargs = dict(
        subject_digest="abc",
        tool_id="tool",
        tool_version="1",
        checked_scope=("scope",),
        assumptions=("a",),
        excluded_scope=("b",),
        completeness=ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE,
    )
    assert ValidationEnvelope.create(**kwargs).envelope_id == ValidationEnvelope.create(**kwargs).envelope_id


def test_witness_identity_is_deterministic():
    one = VerificationWitness.create(
        kind=WitnessKind.STATIC_FACT,
        subject_digest="abc",
        summary="fact",
        reproducible=True,
        details={"x": 1},
    )
    two = VerificationWitness.create(
        kind=WitnessKind.STATIC_FACT,
        subject_digest="abc",
        summary="fact",
        reproducible=True,
        details={"x": 1},
    )
    assert one.witness_id == two.witness_id


def test_request_hides_raw_runtime_parameters_from_serialization():
    request = HighAssuranceRequest.create(
        obligation_id="obl",
        adapter_id="adapter",
        mechanism=AssuranceMechanism.STATIC_ANALYSIS,
        graph_fingerprint="graph",
        semantic_context_fingerprint="context",
        timeout_ms=100,
        parameters={"source_text": "SECRET SOURCE", "forbidden_modules": ["x"]},
    )
    payload = request.to_dict()
    assert "SECRET SOURCE" not in str(payload)
    assert payload["parameter_keys"] == ["forbidden_modules", "source_text"]
    assert len(payload["parameter_digest"]) == 64


def test_request_identity_changes_when_runtime_parameters_change():
    base = dict(
        obligation_id="obl", adapter_id="adapter", mechanism=AssuranceMechanism.STATIC_ANALYSIS,
        graph_fingerprint="g", semantic_context_fingerprint="c", timeout_ms=100,
    )
    one = HighAssuranceRequest.create(**base, parameters={"source_text": "a"})
    two = HighAssuranceRequest.create(**base, parameters={"source_text": "b"})
    assert one.request_id != two.request_id

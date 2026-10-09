from __future__ import annotations

import pytest

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import (
    AssuranceMechanism,
    ControlledHighAssuranceExecutor,
    ExecutableHarnessDescriptor,
    ExecutableHarnessRegistry,
    HighAssuranceAdapterRegistry,
    HighAssurancePolicy,
    REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    REGISTERED_EXECUTABLE_WITNESS_OBLIGATION,
    RegisteredExecutableHarness,
    RegisteredExecutableWitnessAdapter,
    WitnessKind,
)
from audit_engine.semantic_audit.verification.models import (
    VerificationContext,
    VerificationDecision,
    VerificationObligation,
)


def _harness_registry():
    registry = ExecutableHarnessRegistry()
    registry.register(
        RegisteredExecutableHarness(
            ExecutableHarnessDescriptor("sum-two", "1.0.0"),
            lambda inputs: inputs["a"] + inputs["b"],
        )
    )
    return registry


def _obligation(analysis_result, *, expected_output=5, version="1.0.0", harness_id="sum-two"):
    return VerificationObligation.from_analysis_result(
        analysis_result,
        obligation_type=REGISTERED_EXECUTABLE_WITNESS_OBLIGATION,
        requested_verifier_ids=(REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,),
        parameters={
            "harness_id": harness_id,
            "harness_version": version,
            "inputs": {"a": 2, "b": 3},
            "expected_output": expected_output,
            "timeout_ms": 1000,
        },
    )


def _executor():
    adapters = HighAssuranceAdapterRegistry()
    adapters.register(RegisteredExecutableWitnessAdapter(_harness_registry()))
    policy = HighAssurancePolicy(
        allowed_mechanisms=(
            AssuranceMechanism.STATIC_ANALYSIS,
            AssuranceMechanism.ARTIFACT_INTEGRITY,
            AssuranceMechanism.EXECUTABLE_WITNESS,
        ),
        activated_adapter_ids=(REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,),
    )
    return ControlledHighAssuranceExecutor(adapters, policy=policy)


def test_registered_harness_confirms_expected_output(analysis_result, semantic_graph):
    record = _executor().execute(
        _obligation(analysis_result),
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    )
    assert record.result is not None
    assert record.result.decision == VerificationDecision.CONFIRMED
    assert record.result.evidence_state == VerificationStatus.VALIDATED
    assert record.result.witnesses[0].kind == WitnessKind.EXECUTION_TRACE
    assert record.result.witnesses[0].details["matched"] is True


def test_registered_harness_refutes_wrong_output(analysis_result, semantic_graph):
    record = _executor().execute(
        _obligation(analysis_result, expected_output=6),
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    )
    assert record.result is not None
    assert record.result.decision == VerificationDecision.REFUTED


def test_unregistered_harness_is_adapter_error(analysis_result, semantic_graph):
    record = _executor().execute(
        _obligation(analysis_result, harness_id="not-registered"),
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    )
    assert record.status.value == "adapter_error"
    assert "Unknown executable witness harness" in (record.denial_reason or "")


def test_harness_version_mismatch_is_adapter_error(analysis_result, semantic_graph):
    record = _executor().execute(
        _obligation(analysis_result, version="2.0.0"),
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    )
    assert record.status.value == "adapter_error"
    assert "version mismatch" in (record.denial_reason or "")


def test_harness_registry_rejects_duplicate_identity():
    registry = _harness_registry()
    with pytest.raises(ValueError, match="already registered"):
        registry.register(
            RegisteredExecutableHarness(
                ExecutableHarnessDescriptor("sum-two", "1.0.0"),
                lambda inputs: 0,
            )
        )


def test_harness_descriptor_rejects_side_effecting_declaration():
    with pytest.raises(ValueError, match="side-effect-free"):
        ExecutableHarnessDescriptor("unsafe", "1", side_effect_free=False)


def test_harness_descriptor_rejects_network_requirement():
    with pytest.raises(ValueError, match="network"):
        ExecutableHarnessDescriptor("networked", "1", requires_network=True)


def test_execution_trace_serializes_digests_not_raw_inputs(analysis_result, semantic_graph):
    record = _executor().execute(
        _obligation(analysis_result),
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    )
    payload = record.to_dict()
    text = str(payload)
    assert "input_digest" in text
    assert "{'a': 2, 'b': 3}" not in text

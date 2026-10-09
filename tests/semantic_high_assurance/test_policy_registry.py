from __future__ import annotations

from dataclasses import replace

import pytest

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import (
    AssuranceMechanism,
    ContainmentMode,
    ControlledHighAssuranceExecutor,
    HighAssuranceAdapterDescriptor,
    HighAssuranceAdapterRegistry,
    HighAssurancePolicy,
    PythonStaticImportAdapter,
)
from audit_engine.semantic_audit.verification.models import VerificationContext

from .conftest import static_import_obligation


class NeverRunAdapter:
    def __init__(self, descriptor): self._descriptor = descriptor
    @property
    def descriptor(self): return self._descriptor
    def execute(self, request, context): raise AssertionError("denied adapter must not execute")


def descriptor(**kwargs):
    base = dict(
        adapter_id="restricted", version="1", supported_obligation_types=("python_static_import_constraint",),
        mechanism=AssuranceMechanism.STATIC_ANALYSIS, containment_mode=ContainmentMode.IN_PROCESS_READ_ONLY,
        maximum_evidence_state=VerificationStatus.VALIDATED, deterministic=True,
        side_effect_free=True, requires_network=False, produces_witness=True,
    )
    base.update(kwargs)
    return HighAssuranceAdapterDescriptor(**base)


def execute_restricted(analysis_result, semantic_graph, desc, policy=None):
    registry = HighAssuranceAdapterRegistry(); registry.register(NeverRunAdapter(desc))
    executor = ControlledHighAssuranceExecutor(registry, policy=policy)
    obligation = static_import_obligation(analysis_result, "import os\n")
    # Rebind requested verifier identity because helper requests the builtin.
    obligation = replace(obligation, requested_verifier_ids=(desc.adapter_id,))
    return executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id=desc.adapter_id)


def test_registry_rejects_duplicate_adapter():
    registry = HighAssuranceAdapterRegistry(); registry.register(PythonStaticImportAdapter())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(PythonStaticImportAdapter())


def test_policy_denies_network_adapter(analysis_result, semantic_graph):
    record = execute_restricted(analysis_result, semantic_graph, descriptor(requires_network=True))
    assert record.status.value == "denied"
    assert record.denial_reason == "network_access_not_allowed"


def test_policy_denies_side_effecting_adapter(analysis_result, semantic_graph):
    record = execute_restricted(analysis_result, semantic_graph, descriptor(side_effect_free=False))
    assert record.denial_reason == "side_effecting_adapter_not_allowed"


def test_policy_denies_sandbox_without_explicit_permission(analysis_result, semantic_graph):
    record = execute_restricted(
        analysis_result, semantic_graph,
        descriptor(containment_mode=ContainmentMode.SANDBOXED_SUBPROCESS),
    )
    assert record.denial_reason == "containment_mode_not_allowed"


def test_policy_denies_unapproved_mechanism(analysis_result, semantic_graph):
    record = execute_restricted(
        analysis_result, semantic_graph,
        descriptor(mechanism=AssuranceMechanism.SOLVER),
    )
    assert record.denial_reason == "mechanism_not_allowed"


def test_policy_denies_timeout_above_limit(analysis_result, semantic_graph):
    registry = HighAssuranceAdapterRegistry(); registry.register(PythonStaticImportAdapter())
    executor = ControlledHighAssuranceExecutor(registry, policy=HighAssurancePolicy(max_timeout_ms=100))
    obligation = static_import_obligation(analysis_result, "import os\n")
    obligation = replace(obligation, parameters={**obligation.parameters, "timeout_ms": 101})
    record = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="python-static-import")
    assert record.denial_reason == "timeout_exceeds_policy_limit"

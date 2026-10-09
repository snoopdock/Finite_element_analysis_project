"""Explicit construction helpers for the G3.4.0 built-in adapters."""

from __future__ import annotations

from audit_engine.semantic_audit.verification.registry import VerifierRegistry

from .execution import ControlledHighAssuranceExecutor
from .integrity import ArtifactDigestAdapter
from .policy import HighAssurancePolicy
from .registry import HighAssuranceAdapterRegistry
from .static_python import PythonStaticImportAdapter
from .verification_bridge import ControlledHighAssuranceVerifier


def builtin_high_assurance_adapter_registry() -> HighAssuranceAdapterRegistry:
    registry = HighAssuranceAdapterRegistry()
    registry.register(PythonStaticImportAdapter())
    registry.register(ArtifactDigestAdapter())
    return registry


def register_builtin_high_assurance_verifiers(
    verification_registry: VerifierRegistry,
    *,
    policy: HighAssurancePolicy | None = None,
) -> ControlledHighAssuranceExecutor:
    adapter_registry = builtin_high_assurance_adapter_registry()
    executor = ControlledHighAssuranceExecutor(adapter_registry, policy=policy)
    for adapter in adapter_registry.adapters():
        verification_registry.register(
            ControlledHighAssuranceVerifier(executor, adapter.descriptor.adapter_id)
        )
    return executor

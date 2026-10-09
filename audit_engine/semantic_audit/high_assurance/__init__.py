"""G3.4 controlled high-assurance verification foundation."""

from .adapter import HighAssuranceAdapter, HighAssuranceAdapterDescriptor
from .builtins import builtin_high_assurance_adapter_registry, register_builtin_high_assurance_verifiers
from .execution import ControlledHighAssuranceExecutor
from .integrity import ARTIFACT_DIGEST_OBLIGATION, ArtifactDigestAdapter
from .models import (
    AssuranceMechanism,
    ContainmentMode,
    HighAssuranceExecutionRecord,
    HighAssuranceExecutionStatus,
    HighAssuranceRequest,
    HighAssuranceResult,
    ValidationCompleteness,
    ValidationEnvelope,
    VerificationWitness,
    WitnessKind,
)
from .policy import HIGH_ASSURANCE_POLICY_VERSION, HighAssurancePolicy
from .registry import HighAssuranceAdapterRegistry
from .serialization import write_high_assurance_execution
from .static_python import PYTHON_STATIC_IMPORT_OBLIGATION, PythonStaticImportAdapter
from .verification_bridge import ControlledHighAssuranceVerifier

__all__ = [
    "ARTIFACT_DIGEST_OBLIGATION",
    "AssuranceMechanism",
    "ArtifactDigestAdapter",
    "ContainmentMode",
    "ControlledHighAssuranceExecutor",
    "ControlledHighAssuranceVerifier",
    "HIGH_ASSURANCE_POLICY_VERSION",
    "HighAssuranceAdapter",
    "HighAssuranceAdapterDescriptor",
    "HighAssuranceAdapterRegistry",
    "HighAssuranceExecutionRecord",
    "HighAssuranceExecutionStatus",
    "HighAssurancePolicy",
    "HighAssuranceRequest",
    "HighAssuranceResult",
    "PYTHON_STATIC_IMPORT_OBLIGATION",
    "PythonStaticImportAdapter",
    "ValidationCompleteness",
    "ValidationEnvelope",
    "VerificationWitness",
    "WitnessKind",
    "builtin_high_assurance_adapter_registry",
    "register_builtin_high_assurance_verifiers",
    "write_high_assurance_execution",
]

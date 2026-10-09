"""Controlled high-assurance verification architecture (G3.4.x)."""

from .adapter import HighAssuranceAdapter, HighAssuranceAdapterDescriptor
from .builtins import builtin_high_assurance_adapter_registry, register_builtin_high_assurance_verifiers
from .cnf_solver import (
    BOUNDED_CNF_ADAPTER_ID,
    BOUNDED_CNF_SAT_OBLIGATION,
    MAX_BOUNDED_CNF_VARIABLES,
    BoundedCnfSolverAdapter,
)
from .execution import ControlledHighAssuranceExecutor
from .executable_witness import (
    REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    REGISTERED_EXECUTABLE_WITNESS_OBLIGATION,
    ExecutableHarnessDescriptor,
    ExecutableHarnessRegistry,
    RegisteredExecutableHarness,
    RegisteredExecutableWitnessAdapter,
)
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
    "BOUNDED_CNF_ADAPTER_ID",
    "BOUNDED_CNF_SAT_OBLIGATION",
    "BoundedCnfSolverAdapter",
    "ContainmentMode",
    "ControlledHighAssuranceExecutor",
    "ControlledHighAssuranceVerifier",
    "ExecutableHarnessDescriptor",
    "ExecutableHarnessRegistry",
    "HIGH_ASSURANCE_POLICY_VERSION",
    "HighAssuranceAdapter",
    "HighAssuranceAdapterDescriptor",
    "HighAssuranceAdapterRegistry",
    "HighAssuranceExecutionRecord",
    "HighAssuranceExecutionStatus",
    "HighAssurancePolicy",
    "HighAssuranceRequest",
    "HighAssuranceResult",
    "MAX_BOUNDED_CNF_VARIABLES",
    "PYTHON_STATIC_IMPORT_OBLIGATION",
    "PythonStaticImportAdapter",
    "REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID",
    "REGISTERED_EXECUTABLE_WITNESS_OBLIGATION",
    "RegisteredExecutableHarness",
    "RegisteredExecutableWitnessAdapter",
    "ValidationCompleteness",
    "ValidationEnvelope",
    "VerificationWitness",
    "WitnessKind",
    "builtin_high_assurance_adapter_registry",
    "register_builtin_high_assurance_verifiers",
    "write_high_assurance_execution",
]

"""Controlled high-assurance verification architecture (G3.4.x)."""

from .adapter import HighAssuranceAdapter, HighAssuranceAdapterDescriptor
from .builtins import builtin_high_assurance_adapter_registry, register_builtin_high_assurance_verifiers
from .certificate_validation import (
    DEFAULT_INDEPENDENT_UNSAT_MAX_VARIABLES,
    SolverCertificateValidation,
    validate_external_cnf_certificate,
    validate_sat_model_certificate,
    validate_unsat_claim,
)
from .cnf_solver import (
    BOUNDED_CNF_ADAPTER_ID,
    BOUNDED_CNF_SAT_OBLIGATION,
    MAX_BOUNDED_CNF_VARIABLES,
    BoundedCnfSolverAdapter,
)
from .execution import ControlledHighAssuranceExecutor
from .drat_proof import (
    DRAT_CHECKER_ID,
    DRAT_CHECKER_VERSION,
    DRAT_PROOF_FORMAT,
    DratProofCheckLimits,
    DratUnsatProofChecker,
)
from .executable_witness import (
    REGISTERED_EXECUTABLE_WITNESS_ADAPTER_ID,
    REGISTERED_EXECUTABLE_WITNESS_OBLIGATION,
    ExecutableHarnessDescriptor,
    ExecutableHarnessRegistry,
    RegisteredExecutableHarness,
    RegisteredExecutableWitnessAdapter,
)
from .external_process import (
    EXTERNAL_JSON_PROCESS_PROTOCOL,
    ControlledJsonSubprocessRunner,
    ExternalJsonProcessResult,
    ExternalProcessError,
    ExternalProcessRiskAcknowledgement,
    ExternalProcessSpec,
    ExternalProcessTranscript,
)
from .external_solver import (
    CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    CONTROLLED_EXTERNAL_CNF_ADAPTER_VERSION,
    DEFAULT_EXTERNAL_CNF_MAX_VARIABLES,
    ControlledExternalCnfSolverAdapter,
)
from .external_solver_protocol import (
    EXTERNAL_SOLVER_PROTOCOL_VERSION,
    ExternalSolverResponse,
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
from .proof_artifact import (
    DETACHED_UNSAT_PROOF_KIND,
    PROOF_ARTIFACT_FORMAT,
    PROOF_ARTIFACT_MEDIA_TYPE,
    LocalContentAddressedProofStore,
    ProofArtifactError,
    ProofArtifactReference,
    ProofArtifactStoreRegistry,
)
from .streaming_proof import StreamingDetachedProofChecker, StreamingProofCheckLimits
from .policy import HIGH_ASSURANCE_POLICY_VERSION, HighAssurancePolicy
from .registry import HighAssuranceAdapterRegistry
from .serialization import write_high_assurance_execution
from .static_python import PYTHON_STATIC_IMPORT_OBLIGATION, PythonStaticImportAdapter
from .unsat_proof import (
    RUP_CHECKER_ID,
    RUP_CHECKER_VERSION,
    RUP_PROOF_FORMAT,
    ProofCheckLimits,
    RupUnsatProofChecker,
    UnsatProofCheckResult,
    UnsatProofCheckerDescriptor,
    UnsatProofCheckerRegistry,
    builtin_unsat_proof_checker_registry,
    clause_is_rup,
)
from .verification_bridge import ControlledHighAssuranceVerifier

__all__ = [
    "ARTIFACT_DIGEST_OBLIGATION",
    "CONTROLLED_EXTERNAL_CNF_ADAPTER_ID",
    "CONTROLLED_EXTERNAL_CNF_ADAPTER_VERSION",
    "ControlledExternalCnfSolverAdapter",
    "ControlledJsonSubprocessRunner",
    "DEFAULT_EXTERNAL_CNF_MAX_VARIABLES",
    "DEFAULT_INDEPENDENT_UNSAT_MAX_VARIABLES",
    "DRAT_CHECKER_ID",
    "DRAT_CHECKER_VERSION",
    "DRAT_PROOF_FORMAT",
    "DratProofCheckLimits",
    "DratUnsatProofChecker",
    "EXTERNAL_JSON_PROCESS_PROTOCOL",
    "EXTERNAL_SOLVER_PROTOCOL_VERSION",
    "ExternalJsonProcessResult",
    "ExternalProcessError",
    "ExternalProcessRiskAcknowledgement",
    "ExternalProcessSpec",
    "ExternalProcessTranscript",
    "ExternalSolverResponse",
    "SolverCertificateValidation",
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
    "validate_external_cnf_certificate",
    "validate_sat_model_certificate",
    "validate_unsat_claim",
    "ProofCheckLimits",
    "RUP_CHECKER_ID",
    "RUP_CHECKER_VERSION",
    "RUP_PROOF_FORMAT",
    "RupUnsatProofChecker",
    "UnsatProofCheckResult",
    "UnsatProofCheckerDescriptor",
    "UnsatProofCheckerRegistry",
    "builtin_unsat_proof_checker_registry",
    "clause_is_rup",
    "DETACHED_UNSAT_PROOF_KIND",
    "PROOF_ARTIFACT_FORMAT",
    "PROOF_ARTIFACT_MEDIA_TYPE",
    "LocalContentAddressedProofStore",
    "ProofArtifactError",
    "ProofArtifactReference",
    "ProofArtifactStoreRegistry",
    "StreamingDetachedProofChecker",
    "StreamingProofCheckLimits",
    "write_high_assurance_execution",
]

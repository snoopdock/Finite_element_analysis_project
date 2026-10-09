"""Controlled external CNF solver adapter with independent certificate validation.

The external process is a candidate evidence producer, never the authority that
marks its own output validated.  SAT models are checked clause-by-clause by
repository code.  Bounded UNSAT claims are independently re-solved by exhaustive
enumeration.  Larger UNSAT claims require a certificate accepted by an explicitly
registered repository-owned proof checker; otherwise they remain merely observed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationContext, VerificationDecision

from .adapter import HighAssuranceAdapterDescriptor
from .certificate_validation import (
    DEFAULT_INDEPENDENT_UNSAT_MAX_VARIABLES,
    validate_external_cnf_certificate,
)
from .cnf_solver import BOUNDED_CNF_SAT_OBLIGATION, cnf_digest, normalize_cnf
from .external_process import ControlledJsonSubprocessRunner
from .external_solver_protocol import EXTERNAL_SOLVER_PROTOCOL_VERSION, ExternalSolverResponse
from .proof_artifact import ProofArtifactStoreRegistry
from .streaming_proof import StreamingProofCheckLimits
from .unsat_proof import UnsatProofCheckerRegistry, builtin_unsat_proof_checker_registry
from .models import (
    AssuranceMechanism,
    ContainmentMode,
    HighAssuranceRequest,
    HighAssuranceResult,
    ValidationCompleteness,
    ValidationEnvelope,
    VerificationWitness,
    WitnessKind,
)


CONTROLLED_EXTERNAL_CNF_ADAPTER_ID = "controlled-external-cnf"
CONTROLLED_EXTERNAL_CNF_ADAPTER_VERSION = "1.0.0"
DEFAULT_EXTERNAL_CNF_MAX_VARIABLES = 100_000


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ControlledExternalCnfSolverAdapter:
    """Use one fixed external solver process through the controlled JSON boundary.

    ``side_effect_free=False`` is intentional: the Python process wrapper cannot
    prove that an arbitrary binary is side-effect free.  High-assurance policy
    must therefore explicitly permit controlled-external execution and side
    effects in addition to activating this adapter ID.
    """

    descriptor = HighAssuranceAdapterDescriptor(
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
        version=CONTROLLED_EXTERNAL_CNF_ADAPTER_VERSION,
        supported_obligation_types=(BOUNDED_CNF_SAT_OBLIGATION,),
        mechanism=AssuranceMechanism.SOLVER,
        containment_mode=ContainmentMode.CONTROLLED_EXTERNAL,
        maximum_evidence_state=VerificationStatus.VALIDATED,
        deterministic=False,
        side_effect_free=False,
        requires_network=False,
        produces_witness=True,
    )

    def __init__(
        self,
        runner: ControlledJsonSubprocessRunner,
        *,
        solver_id: str,
        solver_version: str,
        independent_unsat_max_variables: int = DEFAULT_INDEPENDENT_UNSAT_MAX_VARIABLES,
        max_variables: int = DEFAULT_EXTERNAL_CNF_MAX_VARIABLES,
        proof_checker_registry: UnsatProofCheckerRegistry | None = None,
        proof_artifact_stores: ProofArtifactStoreRegistry | None = None,
        streaming_proof_limits: StreamingProofCheckLimits | None = None,
    ) -> None:
        if not solver_id.strip() or not solver_version.strip():
            raise ValueError("solver_id and solver_version must be non-empty")
        if independent_unsat_max_variables < 1:
            raise ValueError("independent_unsat_max_variables must be positive")
        if max_variables < 1:
            raise ValueError("max_variables must be positive")
        self.runner = runner
        self.solver_id = solver_id
        self.solver_version = solver_version
        self.independent_unsat_max_variables = independent_unsat_max_variables
        self.max_variables = max_variables
        self.proof_checker_registry = proof_checker_registry or builtin_unsat_proof_checker_registry()
        self.proof_artifact_stores = proof_artifact_stores
        self.streaming_proof_limits = streaming_proof_limits

    def execute(
        self,
        request: HighAssuranceRequest,
        context: VerificationContext,
    ) -> HighAssuranceResult:
        raw_count = request.parameters.get("variable_count")
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            raise ValueError("variable_count must be an integer")
        if raw_count < 1 or raw_count > self.max_variables:
            raise ValueError(f"variable_count must be between 1 and {self.max_variables}")
        expected = request.parameters.get("expected_satisfiable")
        if not isinstance(expected, bool):
            raise ValueError("expected_satisfiable must be boolean")
        clauses = normalize_cnf(request.parameters.get("clauses"), raw_count)
        formula_digest = cnf_digest(raw_count, clauses)
        semantic_input = {
            "protocol_version": EXTERNAL_SOLVER_PROTOCOL_VERSION,
            "request_id": request.request_id,
            "obligation_type": BOUNDED_CNF_SAT_OBLIGATION,
            "variable_count": raw_count,
            "clauses": [list(clause) for clause in clauses],
        }
        input_digest = _sha256_json(semantic_input)
        semantic_input["input_digest"] = input_digest
        process_result = self.runner.run(semantic_input, timeout_ms=request.timeout_ms)
        response = ExternalSolverResponse.from_mapping(process_result.payload)
        response.validate_binding(
            request_id=request.request_id,
            input_digest=input_digest,
            solver_id=self.solver_id,
            solver_version=self.solver_version,
        )

        certificate_validation = validate_external_cnf_certificate(
            verdict=response.verdict,
            certificate=response.certificate,
            variable_count=raw_count,
            clauses=clauses,
            subject_digest=formula_digest,
            independent_unsat_max_variables=self.independent_unsat_max_variables,
            proof_checker_registry=self.proof_checker_registry,
            proof_artifact_stores=self.proof_artifact_stores,
            streaming_proof_limits=self.streaming_proof_limits,
        )
        if certificate_validation.established_verdict is None:
            decision = VerificationDecision.INCONCLUSIVE
        else:
            established_satisfiable = certificate_validation.established_verdict == "sat"
            decision = (
                VerificationDecision.CONFIRMED
                if established_satisfiable == expected
                else VerificationDecision.REFUTED
            )

        transcript_witness = VerificationWitness.create(
            kind=WitnessKind.EXECUTION_TRACE,
            subject_digest=formula_digest,
            summary="Controlled external solver process completed through the fixed JSON protocol.",
            reproducible=True,
            details={
                **process_result.transcript.to_dict(),
                "solver_id": self.solver_id,
                "solver_version": self.solver_version,
                "solver_protocol": EXTERNAL_SOLVER_PROTOCOL_VERSION,
                "semantic_input_digest": input_digest,
            },
        )
        witnesses = [transcript_witness]
        if certificate_validation.witness is not None:
            witnesses.append(certificate_validation.witness)

        completeness = certificate_validation.completeness
        envelope = ValidationEnvelope.create(
            subject_digest=formula_digest,
            tool_id=self.solver_id,
            tool_version=self.solver_version,
            checked_scope=(
                "propositional_boolean_cnf",
                "external_solver_protocol_response",
                "independent_certificate_validation",
            ),
            assumptions=(
                "clauses and variable_count completely encode the intended Boolean CNF instance",
                "registered executable digest identifies the invoked external process image",
            ),
            excluded_scope=(
                "SMT theories",
                "first-order logic",
                "optimization objectives",
                "network isolation by the Python process runner",
                "filesystem isolation outside the ephemeral working directory",
                "UNSAT proof formats without a repository-owned registered checker",
                "detached proof stores not explicitly registered by trusted application code",
            ),
            completeness=completeness,
            environment={
                "adapter_contract": "controlled_external_cnf/v1",
                "solver_protocol": EXTERNAL_SOLVER_PROTOCOL_VERSION,
                "solver_id": self.solver_id,
                "solver_version": self.solver_version,
                "external_process": process_result.transcript.to_dict(),
                "certificate_accepted": certificate_validation.certificate_accepted,
                "independent_unsat_max_variables": self.independent_unsat_max_variables,
                "registered_unsat_proof_formats": list(self.proof_checker_registry.formats()),
                "registered_proof_artifact_stores": (
                    list(self.proof_artifact_stores.ids()) if self.proof_artifact_stores is not None else []
                ),
            },
        )
        diagnostics = tuple(response.diagnostics) + certificate_validation.diagnostics
        return HighAssuranceResult.create(
            request=request,
            adapter_version=self.descriptor.version,
            decision=decision,
            evidence_state=certificate_validation.evidence_state,
            validation_envelope=envelope,
            witnesses=tuple(witnesses),
            diagnostics=diagnostics,
        )

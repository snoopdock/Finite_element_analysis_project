from __future__ import annotations

import json
from pathlib import Path

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import (
    AssuranceMechanism,
    CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    ContainmentMode,
    ControlledExternalCnfSolverAdapter,
    ControlledHighAssuranceExecutor,
    DRAT_PROOF_FORMAT,
    ExternalJsonProcessResult,
    ExternalProcessTranscript,
    HighAssuranceAdapterRegistry,
    HighAssurancePolicy,
    LocalContentAddressedProofStore,
    PROOF_ARTIFACT_FORMAT,
    ProofArtifactStoreRegistry,
    ValidationCompleteness,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import BOUNDED_CNF_SAT_OBLIGATION, cnf_digest, normalize_cnf
from audit_engine.semantic_audit.verification import VerificationContext, VerificationDecision, VerificationObligation


SOLVER_ID = "detached-fixture-solver"
SOLVER_VERSION = "1.0.0"


def _artifact_bytes(digest: str) -> bytes:
    rows = [
        {"artifact_format": PROOF_ARTIFACT_FORMAT, "proof_format": DRAT_PROOF_FORMAT, "cnf_digest": digest},
        {"op": "add", "clause": []},
    ]
    return b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode() for row in rows)


class DetachedReferenceRunner:
    def __init__(self, certificate):
        self.certificate = certificate

    def run(self, payload, *, timeout_ms):
        response = {
            "protocol_version": "semantic_external_solver/v1",
            "request_id": payload["request_id"],
            "input_digest": payload["input_digest"],
            "solver_id": SOLVER_ID,
            "solver_version": SOLVER_VERSION,
            "verdict": "unsat",
            "certificate": self.certificate,
            "diagnostics": [],
        }
        transcript = ExternalProcessTranscript(
            process_id="detached-fixture",
            process_version="1",
            executable_sha256="0" * 64,
            input_sha256="1" * 64,
            stdout_sha256="2" * 64,
            stderr_sha256="3" * 64,
            return_code=0,
            timeout_ms=timeout_ms,
            stdout_bytes=1,
            stderr_bytes=0,
        )
        return ExternalJsonProcessResult(response, transcript)


def test_external_solver_adapter_validates_registered_detached_proof(
    tmp_path: Path,
    analysis_result,
    semantic_graph,
):
    clauses = [[1], [-1]]
    digest = cnf_digest(13, normalize_cnf(clauses, 13))
    store = LocalContentAddressedProofStore(tmp_path, store_id="proofs")
    reference = store.put_bytes(_artifact_bytes(digest), proof_format=DRAT_PROOF_FORMAT, cnf_digest=digest)
    stores = ProofArtifactStoreRegistry(); stores.register(store)

    adapter = ControlledExternalCnfSolverAdapter(
        DetachedReferenceRunner(reference.to_dict()),
        solver_id=SOLVER_ID,
        solver_version=SOLVER_VERSION,
        independent_unsat_max_variables=12,
        proof_artifact_stores=stores,
    )
    registry = HighAssuranceAdapterRegistry(); registry.register(adapter)
    executor = ControlledHighAssuranceExecutor(
        registry,
        policy=HighAssurancePolicy(
            allowed_mechanisms=(AssuranceMechanism.SOLVER,),
            allowed_containment_modes=(ContainmentMode.CONTROLLED_EXTERNAL,),
            allow_side_effects=True,
            activated_adapter_ids=(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,),
        ),
    )
    obligation = VerificationObligation.from_analysis_result(
        analysis_result,
        obligation_type=BOUNDED_CNF_SAT_OBLIGATION,
        requested_verifier_ids=(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,),
        parameters={
            "variable_count": 13,
            "clauses": clauses,
            "expected_satisfiable": False,
            "timeout_ms": 1000,
        },
    )
    result = executor.execute(
        obligation,
        VerificationContext(analysis_result, semantic_graph),
        adapter_id=CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    ).result
    assert result.decision == VerificationDecision.CONFIRMED
    assert result.evidence_state == VerificationStatus.VALIDATED
    assert result.validation_envelope.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE
    assert result.validation_envelope.environment["registered_proof_artifact_stores"] == ("proofs",)
    proof_witness = [w for w in result.witnesses if w.kind.value == "formal_proof"][0]
    assert proof_witness.details["artifact_sha256"] == reference.artifact_sha256

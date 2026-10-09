#!/usr/bin/env python3
"""Deterministic G3.4.5 detached/streaming proof acceptance validator."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import (
    CONTROLLED_EXTERNAL_CNF_ADAPTER_ID,
    DRAT_PROOF_FORMAT,
    DETACHED_UNSAT_PROOF_KIND,
    LocalContentAddressedProofStore,
    PROOF_ARTIFACT_FORMAT,
    ProofArtifactReference,
    ProofArtifactStoreRegistry,
    RUP_PROOF_FORMAT,
    StreamingDetachedProofChecker,
    StreamingProofCheckLimits,
    ValidationCompleteness,
    builtin_high_assurance_adapter_registry,
    validate_external_cnf_certificate,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import cnf_digest

ARTIFACT = ROOT / "artifacts" / "semantic_detached_proof_artifact_validation.json"


def proof_bytes(proof_format: str, digest: str, steps) -> bytes:
    rows = [
        {"artifact_format": PROOF_ARTIFACT_FORMAT, "proof_format": proof_format, "cnf_digest": digest},
        *steps,
    ]
    return b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode() for row in rows)


def manual_workflows_05_19() -> bool:
    folder = ROOT / ".github" / "workflows"
    for number in range(5, 20):
        matches = list(folder.glob(f"{number:02d}_*.yml"))
        if len(matches) != 1:
            return False
        text = matches[0].read_text(encoding="utf-8")
        if "on:\n  workflow_dispatch:\n" not in text or "\n  push:" in text or "\n  pull_request:" in text:
            return False
    return True


def run() -> dict[str, object]:
    checks: dict[str, bool] = {}
    clauses = ((1,), (-1,))
    digest = cnf_digest(13, clauses)

    with tempfile.TemporaryDirectory(prefix="g345-proof-store-") as tmp:
        store = LocalContentAddressedProofStore(tmp, store_id="proofs")
        drat_ref = store.put_bytes(
            proof_bytes(DRAT_PROOF_FORMAT, digest, [{"op": "add", "clause": []}]),
            proof_format=DRAT_PROOF_FORMAT,
            cnf_digest=digest,
        )
        stores = ProofArtifactStoreRegistry(); stores.register(store)

        checked = StreamingDetachedProofChecker(stores).check(
            reference=drat_ref,
            variable_count=13,
            clauses=clauses,
            subject_digest=digest,
        )
        checks["detached_drat_stream_is_repository_checked"] = bool(
            checked.accepted
            and checked.witness is not None
            and checked.witness.details["streaming"] is True
            and checked.witness.details["proof_steps_materialized"] is False
        )
        checks["detached_witness_binds_artifact_digest"] = bool(
            checked.witness is not None
            and checked.witness.details["artifact_sha256"] == drat_ref.artifact_sha256
        )

        promoted = validate_external_cnf_certificate(
            verdict="unsat",
            certificate=drat_ref.to_dict(),
            variable_count=13,
            clauses=clauses,
            subject_digest=digest,
            independent_unsat_max_variables=12,
            proof_artifact_stores=stores,
        )
        checks["valid_detached_large_unsat_can_be_validated"] = (
            promoted.certificate_accepted
            and promoted.evidence_state == VerificationStatus.VALIDATED
            and promoted.completeness == ValidationCompleteness.CERTIFICATE_COMPLETE_WITHIN_SCOPE
        )

        no_store = validate_external_cnf_certificate(
            verdict="unsat",
            certificate=drat_ref.to_dict(),
            variable_count=13,
            clauses=clauses,
            subject_digest=digest,
            independent_unsat_max_variables=12,
        )
        checks["unregistered_store_does_not_promote_evidence"] = (
            not no_store.certificate_accepted
            and no_store.evidence_state == VerificationStatus.OBSERVED
        )

        limited = StreamingDetachedProofChecker(
            stores,
            limits=StreamingProofCheckLimits(max_artifact_bytes=8),
        ).check(reference=drat_ref, variable_count=13, clauses=clauses, subject_digest=digest)
        checks["artifact_resource_limit_is_epistemically_neutral"] = not limited.accepted

        payload = drat_ref.to_dict(); payload["path"] = "/tmp/untrusted"
        try:
            ProofArtifactReference.from_mapping(payload)
        except ValueError:
            checks["solver_cannot_supply_artifact_path"] = True
        else:
            checks["solver_cannot_supply_artifact_path"] = False

        rup_ref = store.put_bytes(
            proof_bytes(RUP_PROOF_FORMAT, digest, [{"op": "add", "clause": []}]),
            proof_format=RUP_PROOF_FORMAT,
            cnf_digest=digest,
        )
        checks["rup_and_drat_detached_formats_supported"] = all(
            StreamingDetachedProofChecker(stores).check(
                reference=ref,
                variable_count=13,
                clauses=clauses,
                subject_digest=digest,
            ).accepted
            for ref in (rup_ref, drat_ref)
        )
        checks["reference_kind_is_explicit"] = drat_ref.kind == DETACHED_UNSAT_PROOF_KIND

    checks["controlled_external_solver_still_not_default_active"] = (
        builtin_high_assurance_adapter_registry().get(CONTROLLED_EXTERNAL_CNF_ADAPTER_ID) is None
    )
    try:
        from formal.router import FormalRouter
        FormalRouter().route("existence", 1.0, 0.5)
    except NotImplementedError:
        checks["formal_router_remains_inactive"] = True
    else:
        checks["formal_router_remains_inactive"] = False

    for name in (
        "detached_proof_artifact_reference_contract.yaml",
        "content_addressed_proof_store_contract.yaml",
        "streaming_cnf_proof_checking_contract.yaml",
        "detached_unsat_proof_validation_contract.yaml",
    ):
        checks[f"contract_present:{name}"] = bool(
            yaml.safe_load((ROOT / "specs" / "contracts" / name).read_text(encoding="utf-8"))
        )
    for name in (
        "detached_proof_artifact_reference.schema.json",
        "streaming_cnf_proof_header.schema.json",
        "streaming_cnf_proof_step.schema.json",
    ):
        checks[f"schema_present:{name}"] = bool(
            json.loads((ROOT / "specs" / "schemas" / name).read_text(encoding="utf-8"))
        )

    workflow = (ROOT / ".github" / "workflows" / "19_semantic_detached_proof_artifact_validation.yml").read_text(encoding="utf-8")
    checks["workflow_19_manual_only"] = "on:\n  workflow_dispatch:\n" in workflow and "\n  push:" not in workflow
    checks["g3_workflows_05_19_manual_only"] = manual_workflows_05_19()

    result = {
        "milestone": "G3.4.5",
        "validator": "validate_semantic_detached_proof_artifacts.py",
        "passed": all(checks.values()),
        "checks": checks,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    payload = run()
    for name, passed in payload["checks"].items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if payload["passed"]:
        print("G3.4.5 detached/streaming proof artifact validation passed.")
        return 0
    print("G3.4.5 detached/streaming proof artifact validation failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

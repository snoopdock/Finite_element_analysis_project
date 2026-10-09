#!/usr/bin/env python3
"""Deterministic G3.4.4 repository-owned DRAT acceptance validator."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import (
    DRAT_PROOF_FORMAT,
    RUP_PROOF_FORMAT,
    DratProofCheckLimits,
    DratUnsatProofChecker,
    ValidationCompleteness,
    builtin_high_assurance_adapter_registry,
    builtin_unsat_proof_checker_registry,
    validate_external_cnf_certificate,
)
from audit_engine.semantic_audit.high_assurance.cnf_solver import cnf_digest
from audit_engine.semantic_audit.high_assurance.external_solver import CONTROLLED_EXTERNAL_CNF_ADAPTER_ID

ARTIFACT = ROOT / "artifacts" / "semantic_drat_proof_validation.json"


def certificate(digest: str, steps):
    return {
        "kind": "unsat_proof",
        "proof_format": DRAT_PROOF_FORMAT,
        "cnf_digest": digest,
        "steps": steps,
    }


def manual_workflows_05_18() -> bool:
    folder = ROOT / ".github" / "workflows"
    for number in range(5, 19):
        matches = list(folder.glob(f"{number:02d}_*.yml"))
        if len(matches) != 1:
            return False
        text = matches[0].read_text(encoding="utf-8")
        if "on:\n  workflow_dispatch:\n" not in text or "\n  push:" in text or "\n  pull_request:" in text:
            return False
    return True


def run() -> dict[str, object]:
    checks: dict[str, bool] = {}

    xor = ((1, 2), (-1, 2), (1, -2), (-1, -2))
    xor_digest = cnf_digest(3, xor)
    result = DratUnsatProofChecker().check(
        certificate=certificate(
            xor_digest,
            [
                {"op": "add", "clause": [3]},
                {"op": "delete", "clause": [3]},
                {"op": "add", "clause": [1]},
                {"op": "add", "clause": [-1]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=3,
        clauses=xor,
        subject_digest=xor_digest,
    )
    checks["drat_checker_accepts_rat_deletion_and_rup_chain"] = bool(
        result.accepted
        and result.witness is not None
        and result.witness.details["rat_additions"] == 1
        and result.witness.details["deletions"] == 1
    )

    nonvacuous = ((1, 2), (1, 3), (1, -2), (2, -1), (-1, -2))
    nonvacuous_digest = cnf_digest(3, nonvacuous)
    nonvacuous_result = DratUnsatProofChecker().check(
        certificate=certificate(
            nonvacuous_digest,
            [
                {"op": "add", "clause": [-3]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=3,
        clauses=nonvacuous,
        subject_digest=nonvacuous_digest,
    )
    checks["non_vacuous_rat_resolvent_is_checked"] = bool(
        nonvacuous_result.accepted
        and nonvacuous_result.witness is not None
        and nonvacuous_result.witness.details["rat_resolvents_checked"] >= 1
    )

    invalid_formula = ((-2, 3),)
    invalid_digest = cnf_digest(13, invalid_formula)
    invalid = validate_external_cnf_certificate(
        verdict="unsat",
        certificate=certificate(
            invalid_digest,
            [
                {"op": "add", "clause": [2]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=13,
        clauses=invalid_formula,
        subject_digest=invalid_digest,
        independent_unsat_max_variables=12,
    )
    checks["invalid_large_drat_does_not_promote_evidence"] = (
        not invalid.certificate_accepted
        and invalid.evidence_state == VerificationStatus.OBSERVED
        and invalid.completeness == ValidationCompleteness.PARTIAL
    )

    limited = DratUnsatProofChecker(limits=DratProofCheckLimits(max_steps=1)).check(
        certificate=certificate(
            xor_digest,
            [
                {"op": "add", "clause": [3]},
                {"op": "add", "clause": []},
            ],
        ),
        variable_count=3,
        clauses=xor,
        subject_digest=xor_digest,
    )
    checks["resource_limit_is_not_proof_acceptance"] = (
        not limited.accepted and limited.diagnostics == ("drat_resource_limit:step_limit",)
    )

    wrong_digest = DratUnsatProofChecker().check(
        certificate=certificate("0" * 64, [{"op": "add", "clause": []}]),
        variable_count=3,
        clauses=xor,
        subject_digest=xor_digest,
    )
    checks["drat_proof_is_bound_to_exact_cnf_digest"] = not wrong_digest.accepted

    formats = builtin_unsat_proof_checker_registry().formats()
    checks["builtins_register_rup_and_drat"] = formats == tuple(sorted((RUP_PROOF_FORMAT, DRAT_PROOF_FORMAT)))
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
        "cnf_drat_unsat_proof_contract.yaml",
        "drat_deletion_semantics_contract.yaml",
        "drat_resource_limit_contract.yaml",
    ):
        checks[f"contract_present:{name}"] = bool(
            yaml.safe_load((ROOT / "specs" / "contracts" / name).read_text(encoding="utf-8"))
        )
    for name in ("cnf_drat_unsat_proof.schema.json", "drat_proof_check.schema.json"):
        checks[f"schema_present:{name}"] = bool(
            json.loads((ROOT / "specs" / "schemas" / name).read_text(encoding="utf-8"))
        )

    workflow = (ROOT / ".github" / "workflows" / "18_semantic_drat_proof_validation.yml").read_text(encoding="utf-8")
    checks["workflow_18_manual_only"] = "on:\n  workflow_dispatch:\n" in workflow and "\n  push:" not in workflow
    checks["g3_workflows_05_18_manual_only"] = manual_workflows_05_18()

    payload = {
        "milestone": "G3.4.4",
        "validator": "validate_semantic_drat_proof_checking.py",
        "passed": all(checks.values()),
        "checks": checks,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = run()
    for name, passed in payload["checks"].items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if payload["passed"]:
        print("G3.4.4 repository-owned DRAT validation passed.")
        return 0
    print("G3.4.4 repository-owned DRAT validation failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

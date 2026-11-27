"""M7.5.17 reconciliation of semantic qualifications to rule obligations.

This is a derived adjudication record only. It does not mutate epistemic
coverage manifests or dossiers, create assertions, or grant audit authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .assurance import AssuranceClaim
from .coverage import EpistemicCoverageManifest
from .rule_coverage import RuleCoveragePlan
from .semantic_qualification import (
    SemanticQualificationError,
    semantic_evidence_contract_registry,
    verify_semantic_evidence_qualification,
)

SCHEMA = "ae32c/qualification-obligation-reconciliation/v1"
POLICY_SCHEMA = "ae32c/qualification-aggregation-policy-registry/v1"

# Each policy is explicit per rule/evidence contract. INSUFFICIENT observations
# are not counterevidence; a supported observation can therefore establish the
# narrow contract unless an unresolved/contested observation remains.
_POLICY_TEMPLATE = {
    "version": "1.0.0",
    "aggregation": "CONTESTED_THEN_UNKNOWN_THEN_ANY_SUPPORTED_ELSE_INSUFFICIENT",
    "precedence": ["CONTESTED", "UNKNOWN", "SUPPORTED", "INSUFFICIENT"],
}


class QualificationReconciliationError(ValueError):
    """A qualification set cannot be reconciled safely to its rule obligations."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def qualification_aggregation_policy_registry() -> dict[str, Any]:
    """Return the versioned, rule-specific aggregation policy registry."""
    contracts = semantic_evidence_contract_registry()["contracts"]
    policies = {
        f"{rule_id}|{contract['evidence_kind']}": dict(_POLICY_TEMPLATE)
        for rule_id, contract in sorted(contracts.items())
    }
    payload = {"schema": POLICY_SCHEMA, "policies": policies}
    return {**payload, "registry_sha256": _digest(payload)}


def _parts(obligation_id: str) -> tuple[str, str, str]:
    parts = obligation_id.split(":")
    if len(parts) < 4 or parts[0] != "rule" or parts[2] not in {"evidence", "coverage"}:
        raise QualificationReconciliationError("invalid_rule_obligation_id:" + obligation_id)
    return parts[1], parts[2], ":".join(parts[3:])


def _aggregate(rule_id: str, evidence_kind: str,
               rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    key = f"{rule_id}|{evidence_kind}"
    policy = qualification_aggregation_policy_registry()["policies"].get(key)
    if not rows:
        disposition = "UNKNOWN"
        reason = "no_qualification_record_for_expected_evidence_obligation"
    elif policy is None:
        disposition = "UNKNOWN"
        reason = "no_rule_specific_aggregation_policy"
    else:
        states = {row.get("qualification") for row in rows}
        invalid = states - {"SUPPORTED", "INSUFFICIENT", "CONTESTED", "UNKNOWN"}
        if invalid:
            raise QualificationReconciliationError("qualification_state_invalid")
        selected = next((state for state in policy["precedence"] if state in states), None)
        if selected is None:
            raise QualificationReconciliationError("aggregation_policy_has_no_matching_state")
        disposition = "SUPPORTED_WITHIN_CONTRACT" if selected == "SUPPORTED" else selected
        reasons = {
            "CONTESTED": "at_least_one_observation_has_an_unresolved_defeater",
            "UNKNOWN": "at_least_one_observation_remains_semantically_unqualified",
            "SUPPORTED": "at_least_one_observation_supports_the_narrow_contract_and_none_is_contested_or_unknown",
            "INSUFFICIENT": "all_observations_are_insufficient_for_the_narrow_contract",
        }
        reason = reasons[selected]
    ordered = sorted(rows, key=lambda row: (str(row.get("observation_id")), str(row.get("qualification"))))
    return {
        "obligation_id": f"rule:{rule_id}:evidence:{evidence_kind}",
        "rule_id": rule_id,
        "evidence_kind": evidence_kind,
        "disposition": disposition,
        "reason": reason,
        "observation_count": len(ordered),
        "observation_ids": [row["observation_id"] for row in ordered],
        "qualification_states": [row["qualification"] for row in ordered],
        "supported_observation_ids": sorted(
            row["observation_id"] for row in ordered if row["qualification"] == "SUPPORTED"),
        "insufficient_observation_ids": sorted(
            row["observation_id"] for row in ordered if row["qualification"] == "INSUFFICIENT"),
        "contested_observation_ids": sorted(
            row["observation_id"] for row in ordered if row["qualification"] == "CONTESTED"),
        "unknown_observation_ids": sorted(
            row["observation_id"] for row in ordered if row["qualification"] == "UNKNOWN"),
        "aggregation_policy": policy["aggregation"] if policy else None,
        "aggregation_policy_version": policy["version"] if policy else None,
    }


def reconcile_semantic_qualifications(
    qualification: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    claim: AssuranceClaim,
    plan: RuleCoveragePlan,
    coverage_manifest: EpistemicCoverageManifest,
    source_manifest: Mapping[str, Any],
    repository_root: str | Path,
    defeaters: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Replay qualification and reconcile every rule-derived evidence obligation.

    Coverage obligations are reported as NOT_IN_SCOPE. Missing evidence
    qualifications remain UNKNOWN; this function never infers absence.
    """
    try:
        replay = verify_semantic_evidence_qualification(
            qualification, bundle, claim=claim, plan=plan,
            coverage_manifest=coverage_manifest, source_manifest=source_manifest,
            repository_root=repository_root, defeaters=defeaters,
        )
    except (SemanticQualificationError, ValueError, TypeError, KeyError, OSError) as exc:
        raise QualificationReconciliationError(
            "semantic_qualification_replay_failed:" + type(exc).__name__) from exc

    if qualification.get("schema") != "ae32c/semantic-evidence-qualification/v1":
        raise QualificationReconciliationError("qualification_schema_invalid")
    records = qualification.get("qualifications")
    if not isinstance(records, list) or qualification.get("qualification_count") != len(records):
        raise QualificationReconciliationError("qualification_collection_invalid")

    expected = set(plan.expected_obligation_ids)
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for row in records:
        if not isinstance(row, Mapping):
            raise QualificationReconciliationError("qualification_record_invalid")
        obligation_id = row.get("obligation_id")
        observation_id = row.get("observation_id")
        if obligation_id not in expected:
            raise QualificationReconciliationError("qualification_outside_verified_plan")
        if not isinstance(observation_id, str) or not observation_id:
            raise QualificationReconciliationError("qualification_observation_id_invalid")
        rule_id, dimension, requirement = _parts(obligation_id)
        if dimension != "evidence":
            raise QualificationReconciliationError("qualification_bound_to_non_evidence_obligation")
        if row.get("rule_id") != rule_id or row.get("evidence_kind") != requirement:
            raise QualificationReconciliationError("qualification_rule_evidence_binding_mismatch")
        pair = (obligation_id, observation_id)
        if pair in seen_pairs:
            raise QualificationReconciliationError("duplicate_obligation_observation_qualification")
        seen_pairs.add(pair)
        grouped.setdefault(obligation_id, []).append(row)

    reconciled = []
    for obligation_id in plan.expected_obligation_ids:
        rule_id, dimension, requirement = _parts(obligation_id)
        if dimension == "coverage":
            reconciled.append({
                "obligation_id": obligation_id,
                "rule_id": rule_id,
                "dimension": "coverage",
                "disposition": "NOT_IN_SCOPE",
                "reason": "M7.5.17 reconciles semantic evidence obligations only",
                "observation_count": 0,
                "observation_ids": [],
            })
        else:
            reconciled.append(_aggregate(rule_id, requirement, grouped.get(obligation_id, [])))

    reconciled.sort(key=lambda row: row["obligation_id"])
    summary = {
        state: sum(1 for row in reconciled if row["disposition"] == state)
        for state in ("SUPPORTED_WITHIN_CONTRACT", "INSUFFICIENT", "CONTESTED", "UNKNOWN", "NOT_IN_SCOPE")
    }
    policy_registry = qualification_aggregation_policy_registry()
    payload = {
        "schema": SCHEMA,
        "claim_id": claim.claim_id,
        "source_snapshot_id": plan.source_snapshot_id,
        "plan_sha256": plan.plan_sha256,
        "rule_registry_sha256": plan.registry_sha256,
        "coverage_manifest_sha256": coverage_manifest.manifest_sha256,
        "qualification_sha256": qualification["qualification_sha256"],
        "observation_bundle_sha256": bundle["bundle_sha256"],
        "qualification_replay": {
            "semantic_replay": replay["semantic_replay"],
            "qualification_count": replay["qualification_count"],
        },
        "aggregation_policy_registry_sha256": policy_registry["registry_sha256"],
        "expected_obligation_ids": list(plan.expected_obligation_ids),
        "obligation_reconciliations": reconciled,
        "summary": summary,
        "authority": {
            "all_evidence_obligations_satisfied": False,
            "epistemic_coverage_manifest_mutated": False,
            "coverage_dossier_mutated": False,
            "epistemic_assertions_created": False,
            "proposition_truth_established": False,
            "audit_decision_authority": False,
            "allow_deny_authority": False,
            "production_approval": False,
        },
    }
    return {**payload, "reconciliation_sha256": _digest(payload)}


def verify_qualification_obligation_reconciliation(
    reconciliation: Mapping[str, Any],
    qualification: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    claim: AssuranceClaim,
    plan: RuleCoveragePlan,
    coverage_manifest: EpistemicCoverageManifest,
    source_manifest: Mapping[str, Any],
    repository_root: str | Path,
    defeaters: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Independently replay a qualification-to-obligation reconciliation."""
    if not isinstance(reconciliation, Mapping):
        raise TypeError("reconciliation_must_be_an_object")
    submitted = dict(reconciliation)
    identity = submitted.get("reconciliation_sha256")
    payload = {key: value for key, value in submitted.items() if key != "reconciliation_sha256"}
    if identity != _digest(payload):
        raise QualificationReconciliationError("reconciliation_digest_mismatch")
    expected = reconcile_semantic_qualifications(
        qualification, bundle, claim=claim, plan=plan,
        coverage_manifest=coverage_manifest, source_manifest=source_manifest,
        repository_root=repository_root, defeaters=defeaters,
    )
    if _canonical(expected) != _canonical(submitted):
        raise QualificationReconciliationError("reconciliation_semantic_replay_mismatch")
    return {
        "reconciliation_sha256": identity,
        "semantic_replay": True,
        "obligation_count": len(expected["obligation_reconciliations"]),
        "summary": dict(expected["summary"]),
    }

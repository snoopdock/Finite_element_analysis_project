"""M7.5.23 composition of execution and semantic qualification by obligation.

The output is a two-axis inspection artifact. It does not merge execution
completion with semantic support or grant epistemic/decision authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


SCHEMA = "ae32c/execution-semantic-obligation-composition/v1"
EXECUTION_SCHEMA = "ae32c/execution-obligation-reconciliation/v1"
QUALIFICATION_SCHEMA = "ae32c/qualification-obligation-reconciliation/v1"


class ObligationCompositionError(ValueError):
    """Cross-layer obligation composition cannot be verified."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sealed_payload(value: Mapping[str, Any], identity_key: str, error: str) -> str:
    identity = value.get(identity_key)
    payload = {key: item for key, item in value.items() if key != identity_key}
    if not isinstance(identity, str) or identity != _digest(payload):
        raise ObligationCompositionError(error)
    return identity


def _unique_ids(values: Any, error: str) -> list[str]:
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ObligationCompositionError(error)
    if len(values) != len(set(values)):
        raise ObligationCompositionError(error)
    return values


def _validate_execution_replay(report: Mapping[str, Any],
                               replay: Mapping[str, Any]) -> None:
    if not isinstance(replay, Mapping):
        raise ObligationCompositionError("execution_replay_result_invalid")
    if (
        replay.get("reconciliation_sha256") != report.get("reconciliation_sha256")
        or replay.get("ledger_integrity") is not True
        or replay.get("semantic_replay") is not True
        or replay.get("dossier_unchanged") is not True
    ):
        raise ObligationCompositionError("execution_replay_not_verified")


def _qualification_consumer_state(
    qualification: Mapping[str, Any],
    consumer_result: Mapping[str, Any],
) -> tuple[str, str]:
    if not isinstance(consumer_result, Mapping):
        raise ObligationCompositionError("qualification_consumer_result_invalid")
    record_id = qualification.get("reconciliation_sha256")
    if consumer_result.get("record_id") != record_id:
        raise ObligationCompositionError("qualification_consumer_record_binding_mismatch")
    if (
        not isinstance(consumer_result.get("consumer_id"), str)
        or not consumer_result["consumer_id"].strip()
        or not isinstance(consumer_result.get("operation"), str)
        or not consumer_result["operation"].strip()
        or consumer_result.get("downstream_authorization") != "NOT_EVALUATED"
    ):
        raise ObligationCompositionError("qualification_consumer_contract_invalid")
    preflight = consumer_result.get("preflight")
    if not isinstance(preflight, Mapping):
        raise ObligationCompositionError("qualification_consumer_preflight_missing")
    preflight_status = preflight.get("consumer_preflight_status")
    operation_status = consumer_result.get("consumer_operation_status")
    if (
        operation_status == "REPLAY_VERIFIED"
        and preflight_status == "CURRENTNESS_CONFIRMED"
        and consumer_result.get("semantic_replay_performed") is True
    ):
        replay = consumer_result.get("replay_result")
        if not isinstance(replay, Mapping) or (
            replay.get("record_id") != record_id
            or replay.get("ledger_integrity") is not True
            or replay.get("historical_replay") is not True
            or replay.get("semantic_replay") is not True
        ):
            raise ObligationCompositionError("qualification_semantic_replay_not_verified")
        return "CURRENT_REPLAY_VERIFIED", preflight_status
    if (
        operation_status == "BLOCKED_INVALIDATED"
        and preflight_status == "BLOCKED_INVALIDATED"
        and consumer_result.get("semantic_replay_performed") is False
        and consumer_result.get("replay_result") is None
    ):
        return "BLOCKED_INVALIDATED", preflight_status
    raise ObligationCompositionError("qualification_consumer_outcome_invalid")


def compose_execution_and_semantic_obligations(
    execution_reconciliation: Mapping[str, Any],
    execution_replay: Mapping[str, Any],
    qualification_reconciliation: Mapping[str, Any],
    qualification_consumer_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Compose two independently verified obligation assessments without merging them."""
    if not all(isinstance(item, Mapping) for item in (
        execution_reconciliation, qualification_reconciliation
    )):
        raise TypeError("reconciliation_inputs_must_be_mappings")

    execution_id = _sealed_payload(
        execution_reconciliation, "reconciliation_sha256",
        "execution_reconciliation_digest_mismatch",
    )
    qualification_id = _sealed_payload(
        qualification_reconciliation, "reconciliation_sha256",
        "qualification_reconciliation_digest_mismatch",
    )
    execution = execution_reconciliation
    qualification = qualification_reconciliation
    if execution.get("schema") != EXECUTION_SCHEMA:
        raise ObligationCompositionError("execution_reconciliation_schema_invalid")
    if qualification.get("schema") != QUALIFICATION_SCHEMA:
        raise ObligationCompositionError("qualification_reconciliation_schema_invalid")
    if not isinstance(qualification.get("qualification_replay"), Mapping) or (
        qualification["qualification_replay"].get("semantic_replay") is not True
    ):
        raise ObligationCompositionError("qualification_reconciliation_replay_not_verified")
    execution_authority = execution.get("authority")
    qualification_authority = qualification.get("authority")
    if not isinstance(execution_authority, Mapping) or not isinstance(qualification_authority, Mapping):
        raise ObligationCompositionError("source_reconciliation_authority_contract_missing")
    if any(execution_authority.get(key) is not False for key in (
        "semantic_evidence_sufficiency_established", "proposition_truth_established",
        "graph_completeness_established", "audit_decision_authority", "production_approval",
    )):
        raise ObligationCompositionError("execution_reconciliation_authority_boundary_violation")
    if any(qualification_authority.get(key) is not False for key in (
        "all_evidence_obligations_satisfied", "epistemic_coverage_manifest_mutated",
        "epistemic_assertions_created", "proposition_truth_established",
        "audit_decision_authority", "allow_deny_authority", "production_approval",
    )):
        raise ObligationCompositionError("qualification_reconciliation_authority_boundary_violation")
    execution_summary = execution.get("summary")
    if not isinstance(execution_summary, Mapping) or any(
        execution_summary.get(key) is not False
        for key in ("epistemic_coverage_upgraded", "coverage_dossier_mutated")
    ):
        raise ObligationCompositionError("execution_reconciliation_summary_boundary_violation")
    _validate_execution_replay(execution, execution_replay)
    qualification_state, preflight_status = _qualification_consumer_state(
        qualification, qualification_consumer_result
    )

    for field in ("claim_id", "source_snapshot_id", "plan_sha256",
                  "coverage_manifest_sha256"):
        if not isinstance(execution.get(field), str) or not execution[field]:
            raise ObligationCompositionError("cross_layer_binding_missing:" + field)
        if execution.get(field) != qualification.get(field):
            raise ObligationCompositionError("cross_layer_binding_mismatch:" + field)

    expected_ids = _unique_ids(
        qualification.get("expected_obligation_ids"),
        "qualification_expected_obligation_ids_invalid",
    )
    execution_rows = execution.get("obligations")
    semantic_rows = qualification.get("obligation_reconciliations")
    if not isinstance(execution_rows, list) or not isinstance(semantic_rows, list):
        raise ObligationCompositionError("obligation_rows_invalid")
    execution_map = {}
    for row in execution_rows:
        if not isinstance(row, Mapping):
            raise ObligationCompositionError("execution_obligation_row_invalid")
        oid = row.get("obligation_id")
        if not isinstance(oid, str) or not oid or oid in execution_map:
            raise ObligationCompositionError("execution_obligation_identity_duplicate_or_invalid")
        execution_map[oid] = row
    semantic_map = {}
    for row in semantic_rows:
        if not isinstance(row, Mapping):
            raise ObligationCompositionError("semantic_obligation_row_invalid")
        oid = row.get("obligation_id")
        if not isinstance(oid, str) or not oid or oid in semantic_map:
            raise ObligationCompositionError("semantic_obligation_identity_duplicate_or_invalid")
        semantic_map[oid] = row
    if set(execution_map) != set(expected_ids) or set(semantic_map) != set(expected_ids):
        raise ObligationCompositionError("cross_layer_obligation_inventory_mismatch")

    rows = []
    for oid in sorted(expected_ids):
        execution_row = execution_map[oid]
        semantic_row = semantic_map[oid]
        execution_assessment = {
            "kind": execution_row.get("kind"),
            "status": execution_row.get("status"),
            "reason": execution_row.get("reason"),
            "candidate_ids": list(execution_row.get("candidate_ids", [])),
            "outcome_ids": list(execution_row.get("outcome_ids", [])),
        }
        if qualification_state == "CURRENT_REPLAY_VERIFIED":
            semantic_assessment = {
                "state": qualification_state,
                "disposition": semantic_row.get("disposition"),
                "reason": semantic_row.get("reason"),
                "observation_ids": list(semantic_row.get("observation_ids", [])),
            }
        else:
            semantic_assessment = {
                "state": qualification_state,
                "disposition": None,
                "historical_disposition": semantic_row.get("disposition"),
                "reason": "qualification_currentness_preflight_blocked",
                "observation_ids": [],
            }
        rows.append({
            "obligation_id": oid,
            "execution_assessment": execution_assessment,
            "semantic_qualification": semantic_assessment,
        })

    execution_complete = execution_summary.get(
        "extractor_execution_complete_for_declared_coverage"
    ) is True
    payload = {
        "schema": SCHEMA,
        "claim_id": execution["claim_id"],
        "source_snapshot_id": execution["source_snapshot_id"],
        "plan_sha256": execution["plan_sha256"],
        "coverage_manifest_sha256": execution["coverage_manifest_sha256"],
        "execution_reconciliation_sha256": execution_id,
        "execution_dossier_id": execution.get("dossier_id"),
        "qualification_reconciliation_sha256": qualification_id,
        "qualification_currentness": {
            "state": qualification_state,
            "preflight_status": preflight_status,
            "semantic_dispositions_are_current": qualification_state == "CURRENT_REPLAY_VERIFIED",
        },
        "obligations": rows,
        "summary": {
            "obligation_count": len(rows),
            "extractor_execution_complete_for_declared_coverage": execution_complete,
            "semantic_qualification_current": qualification_state == "CURRENT_REPLAY_VERIFIED",
            "semantic_qualification_blocked": qualification_state == "BLOCKED_INVALIDATED",
            "epistemic_evidence_acceptance_established": False,
        },
        "authority": {
            "execution_reconciliation_replayed": True,
            "qualification_reconciliation_currently_replayed": qualification_state == "CURRENT_REPLAY_VERIFIED",
            "epistemic_evidence_accepted": False,
            "proposition_truth_established": False,
            "graph_completeness_established": False,
            "assurance_success_established": False,
            "audit_decision_authority": False,
            "allow_deny_authority": False,
            "release_approval": False,
            "production_approval": False,
        },
    }
    return {**payload, "composition_sha256": _digest(payload)}


def verify_obligation_composition(
    composition: Mapping[str, Any],
    execution_reconciliation: Mapping[str, Any],
    execution_replay: Mapping[str, Any],
    qualification_reconciliation: Mapping[str, Any],
    qualification_consumer_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute and compare the complete composition artifact."""
    if not isinstance(composition, Mapping):
        raise TypeError("composition_must_be_a_mapping")
    submitted = dict(composition)
    identity = submitted.get("composition_sha256")
    if identity != _digest({key: value for key, value in submitted.items()
                            if key != "composition_sha256"}):
        raise ObligationCompositionError("composition_digest_mismatch")
    expected = compose_execution_and_semantic_obligations(
        execution_reconciliation, execution_replay,
        qualification_reconciliation, qualification_consumer_result,
    )
    if _canonical(submitted) != _canonical(expected):
        raise ObligationCompositionError("composition_semantic_replay_mismatch")
    return {
        "composition_sha256": identity,
        "semantic_replay": True,
        "obligation_count": len(expected["obligations"]),
        "qualification_currentness": expected["qualification_currentness"]["state"],
        "epistemic_evidence_accepted": False,
        "audit_decision_authority": False,
        "production_approval": False,
    }

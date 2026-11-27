"""M7.5.21 currentness-enforced persisted qualification replay consumer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .qualification_consumer_gate import (
    QualificationConsumerCheckStore,
    QualificationConsumerGateError,
    evaluate_qualification_reconciliation_for_consumer,
)
from .qualification_reconciliation import qualification_aggregation_policy_registry
from .qualification_reconciliation_store import (
    QualificationReconciliationStore,
    QualificationReconciliationStoreError,
    verify_persisted_qualification_reconciliation,
)
from .semantic_qualification import semantic_evidence_contract_registry


class QualificationConsumerReplayError(RuntimeError):
    """A qualification consumer cannot bind current artifacts to its preflight."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest_payload(value: Mapping[str, Any], identity_field: str) -> str:
    payload = {key: item for key, item in value.items() if key != identity_field}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def qualification_consumer_current_context(
    *,
    claim: Any,
    plan: Any,
    coverage_manifest: Any,
    current_qualification: Mapping[str, Any],
    current_observation_bundle: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
) -> dict[str, str]:
    """Derive the eight-dimensional currentness token from supplied live artifacts."""
    if not isinstance(current_qualification, Mapping) or not isinstance(current_observation_bundle, Mapping):
        raise TypeError("current_qualification_and_observation_bundle_must_be_mappings")
    if not isinstance(source_manifest, Mapping):
        raise TypeError("source_manifest_must_be_a_mapping")
    try:
        source_id = plan.source_snapshot_id
        if (
            claim.source_snapshot_id != source_id
            or source_manifest.get("source_snapshot_id") != source_id
            or current_qualification.get("source_snapshot_id") != source_id
            or current_observation_bundle.get("source_snapshot_id") != source_id
        ):
            raise QualificationConsumerReplayError("current_artifacts_source_snapshot_mismatch")
        qualification_id = current_qualification.get("qualification_sha256")
        bundle_id = current_observation_bundle.get("bundle_sha256")
        if (
            not isinstance(qualification_id, str)
            or qualification_id != _digest_payload(current_qualification, "qualification_sha256")
        ):
            raise QualificationConsumerReplayError("current_qualification_digest_mismatch")
        if (
            not isinstance(bundle_id, str)
            or bundle_id != _digest_payload(current_observation_bundle, "bundle_sha256")
        ):
            raise QualificationConsumerReplayError("current_observation_bundle_digest_mismatch")
        if current_qualification.get("observation_bundle_sha256") != bundle_id:
            raise QualificationConsumerReplayError("current_qualification_bundle_binding_mismatch")
        if current_observation_bundle.get("plan_sha256") != plan.plan_sha256:
            raise QualificationConsumerReplayError("current_bundle_plan_binding_mismatch")
        contract_registry = semantic_evidence_contract_registry()
        aggregation_registry = qualification_aggregation_policy_registry()
        if current_qualification.get("contract_registry_sha256") != contract_registry["registry_sha256"]:
            raise QualificationConsumerReplayError("current_semantic_contract_registry_mismatch")
        return {
            "source_snapshot_id": source_id,
            "plan_sha256": plan.plan_sha256,
            "rule_registry_sha256": plan.registry_sha256,
            "coverage_manifest_sha256": coverage_manifest.manifest_sha256,
            "contract_registry_sha256": contract_registry["registry_sha256"],
            "aggregation_policy_registry_sha256": aggregation_registry["registry_sha256"],
            "qualification_sha256": qualification_id,
            "observation_bundle_sha256": bundle_id,
        }
    except AttributeError as exc:
        raise QualificationConsumerReplayError("current_artifact_contract_invalid") from exc


def verify_persisted_qualification_reconciliation_for_consumer(
    record_id: str,
    *,
    consumer_id: str,
    operation: str,
    reconciliation_store: QualificationReconciliationStore,
    check_store: QualificationConsumerCheckStore,
    current_context: Mapping[str, str],
    claim: Any,
    plan: Any,
    coverage_manifest: Any,
    current_qualification: Mapping[str, Any],
    current_observation_bundle: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    repository_root: str | Path,
    defeaters: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Gate and then semantically replay a persisted reconciliation for a named consumer.

    A blocked preflight returns without semantic replay. A current preflight
    must match context independently derived from the caller's live artifacts;
    only then is the existing M7.5.18 historical replay verifier invoked.
    """
    expected_context = qualification_consumer_current_context(
        claim=claim, plan=plan, coverage_manifest=coverage_manifest,
        current_qualification=current_qualification,
        current_observation_bundle=current_observation_bundle,
        source_manifest=source_manifest,
    )
    if not isinstance(current_context, Mapping) or dict(current_context) != expected_context:
        raise QualificationConsumerReplayError("caller_current_context_does_not_match_live_artifacts")

    preflight = evaluate_qualification_reconciliation_for_consumer(
        record_id,
        consumer_id=consumer_id,
        operation=operation,
        reconciliation_store=reconciliation_store,
        check_store=check_store,
        current_context=expected_context,
    )
    if preflight["consumer_preflight_status"] == "BLOCKED_INVALIDATED":
        return {
            "consumer_operation_status": "BLOCKED_INVALIDATED",
            "record_id": record_id,
            "consumer_id": consumer_id,
            "operation": operation,
            "preflight": preflight,
            "semantic_replay_performed": False,
            "replay_result": None,
            "downstream_authorization": "NOT_EVALUATED",
        }

    replay = verify_persisted_qualification_reconciliation(
        record_id,
        store=reconciliation_store,
        claim=claim,
        plan=plan,
        coverage_manifest=coverage_manifest,
        source_manifest=source_manifest,
        repository_root=repository_root,
        defeaters=defeaters,
    )
    return {
        "consumer_operation_status": "REPLAY_VERIFIED",
        "record_id": record_id,
        "consumer_id": consumer_id,
        "operation": operation,
        "preflight": preflight,
        "semantic_replay_performed": True,
        "replay_result": replay,
        "downstream_authorization": "NOT_EVALUATED",
    }

"""M7.5.24 orchestration of persisted cross-layer obligation verification.

This adapter retrieves persisted reconciliation records, invokes the existing
M7.5.14 and M7.5.21 verification paths, and composes only their returned
results. It does not make the participating SQLite stores transactional.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .execution_obligation_reconciliation import (
    ExecutionObligationReconciliationError,
    ExecutionObligationReconciliationStore,
    verify_execution_obligation_reconciliation,
)
from .obligation_composition import (
    compose_execution_and_semantic_obligations,
)
from .qualification_reconciliation_consumer import (
    QualificationConsumerReplayError,
    qualification_consumer_current_context,
    verify_persisted_qualification_reconciliation_for_consumer,
)
from .qualification_reconciliation_store import (
    QualificationReconciliationStore,
    QualificationReconciliationStoreError,
)


SCHEMA = "ae32c/orchestrated-persisted-obligation-composition/v1"


class ObligationCompositionOrchestrationError(RuntimeError):
    """Persisted cross-layer composition could not be orchestrated safely."""


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def verify_persisted_cross_layer_obligation_composition(
    execution_reconciliation_id: str,
    qualification_record_id: str,
    *,
    execution_reconciliation_store: ExecutionObligationReconciliationStore,
    dossier_id: str,
    claim: Any,
    plan: Any,
    coverage_manifest: Any,
    source_manifest: Mapping[str, Any],
    inventory: Mapping[str, Any],
    execution_report: Mapping[str, Any],
    repository_root: str | Path,
    assurance_store: Any,
    epistemic_store: Any,
    dossier_store: Any,
    qualification_reconciliation_store: QualificationReconciliationStore,
    qualification_check_store: Any,
    consumer_id: str,
    operation: str,
    current_qualification: Mapping[str, Any],
    current_observation_bundle: Mapping[str, Any],
    defeaters: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Verify persisted execution and qualification records, then compose them.

    The execution verifier receives its original source/dossier context. The
    qualification consumer derives its currentness context from live artifacts
    and performs its own preflight-before-replay sequence. No replay-result
    mapping is accepted from the caller.
    """
    if not isinstance(execution_reconciliation_id, str) or not execution_reconciliation_id.strip():
        raise ObligationCompositionOrchestrationError("execution_reconciliation_id_required")
    if not isinstance(qualification_record_id, str) or not qualification_record_id.strip():
        raise ObligationCompositionOrchestrationError("qualification_record_id_required")
    if not isinstance(consumer_id, str) or not consumer_id.strip():
        raise ObligationCompositionOrchestrationError("consumer_id_required")
    if not isinstance(operation, str) or not operation.strip():
        raise ObligationCompositionOrchestrationError("consumer_operation_required")

    try:
        execution_reconciliation = execution_reconciliation_store.get(
            execution_reconciliation_id
        )
    except ExecutionObligationReconciliationError:
        raise
    if execution_reconciliation is None:
        raise ObligationCompositionOrchestrationError(
            "execution_reconciliation_not_found"
        )
    if not isinstance(execution_reconciliation, Mapping):
        raise ObligationCompositionOrchestrationError(
            "execution_persisted_record_invalid"
        )
    if execution_reconciliation.get("reconciliation_sha256") != execution_reconciliation_id:
        raise ObligationCompositionOrchestrationError(
            "execution_persisted_record_identity_mismatch"
        )

    try:
        qualification_envelope = qualification_reconciliation_store.get(
            qualification_record_id
        )
    except QualificationReconciliationStoreError:
        raise
    if qualification_envelope is None:
        raise ObligationCompositionOrchestrationError(
            "qualification_reconciliation_not_found"
        )
    if (
        not isinstance(qualification_envelope, Mapping)
        or qualification_envelope.get("record_id") != qualification_record_id
        or not isinstance(qualification_envelope.get("reconciliation"), Mapping)
    ):
        raise ObligationCompositionOrchestrationError(
            "qualification_persisted_envelope_invalid"
        )
    qualification_reconciliation = qualification_envelope["reconciliation"]
    if qualification_reconciliation.get("reconciliation_sha256") != qualification_record_id:
        raise ObligationCompositionOrchestrationError(
            "qualification_persisted_record_identity_mismatch"
        )

    # M7.5.14 independently checks ledger integrity and re-derives the report
    # against the live source, inventory, execution report, and dossier stores.
    execution_replay = verify_execution_obligation_reconciliation(
        execution_reconciliation_id,
        reconciliation_store=execution_reconciliation_store,
        dossier_id=dossier_id,
        claim=claim,
        plan=plan,
        manifest=coverage_manifest,
        source_manifest=source_manifest,
        inventory=inventory,
        execution_report=execution_report,
        repository_root=repository_root,
        assurance_store=assurance_store,
        epistemic_store=epistemic_store,
        dossier_store=dossier_store,
    )

    # Derive the eight-dimensional currentness context here. The M7.5.21
    # adapter independently derives it again before accepting the preflight.
    try:
        current_context = qualification_consumer_current_context(
            claim=claim,
            plan=plan,
            coverage_manifest=coverage_manifest,
            current_qualification=current_qualification,
            current_observation_bundle=current_observation_bundle,
            source_manifest=source_manifest,
        )
        qualification_consumer_result = (
            verify_persisted_qualification_reconciliation_for_consumer(
                qualification_record_id,
                consumer_id=consumer_id,
                operation=operation,
                reconciliation_store=qualification_reconciliation_store,
                check_store=qualification_check_store,
                current_context=current_context,
                claim=claim,
                plan=plan,
                coverage_manifest=coverage_manifest,
                current_qualification=current_qualification,
                current_observation_bundle=current_observation_bundle,
                source_manifest=source_manifest,
                repository_root=repository_root,
                defeaters=defeaters,
            )
        )
    except QualificationConsumerReplayError:
        raise

    composition = compose_execution_and_semantic_obligations(
        execution_reconciliation,
        execution_replay,
        qualification_reconciliation,
        qualification_consumer_result,
    )
    payload = {
        "schema": SCHEMA,
        "execution_reconciliation_sha256": execution_reconciliation_id,
        "qualification_reconciliation_sha256": qualification_record_id,
        "execution_replay": execution_replay,
        "qualification_consumer_result": qualification_consumer_result,
        "composition": composition,
        "authority": {
            "execution_replay_verified": True,
            "qualification_currently_replayed": (
                composition["qualification_currentness"]["state"]
                == "CURRENT_REPLAY_VERIFIED"
            ),
            "epistemic_evidence_accepted": False,
            "proposition_truth_established": False,
            "audit_decision_authority": False,
            "allow_deny_authority": False,
            "release_approval": False,
            "production_approval": False,
            "downstream_authorization": "NOT_EVALUATED",
        },
    }
    return {**payload, "orchestration_sha256": _digest(payload)}


def verify_orchestrated_obligation_composition(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Check the orchestration envelope digest and embedded composition digest.

    This verifies the returned envelope's content binding only. Replaying the
    underlying persisted records requires calling the orchestration API again
    with the live stores and original verification context.
    """
    if not isinstance(result, Mapping):
        raise TypeError("orchestration_result_must_be_a_mapping")
    submitted = dict(result)
    identity = submitted.get("orchestration_sha256")
    payload = {key: value for key, value in submitted.items()
               if key != "orchestration_sha256"}
    if not isinstance(identity, str) or identity != _digest(payload):
        raise ObligationCompositionOrchestrationError(
            "orchestration_digest_mismatch"
        )
    composition = submitted.get("composition")
    if not isinstance(composition, Mapping):
        raise ObligationCompositionOrchestrationError(
            "orchestration_composition_missing"
        )
    composition_id = composition.get("composition_sha256")
    composition_payload = {
        key: value for key, value in composition.items()
        if key != "composition_sha256"
    }
    if not isinstance(composition_id, str) or composition_id != _digest(
        composition_payload
    ):
        raise ObligationCompositionOrchestrationError(
            "embedded_composition_digest_mismatch"
        )
    return {
        "orchestration_sha256": identity,
        "composition_sha256": composition_id,
        "orchestration_envelope_integrity": True,
        "composition_content_integrity": True,
        "semantic_replay_performed": False,
        "downstream_authorization": "NOT_EVALUATED",
    }

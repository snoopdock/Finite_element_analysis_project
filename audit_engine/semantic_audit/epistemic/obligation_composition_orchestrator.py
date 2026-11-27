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
from .cross_layer_snapshot_provenance import (
    CrossLayerSnapshotProvenanceError,
    verify_cross_layer_snapshot_provenance,
    verify_cross_layer_snapshot_provenance_envelope,
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


def _run_persisted_cross_layer_obligation_composition(
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
    _include_context: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], dict[str, Any]]:
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

    # Re-run execution reconciliation after qualification verification. This
    # brackets the qualification operation and detects execution-side drift
    # observed between the two checks; it is not an atomic cross-store snapshot.
    try:
        execution_replay_postflight = verify_execution_obligation_reconciliation(
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
    except ExecutionObligationReconciliationError as exc:
        raise ObligationCompositionOrchestrationError(
            "execution_reconciliation_changed_during_cross_layer_verification"
        ) from exc
    if execution_replay_postflight != execution_replay:
        raise ObligationCompositionOrchestrationError(
            "execution_replay_bracket_mismatch"
        )
    execution_replay_bracket = {
        "pre_qualification_replay_verified": True,
        "post_qualification_replay_verified": True,
        "reconciliation_sha256": execution_reconciliation_id,
        "results_identical": True,
        "atomic_cross_store_snapshot": False,
    }
    execution_replay = execution_replay_postflight

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
        "execution_replay_bracket": execution_replay_bracket,
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
    result = {**payload, "orchestration_sha256": _digest(payload)}
    if _include_context:
        return result, {
            "source_manifest": source_manifest,
            "execution_reconciliation": execution_reconciliation,
            "qualification_reconciliation": qualification_reconciliation,
            "qualification": current_qualification,
            "observation_bundle": current_observation_bundle,
            "repository_root": repository_root,
        }
    return result


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
    """Run the original M7.5.24 v1 operation and return its unchanged result."""
    return _run_persisted_cross_layer_obligation_composition(
        execution_reconciliation_id,
        qualification_record_id,
        execution_reconciliation_store=execution_reconciliation_store,
        dossier_id=dossier_id,
        claim=claim,
        plan=plan,
        coverage_manifest=coverage_manifest,
        source_manifest=source_manifest,
        inventory=inventory,
        execution_report=execution_report,
        repository_root=repository_root,
        assurance_store=assurance_store,
        epistemic_store=epistemic_store,
        dossier_store=dossier_store,
        qualification_reconciliation_store=qualification_reconciliation_store,
        qualification_check_store=qualification_check_store,
        consumer_id=consumer_id,
        operation=operation,
        current_qualification=current_qualification,
        current_observation_bundle=current_observation_bundle,
        defeaters=defeaters,
    )


PACKAGE_SCHEMA = "ae32c/cross-layer-obligation-package/v1"


class CrossLayerObligationPackageError(RuntimeError):
    """A strict source-state-replayed cross-layer package could not be built or verified."""


def _validate_orchestration_package_contract(orchestration: Mapping[str, Any]) -> None:
    """Reject a resealed inner orchestration that changes its v1 or authority contract."""
    if orchestration.get("schema") != SCHEMA:
        raise CrossLayerObligationPackageError("package_orchestration_schema_invalid")
    composition = orchestration.get("composition")
    currentness = composition.get("qualification_currentness") if isinstance(composition, Mapping) else None
    if not isinstance(currentness, Mapping):
        raise CrossLayerObligationPackageError("package_orchestration_currentness_missing")
    state = currentness.get("state")
    if state not in ("CURRENT_REPLAY_VERIFIED", "BLOCKED_INVALIDATED"):
        raise CrossLayerObligationPackageError("package_orchestration_currentness_invalid")
    expected_authority = {
        "execution_replay_verified": True,
        "qualification_currently_replayed": state == "CURRENT_REPLAY_VERIFIED",
        "epistemic_evidence_accepted": False,
        "proposition_truth_established": False,
        "audit_decision_authority": False,
        "allow_deny_authority": False,
        "release_approval": False,
        "production_approval": False,
        "downstream_authorization": "NOT_EVALUATED",
    }
    if orchestration.get("authority") != expected_authority:
        raise CrossLayerObligationPackageError("package_orchestration_authority_claim_invalid")
    bracket = orchestration.get("execution_replay_bracket")
    if not isinstance(bracket, Mapping) or bracket.get("atomic_cross_store_snapshot") is not False:
        raise CrossLayerObligationPackageError("package_orchestration_atomicity_claim_invalid")


def _validate_provenance_package_contract(provenance: Mapping[str, Any]) -> None:
    """Enforce M7.5.26's non-authority and replay claims in a sealed package."""
    if provenance.get("snapshot_identity_assurance") != "SOURCE_STATE_REPLAY_VERIFIED":
        raise CrossLayerObligationPackageError("package_source_state_replay_not_verified")
    source_state = provenance.get("source_state_verification")
    if (
        not isinstance(source_state, Mapping)
        or source_state.get("status") != "SOURCE_STATE_REPLAY_VERIFIED"
        or source_state.get("source_state_replay_verified") is not True
        or source_state.get("worktree_clean_at_replay") is not True
    ):
        raise CrossLayerObligationPackageError("package_source_state_status_invalid")
    if provenance.get("atomic_cross_store_snapshot") is not False:
        raise CrossLayerObligationPackageError("package_provenance_atomicity_claim_invalid")
    if provenance.get("trust_anchor") != "NONE":
        raise CrossLayerObligationPackageError("package_provenance_trust_anchor_claim_invalid")
    if provenance.get("external_lfs_payload_verified") is not False:
        raise CrossLayerObligationPackageError("package_external_lfs_claim_invalid")
    if provenance.get("recursive_submodule_state_verified") is not False:
        raise CrossLayerObligationPackageError("package_submodule_claim_invalid")
    expected_authority = {
        "evidence_accepted": False,
        "proposition_truth_established": False,
        "graph_completeness_established": False,
        "assurance_success_established": False,
        "audit_decision_authority": False,
        "allow_deny_authority": False,
        "release_approval": False,
        "production_approval": False,
    }
    if provenance.get("authority") != expected_authority:
        raise CrossLayerObligationPackageError("package_provenance_authority_claim_invalid")


def verify_persisted_cross_layer_obligation_package(
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
    """Build a strict package using the exact single-pass M7.5.24 operation context."""
    if not isinstance(source_manifest, Mapping):
        raise CrossLayerObligationPackageError("source_manifest_must_be_a_mapping")
    source = source_manifest.get("source")
    expected_revision = source.get("commit_oid") if isinstance(source, Mapping) else None
    if not isinstance(expected_revision, str) or not expected_revision.strip():
        raise CrossLayerObligationPackageError("verified_manifest_commit_oid_required")

    orchestration, context = _run_persisted_cross_layer_obligation_composition(
        execution_reconciliation_id,
        qualification_record_id,
        execution_reconciliation_store=execution_reconciliation_store,
        dossier_id=dossier_id,
        claim=claim,
        plan=plan,
        coverage_manifest=coverage_manifest,
        source_manifest=source_manifest,
        inventory=inventory,
        execution_report=execution_report,
        repository_root=repository_root,
        assurance_store=assurance_store,
        epistemic_store=epistemic_store,
        dossier_store=dossier_store,
        qualification_reconciliation_store=qualification_reconciliation_store,
        qualification_check_store=qualification_check_store,
        consumer_id=consumer_id,
        operation=operation,
        current_qualification=current_qualification,
        current_observation_bundle=current_observation_bundle,
        defeaters=defeaters,
        _include_context=True,
    )
    try:
        provenance = verify_cross_layer_snapshot_provenance(
            context["source_manifest"],
            context["execution_reconciliation"],
            context["qualification_reconciliation"],
            context["qualification"],
            context["observation_bundle"],
            orchestration,
            repository_root=context["repository_root"],
            expected_source_revision=expected_revision,
        )
    except (CrossLayerSnapshotProvenanceError, OSError, ValueError, TypeError) as exc:
        raise CrossLayerObligationPackageError(
            "strict_source_state_replay_or_binding_failed:" + type(exc).__name__
        ) from exc

    _validate_provenance_package_contract(provenance)
    qualification_state = orchestration["composition"]["qualification_currentness"]["state"]
    if provenance.get("qualification_currentness") != qualification_state:
        raise CrossLayerObligationPackageError("qualification_currentness_binding_mismatch")

    package_payload = {
        "schema": PACKAGE_SCHEMA,
        "orchestration": orchestration,
        "provenance": provenance,
        "atomic_cross_store_snapshot": False,
        "trust_anchor": "NONE",
        "authority": {
            "evidence_accepted": False,
            "proposition_truth_established": False,
            "graph_completeness_established": False,
            "assurance_success_established": False,
            "audit_decision_authority": False,
            "allow_deny_authority": False,
            "release_approval": False,
            "production_approval": False,
            "downstream_authorization": "NOT_EVALUATED",
        },
    }
    return {**package_payload, "package_sha256": _digest(package_payload)}


def verify_cross_layer_obligation_package_envelope(
    package: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify package and inner seals only; this does not replay Git or persisted stores."""
    if not isinstance(package, Mapping):
        raise TypeError("cross_layer_obligation_package_must_be_a_mapping")
    submitted = dict(package)
    package_id = submitted.get("package_sha256")
    payload = {key: value for key, value in submitted.items() if key != "package_sha256"}
    if (
        submitted.get("schema") != PACKAGE_SCHEMA
        or not isinstance(package_id, str)
        or package_id != _digest(payload)
    ):
        raise CrossLayerObligationPackageError("package_digest_mismatch")

    orchestration = submitted.get("orchestration")
    provenance = submitted.get("provenance")
    if not isinstance(orchestration, Mapping) or not isinstance(provenance, Mapping):
        raise CrossLayerObligationPackageError("package_inner_envelopes_missing")
    _validate_orchestration_package_contract(orchestration)
    try:
        orchestration_check = verify_orchestrated_obligation_composition(orchestration)
        provenance_check = verify_cross_layer_snapshot_provenance_envelope(provenance)
    except (ObligationCompositionOrchestrationError, CrossLayerSnapshotProvenanceError) as exc:
        raise CrossLayerObligationPackageError("package_inner_seal_invalid:" + str(exc)) from exc

    _validate_provenance_package_contract(provenance)
    if provenance.get("orchestration_sha256") != orchestration.get("orchestration_sha256"):
        raise CrossLayerObligationPackageError("package_orchestration_binding_mismatch")
    composition = orchestration.get("composition")
    currentness = composition.get("qualification_currentness") if isinstance(composition, Mapping) else None
    if not isinstance(currentness, Mapping) or provenance.get("qualification_currentness") != currentness.get("state"):
        raise CrossLayerObligationPackageError("package_qualification_currentness_mismatch")
    if submitted.get("atomic_cross_store_snapshot") is not False:
        raise CrossLayerObligationPackageError("package_atomicity_claim_invalid")
    if submitted.get("trust_anchor") != "NONE":
        raise CrossLayerObligationPackageError("package_trust_anchor_claim_invalid")
    authority = submitted.get("authority")
    expected_authority = {
        "evidence_accepted": False,
        "proposition_truth_established": False,
        "graph_completeness_established": False,
        "assurance_success_established": False,
        "audit_decision_authority": False,
        "allow_deny_authority": False,
        "release_approval": False,
        "production_approval": False,
        "downstream_authorization": "NOT_EVALUATED",
    }
    if authority != expected_authority:
        raise CrossLayerObligationPackageError("package_authority_claim_invalid")
    return {
        "package_sha256": package_id,
        "orchestration_sha256": orchestration_check["orchestration_sha256"],
        "cross_layer_snapshot_identity_sha256": provenance_check["cross_layer_snapshot_identity_sha256"],
        "package_content_integrity": True,
        "source_state_replay_performed_by_this_check": False,
        "qualification_currentness": provenance["qualification_currentness"],
        "atomic_cross_store_snapshot": False,
        "downstream_authorization": "NOT_EVALUATED",
    }

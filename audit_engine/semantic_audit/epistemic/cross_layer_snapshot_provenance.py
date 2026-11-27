"""M7.5.26 cross-layer snapshot identity and provenance contract."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from tools.ae32c_source_snapshot_manifest import SnapshotError, verify_verified_manifest_data

SCHEMA = "ae32c/cross-layer-snapshot-provenance/v1"
SOURCE_MANIFEST_SCHEMA = "ae32c/source-snapshot-manifest/v1"


class CrossLayerSnapshotProvenanceError(ValueError):
    """Cross-layer snapshot provenance is incomplete or inconsistent."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any], identity_key: str, error: str) -> str:
    identity = value.get(identity_key)
    payload = {key: item for key, item in value.items() if key != identity_key}
    if not isinstance(identity, str) or identity != _digest(payload):
        raise CrossLayerSnapshotProvenanceError(error)
    return identity


def _require_digest(value: Any, field: str, error: str) -> str:
    candidate = value.get(field) if isinstance(value, Mapping) else None
    if (not isinstance(candidate, str) or len(candidate) != 64
            or any(ch not in "0123456789abcdef" for ch in candidate)):
        raise CrossLayerSnapshotProvenanceError(error)
    return candidate


def _verify_manifest_structure(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("manifest_schema") != SOURCE_MANIFEST_SCHEMA:
        raise CrossLayerSnapshotProvenanceError("source_manifest_schema_invalid")
    manifest_id = _sealed(manifest, "manifest_sha256", "source_manifest_digest_mismatch")
    if manifest.get("status") != "VERIFIED":
        raise CrossLayerSnapshotProvenanceError("source_manifest_not_verified")
    source, inventory = manifest.get("source"), manifest.get("source_inventory")
    verification, materialization = manifest.get("verification"), manifest.get("materialization")
    if not all(isinstance(item, Mapping) for item in (source, inventory, verification, materialization)):
        raise CrossLayerSnapshotProvenanceError("source_manifest_components_missing")
    entries = inventory.get("entries")
    if not isinstance(entries, list) or inventory.get("entry_count") != len(entries):
        raise CrossLayerSnapshotProvenanceError("source_inventory_collection_invalid")
    if inventory.get("sha256") != _digest(entries):
        raise CrossLayerSnapshotProvenanceError("source_inventory_digest_mismatch")
    if source.get("source_inventory_sha256") != inventory.get("sha256"):
        raise CrossLayerSnapshotProvenanceError("source_inventory_binding_mismatch")
    source_id = _require_digest(manifest, "source_snapshot_id", "source_snapshot_id_invalid")
    if source_id != _digest(dict(source)):
        raise CrossLayerSnapshotProvenanceError("source_snapshot_id_mismatch")
    if verification.get("status") != "VERIFIED":
        raise CrossLayerSnapshotProvenanceError("source_manifest_verification_not_verified")
    if verification.get("source_snapshot_id_at_verification") != source_id:
        raise CrossLayerSnapshotProvenanceError("verified_snapshot_identity_mismatch")
    if verification.get("source_inventory_sha256_at_verification") != inventory.get("sha256"):
        raise CrossLayerSnapshotProvenanceError("verified_inventory_identity_mismatch")
    if verification.get("worktree_clean_at_verification") is not True:
        raise CrossLayerSnapshotProvenanceError("verified_worktree_cleanliness_missing")
    worktree = materialization.get("worktree")
    if (materialization.get("status") != "CLEAN" or not isinstance(worktree, Mapping)
            or worktree.get("clean") is not True):
        raise CrossLayerSnapshotProvenanceError("source_materialization_not_clean")
    if (materialization.get("checkout_commit_oid") != source.get("commit_oid")
            or materialization.get("checkout_root_tree_oid") != source.get("root_tree_oid")):
        raise CrossLayerSnapshotProvenanceError("source_materialization_identity_mismatch")
    if not isinstance(source.get("repository"), str) or not source["repository"].strip():
        raise CrossLayerSnapshotProvenanceError("source_repository_identity_missing")
    return {
        "manifest_sha256": manifest_id, "source_snapshot_id": source_id,
        "commit_oid": source.get("commit_oid"), "root_tree_oid": source.get("root_tree_oid"),
        "source_inventory_sha256": inventory.get("sha256"), "repository": source.get("repository"),
    }


def verify_cross_layer_snapshot_provenance(
    source_manifest: Mapping[str, Any],
    execution_reconciliation: Mapping[str, Any],
    qualification_reconciliation: Mapping[str, Any],
    qualification: Mapping[str, Any],
    observation_bundle: Mapping[str, Any],
    orchestration_result: Mapping[str, Any],
    *,
    repository_root: str | Path | None = None,
    expected_source_revision: str | None = None,
) -> dict[str, Any]:
    """Verify common snapshot bindings; optionally reconstruct the live Git source state."""
    inputs = (source_manifest, execution_reconciliation, qualification_reconciliation,
              qualification, observation_bundle, orchestration_result)
    if not all(isinstance(item, Mapping) for item in inputs):
        raise TypeError("all_provenance_inputs_must_be_mappings")
    manifest = _verify_manifest_structure(source_manifest)
    execution_id = _sealed(execution_reconciliation, "reconciliation_sha256",
                           "execution_reconciliation_digest_mismatch")
    qualification_reconciliation_id = _sealed(
        qualification_reconciliation, "reconciliation_sha256",
        "qualification_reconciliation_digest_mismatch")
    qualification_id = _sealed(qualification, "qualification_sha256", "qualification_digest_mismatch")
    bundle_id = _sealed(observation_bundle, "bundle_sha256", "observation_bundle_digest_mismatch")
    source_id, manifest_id = manifest["source_snapshot_id"], manifest["manifest_sha256"]

    for label, artifact in (("execution_reconciliation", execution_reconciliation),
                            ("qualification_reconciliation", qualification_reconciliation),
                            ("qualification", qualification), ("observation_bundle", observation_bundle)):
        if artifact.get("source_snapshot_id") != source_id:
            raise CrossLayerSnapshotProvenanceError("snapshot_binding_mismatch:" + label)
    if execution_reconciliation.get("source_manifest_sha256") != manifest_id:
        raise CrossLayerSnapshotProvenanceError("execution_source_manifest_binding_mismatch")
    if qualification_reconciliation.get("qualification_sha256") != qualification_id:
        raise CrossLayerSnapshotProvenanceError("qualification_reconciliation_qualification_binding_mismatch")
    if qualification_reconciliation.get("observation_bundle_sha256") != bundle_id:
        raise CrossLayerSnapshotProvenanceError("qualification_reconciliation_bundle_binding_mismatch")
    if qualification.get("observation_bundle_sha256") != bundle_id:
        raise CrossLayerSnapshotProvenanceError("qualification_bundle_binding_mismatch")
    if qualification_reconciliation.get("plan_sha256") != observation_bundle.get("plan_sha256"):
        raise CrossLayerSnapshotProvenanceError("qualification_bundle_plan_binding_mismatch")
    if execution_reconciliation.get("plan_sha256") != qualification_reconciliation.get("plan_sha256"):
        raise CrossLayerSnapshotProvenanceError("cross_layer_plan_binding_mismatch")
    if execution_reconciliation.get("coverage_manifest_sha256") != qualification_reconciliation.get("coverage_manifest_sha256"):
        raise CrossLayerSnapshotProvenanceError("cross_layer_coverage_manifest_binding_mismatch")
    if execution_reconciliation.get("claim_id") != qualification_reconciliation.get("claim_id"):
        raise CrossLayerSnapshotProvenanceError("cross_layer_claim_binding_mismatch")

    composition = orchestration_result.get("composition")
    if not isinstance(composition, Mapping):
        raise CrossLayerSnapshotProvenanceError("orchestration_composition_missing")
    composition_id = _sealed(composition, "composition_sha256", "composition_digest_mismatch")
    orchestration_id = _sealed(orchestration_result, "orchestration_sha256", "orchestration_digest_mismatch")
    if composition.get("source_snapshot_id") != source_id:
        raise CrossLayerSnapshotProvenanceError("composition_snapshot_binding_mismatch")
    if composition.get("execution_reconciliation_sha256") != execution_id:
        raise CrossLayerSnapshotProvenanceError("composition_execution_binding_mismatch")
    if composition.get("qualification_reconciliation_sha256") != qualification_reconciliation_id:
        raise CrossLayerSnapshotProvenanceError("composition_qualification_binding_mismatch")
    if composition.get("plan_sha256") != execution_reconciliation.get("plan_sha256"):
        raise CrossLayerSnapshotProvenanceError("composition_plan_binding_mismatch")
    if composition.get("coverage_manifest_sha256") != execution_reconciliation.get("coverage_manifest_sha256"):
        raise CrossLayerSnapshotProvenanceError("composition_coverage_binding_mismatch")
    if orchestration_result.get("execution_reconciliation_sha256") != execution_id:
        raise CrossLayerSnapshotProvenanceError("orchestration_execution_binding_mismatch")
    if orchestration_result.get("qualification_reconciliation_sha256") != qualification_reconciliation_id:
        raise CrossLayerSnapshotProvenanceError("orchestration_qualification_binding_mismatch")

    replay, bracket = orchestration_result.get("execution_replay"), orchestration_result.get("execution_replay_bracket")
    consumer = orchestration_result.get("qualification_consumer_result")
    if (not isinstance(replay, Mapping) or replay.get("reconciliation_sha256") != execution_id
            or replay.get("ledger_integrity") is not True or replay.get("semantic_replay") is not True):
        raise CrossLayerSnapshotProvenanceError("execution_replay_not_verified")
    if (not isinstance(bracket, Mapping) or bracket.get("reconciliation_sha256") != execution_id
            or bracket.get("pre_qualification_replay_verified") is not True
            or bracket.get("post_qualification_replay_verified") is not True
            or bracket.get("results_identical") is not True
            or bracket.get("atomic_cross_store_snapshot") is not False):
        raise CrossLayerSnapshotProvenanceError("execution_replay_bracket_invalid")
    if (not isinstance(consumer, Mapping)
            or consumer.get("record_id") != qualification_reconciliation_id
            or consumer.get("downstream_authorization") != "NOT_EVALUATED"):
        raise CrossLayerSnapshotProvenanceError("qualification_consumer_binding_invalid")
    currentness = composition.get("qualification_currentness")
    if (not isinstance(currentness, Mapping)
            or currentness.get("state") not in ("CURRENT_REPLAY_VERIFIED", "BLOCKED_INVALIDATED")):
        raise CrossLayerSnapshotProvenanceError("qualification_currentness_state_invalid")

    source_state = {
        "status": "NOT_PERFORMED", "source_state_replay_verified": False,
        "commit_oid": manifest["commit_oid"], "root_tree_oid": manifest["root_tree_oid"],
        "source_inventory_sha256": manifest["source_inventory_sha256"],
    }
    assurance_level = "DECLARED_ONLY"
    if repository_root is not None:
        try:
            replayed = verify_verified_manifest_data(
                repository_root, dict(source_manifest), expected_source_revision=expected_source_revision)
        except (SnapshotError, OSError, ValueError, TypeError) as exc:
            raise CrossLayerSnapshotProvenanceError("source_state_replay_failed:" + type(exc).__name__) from exc
        source_state = {"status": "SOURCE_STATE_REPLAY_VERIFIED", **replayed}
        assurance_level = "SOURCE_STATE_REPLAY_VERIFIED"

    identity_payload = {
        "schema": SCHEMA, "source_snapshot_id": source_id,
        "source_manifest_sha256": manifest_id,
        "source_inventory_sha256": manifest["source_inventory_sha256"],
        "execution_reconciliation_sha256": execution_id,
        "qualification_reconciliation_sha256": qualification_reconciliation_id,
        "qualification_sha256": qualification_id, "observation_bundle_sha256": bundle_id,
        "composition_sha256": composition_id, "orchestration_sha256": orchestration_id,
        "claim_id": execution_reconciliation.get("claim_id"),
        "plan_sha256": execution_reconciliation.get("plan_sha256"),
        "coverage_manifest_sha256": execution_reconciliation.get("coverage_manifest_sha256"),
    }
    return {
        **identity_payload,
        "cross_layer_snapshot_identity_sha256": _digest(identity_payload),
        "provenance_status": "COMPLETE", "snapshot_identity_assurance": assurance_level,
        "source_state_verification": source_state,
        "qualification_currentness": currentness["state"],
        "atomic_cross_store_snapshot": False,
        "external_lfs_payload_verified": False,
        "recursive_submodule_state_verified": False,
        "trust_anchor": "NONE",
        "authority": {
            "evidence_accepted": False, "proposition_truth_established": False,
            "graph_completeness_established": False, "assurance_success_established": False,
            "audit_decision_authority": False, "allow_deny_authority": False,
            "release_approval": False, "production_approval": False,
        },
        "limitations": [
            "Content hashes and matching identifiers do not authenticate artifact producers",
            "Git source-state replay is a point-in-time check, not a distributed snapshot transaction",
            "Independent SQLite ledgers are not coordinated by this contract",
            "External Git LFS payload bytes and recursive submodule contents are not verified",
            "A later mutation can occur after source-state replay",
        ],
    }


def verify_cross_layer_snapshot_provenance_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Verify only the content seal; this does not replay the repository or stores."""
    if not isinstance(envelope, Mapping):
        raise TypeError("provenance_envelope_must_be_a_mapping")
    identity = envelope.get("cross_layer_snapshot_identity_sha256")
    identity_fields = {key: envelope.get(key) for key in (
        "schema", "source_snapshot_id", "source_manifest_sha256", "source_inventory_sha256",
        "execution_reconciliation_sha256", "qualification_reconciliation_sha256",
        "qualification_sha256", "observation_bundle_sha256", "composition_sha256",
        "orchestration_sha256", "claim_id", "plan_sha256", "coverage_manifest_sha256")}
    if (envelope.get("schema") != SCHEMA or not isinstance(identity, str)
            or identity != _digest(identity_fields)):
        raise CrossLayerSnapshotProvenanceError("provenance_envelope_digest_mismatch")
    return {
        "cross_layer_snapshot_identity_sha256": identity,
        "content_binding_verified": True, "source_state_replay_performed": False,
        "atomic_cross_store_snapshot": False, "downstream_authorization": "NOT_EVALUATED",
    }

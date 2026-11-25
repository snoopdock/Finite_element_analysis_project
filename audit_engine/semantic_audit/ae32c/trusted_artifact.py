"""Validate untrusted AE-32C producer artifacts for a trusted publisher.

This module validates integrity and cross-bindings only. It does not establish
that producer code computed semantically correct findings.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from audit_engine.semantic_audit.ae32c.publication import build_run_record
from tools.ae32c_graph_snapshot import verify_graph_manifest, GraphSnapshotError

SOURCE_SCHEMA = "ae32c/source-snapshot-manifest/v1"
POLICY_SCHEMA = "ae32c/trusted-publication-config/v1"
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
_HEX = re.compile(r"^[0-9a-f]+$")


class TrustedArtifactError(ValueError):
    """An upstream artifact cannot be trusted as a publication input."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TrustedArtifactError("canonical_json_invalid") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TrustedArtifactError("duplicate_json_key:" + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise TrustedArtifactError("non_finite_json_number:" + value)


def parse_manifest(raw: bytes, *, label: str) -> dict[str, Any]:
    if not isinstance(raw, bytes) or len(raw) > MAX_MANIFEST_BYTES:
        raise TrustedArtifactError(label + "_size_invalid")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"),
                           object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except TrustedArtifactError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise TrustedArtifactError(label + "_json_invalid") from exc
    if not isinstance(value, dict):
        raise TrustedArtifactError(label + "_root_not_object")
    return value


def _require_hex(value: Any, lengths: tuple[int, ...], label: str) -> None:
    if not isinstance(value, str) or len(value) not in lengths or not _HEX.fullmatch(value):
        raise TrustedArtifactError(label + "_invalid")


def _verify_source_manifest(manifest: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    if manifest.get("manifest_schema") != SOURCE_SCHEMA:
        raise TrustedArtifactError("source_manifest_schema_invalid")
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != digest(payload):
        raise TrustedArtifactError("source_manifest_digest_invalid")
    if manifest.get("status") != "VERIFIED":
        raise TrustedArtifactError("source_manifest_not_verified")
    source = manifest.get("source")
    event = manifest.get("event")
    verification = manifest.get("verification")
    inventory = manifest.get("source_inventory")
    run = manifest.get("run")
    if not all(isinstance(x, dict) for x in (source, event, verification, inventory, run)):
        raise TrustedArtifactError("source_manifest_fields_missing")
    commit = source.get("commit_oid")
    tree = source.get("root_tree_oid")
    algorithm = source.get("commit_oid_algorithm")
    lengths = (40,) if algorithm == "sha1" else (64,) if algorithm == "sha256" else ()
    _require_hex(commit, lengths, "source_commit_oid")
    _require_hex(tree, lengths, "source_root_tree_oid")
    _require_hex(source.get("source_inventory_sha256"), (64,), "source_inventory_digest")
    if manifest.get("source_snapshot_id") != digest(source):
        raise TrustedArtifactError("source_snapshot_identity_invalid")
    entries = inventory.get("entries")
    if not isinstance(entries, list) or inventory.get("entry_count") != len(entries):
        raise TrustedArtifactError("source_inventory_count_invalid")
    if inventory.get("sha256") != digest(entries):
        raise TrustedArtifactError("source_inventory_digest_invalid")
    if inventory.get("sha256") != source.get("source_inventory_sha256"):
        raise TrustedArtifactError("source_inventory_source_binding_invalid")
    paths = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"]:
            raise TrustedArtifactError("source_inventory_entry_invalid")
        paths.append(entry["path"])
    if len(paths) != len(set(paths)):
        raise TrustedArtifactError("source_inventory_duplicate_path")
    if paths != sorted(paths, key=lambda item: item.encode("utf-8")):
        raise TrustedArtifactError("source_inventory_order_invalid")
    if verification.get("status") != "VERIFIED":
        raise TrustedArtifactError("source_postflight_not_verified")
    if verification.get("source_snapshot_id_at_verification") != manifest.get("source_snapshot_id"):
        raise TrustedArtifactError("source_postflight_identity_mismatch")
    if verification.get("source_inventory_sha256_at_verification") != inventory.get("sha256"):
        raise TrustedArtifactError("source_postflight_inventory_mismatch")
    if verification.get("worktree_clean_at_verification") is not True:
        raise TrustedArtifactError("source_postflight_worktree_not_clean")
    if source.get("repository") != expected.get("repository"):
        raise TrustedArtifactError("source_repository_mismatch")
    if source.get("commit_oid") != expected.get("head_sha"):
        raise TrustedArtifactError("source_revision_mismatch")
    if event.get("repository") != expected.get("repository"):
        raise TrustedArtifactError("event_repository_mismatch")
    if event.get("event_name") != "push" or expected.get("event") != "push":
        raise TrustedArtifactError("event_not_authorized")
    if event.get("ref") != expected.get("ref"):
        raise TrustedArtifactError("event_ref_mismatch")
    if expected.get("ref") != "refs/heads/" + str(expected.get("default_branch")):
        raise TrustedArtifactError("event_ref_not_default_branch")
    if expected.get("head_branch") != expected.get("default_branch"):
        raise TrustedArtifactError("head_branch_not_default_branch")
    if expected.get("head_repository") != expected.get("repository"):
        raise TrustedArtifactError("head_repository_not_trusted")
    if str(run.get("run_id")) != str(expected.get("run_id")):
        raise TrustedArtifactError("workflow_run_id_mismatch")
    if str(run.get("run_attempt")) != str(expected.get("run_attempt")):
        raise TrustedArtifactError("workflow_run_attempt_mismatch")
    authority = manifest.get("authority")
    if not isinstance(authority, dict) or authority.get("production_approval") is not False:
        raise TrustedArtifactError("source_authority_flag_invalid")


def validate_publication_artifact(
    source_manifest: Mapping[str, Any],
    graph_manifest: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate manifests against independently retrieved GitHub run metadata.

    The caller must independently enforce the allowlisted workflow ID and
    successful upstream conclusion. This function restricts current candidates
    to same-repository pushes on the protected default branch.
    """
    required = ("repository", "default_branch", "head_branch", "head_repository",
                "ref", "event", "head_sha", "run_id", "run_attempt", "run_number",
                "workflow_id", "workflow_path", "conclusion")
    if any(expected.get(key) in (None, "") for key in required):
        raise TrustedArtifactError("upstream_run_metadata_missing")
    if expected["conclusion"] != "success":
        raise TrustedArtifactError("upstream_workflow_not_successful")
    _verify_source_manifest(source_manifest, expected)
    try:
        verify_graph_manifest(dict(graph_manifest))
    except (GraphSnapshotError, ValueError, TypeError, KeyError) as exc:
        raise TrustedArtifactError("graph_manifest_invalid:" + str(exc)) from exc
    if graph_manifest.get("status") != "CAPTURED":
        raise TrustedArtifactError("graph_manifest_not_captured")
    if graph_manifest.get("source_snapshot_id") != source_manifest.get("source_snapshot_id"):
        raise TrustedArtifactError("graph_source_snapshot_mismatch")
    source = source_manifest["source"]
    graph_source = graph_manifest.get("source", {})
    if (graph_source.get("repository") != source.get("repository")
            or graph_source.get("commit_oid") != source.get("commit_oid")
            or graph_source.get("root_tree_oid") != source.get("root_tree_oid")):
        raise TrustedArtifactError("graph_source_identity_mismatch")
    graph_authority = graph_manifest.get("authority")
    if not isinstance(graph_authority, dict) or graph_authority.get("production_approval") is not False:
        raise TrustedArtifactError("graph_authority_flag_invalid")
    coverage = graph_manifest.get("coverage", {})
    source_count = len(source_manifest["source_inventory"]["entries"])
    if (coverage.get("source_unit_count") != source_count
            or len(coverage.get("source_units", [])) != source_count):
        raise TrustedArtifactError("graph_source_coverage_denominator_mismatch")
    represented = coverage.get("represented_count")
    excluded = coverage.get("excluded_count")
    unaccounted = coverage.get("unaccounted_count")
    if not all(isinstance(x, int) and x >= 0 for x in (represented, excluded, unaccounted)):
        raise TrustedArtifactError("graph_coverage_counts_invalid")
    if represented + excluded + unaccounted != source_count:
        raise TrustedArtifactError("graph_coverage_counts_do_not_reconcile")
    complete = (coverage.get("status") == "COMPLETE_WITH_DECLARED_EXCLUSIONS"
                and unaccounted == 0)
    builder = graph_manifest.get("builder")
    if not isinstance(builder, dict):
        raise TrustedArtifactError("graph_builder_identity_missing")
    config = {
        "schema": POLICY_SCHEMA,
        "policy_version": "ae32c-trusted-publisher/v1",
        "workflow_id": int(expected["workflow_id"]),
        "workflow_path": str(expected["workflow_path"]),
        "producer_revision": str(expected["head_sha"]),
        "graph_builder": builder,
        "rule_registry_sha256": graph_manifest["rule_registry_sha256"],
        "source_event": "push",
        "source_ref": str(expected["ref"]),
    }
    record = build_run_record(
        repository=str(expected["repository"]),
        source_revision=str(source["commit_oid"]),
        source_snapshot_id=str(source_manifest["source_snapshot_id"]),
        graph_snapshot_id=str(graph_manifest["graph_snapshot_id"]),
        rule_registry_sha256=str(graph_manifest["rule_registry_sha256"]),
        finding_ledger_sha256=str(graph_manifest["finding_ledger_sha256"]),
        configuration_sha256=digest(config),
        workflow_run_id=int(expected["run_id"]),
        run_number=int(expected["run_number"]),
        run_attempt=int(expected["run_attempt"]),
        outcome="SUCCEEDED" if complete else "INCOMPLETE",
    )
    return {
        "record": record,
        "current_eligible": complete,
        "eligibility_reason": "complete_declared_coverage" if complete else "graph_coverage_incomplete",
        "configuration": config,
        "configuration_sha256": digest(config),
    }

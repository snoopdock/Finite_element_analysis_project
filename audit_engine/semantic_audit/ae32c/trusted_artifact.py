"""Validate untrusted AE-32C producer artifacts for a trusted publisher.

This module validates integrity and cross-bindings only. It does not establish
that producer code computed semantically correct findings.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from typing import Any, Mapping

from audit_engine.semantic_audit.ae32c.publication import build_run_record
from tools.ae32c_graph_snapshot import verify_graph_manifest, GraphSnapshotError

SOURCE_SCHEMA = "ae32c/source-snapshot-manifest/v1"
POLICY_SCHEMA = "ae32c/trusted-publication-config/v1"
ALLOWED_PRODUCER_WORKFLOW_ID = 430355742
ALLOWED_PRODUCER_WORKFLOW_PATH = ".github/workflows/ae32c_source_snapshot_manifest.yml"
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 100
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


def parse_artifact_archive(raw: bytes) -> dict[str, dict[str, Any]]:
    """Safely read the two expected JSON members from an untrusted ZIP artifact."""
    if not isinstance(raw, bytes) or len(raw) > MAX_ARCHIVE_BYTES:
        raise TrustedArtifactError("artifact_archive_size_invalid")
    expected_names = {"source-snapshot-manifest.json", "graph-snapshot-manifest.json"}
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            if len(names) != 2 or len(set(names)) != 2 or set(names) != expected_names:
                raise TrustedArtifactError("artifact_archive_member_set_invalid")
            total_uncompressed = 0
            payloads: dict[str, bytes] = {}
            for item in members:
                name = item.filename
                if (name.startswith(("/", chr(92))) or chr(92) in name
                        or any(part in ("", ".", "..") for part in name.split("/"))):
                    raise TrustedArtifactError("artifact_archive_path_invalid:" + name)
                mode = item.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if item.is_dir() or file_type not in (0, stat.S_IFREG):
                    raise TrustedArtifactError("artifact_archive_member_type_invalid:" + name)
                if item.flag_bits & 0x1:
                    raise TrustedArtifactError("artifact_archive_encrypted_member:" + name)
                if item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise TrustedArtifactError("artifact_archive_compression_invalid:" + name)
                if item.file_size < 0 or item.file_size > MAX_MANIFEST_BYTES:
                    raise TrustedArtifactError("artifact_archive_member_size_invalid:" + name)
                total_uncompressed += item.file_size
                if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise TrustedArtifactError("artifact_archive_uncompressed_size_invalid")
                if item.file_size and (item.compress_size == 0
                        or item.file_size / item.compress_size > MAX_ARCHIVE_COMPRESSION_RATIO):
                    raise TrustedArtifactError("artifact_archive_compression_ratio_invalid:" + name)
                payload = archive.read(item)
                if len(payload) != item.file_size:
                    raise TrustedArtifactError("artifact_archive_member_length_mismatch:" + name)
                payloads[name] = payload
    except TrustedArtifactError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError, RuntimeError) as exc:
        raise TrustedArtifactError("artifact_archive_invalid") from exc
    return {
        "source": parse_manifest(payloads["source-snapshot-manifest.json"], label="source"),
        "graph": parse_manifest(payloads["graph-snapshot-manifest.json"], label="graph"),
    }


def validate_manifest_schemas(
    source_manifest: Mapping[str, Any],
    graph_manifest: Mapping[str, Any],
    *,
    source_schema: Mapping[str, Any],
    graph_schema: Mapping[str, Any],
) -> None:
    """Validate manifests against trusted local JSON Schemas, never artifact schemas."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from jsonschema.exceptions import SchemaError
    except ImportError as exc:
        raise TrustedArtifactError("jsonschema_dependency_missing") from exc
    for label, instance, schema in (
        ("source", source_manifest, source_schema),
        ("graph", graph_manifest, graph_schema),
    ):
        try:
            Draft202012Validator.check_schema(dict(schema))
            validator = Draft202012Validator(dict(schema), format_checker=FormatChecker())
            errors = sorted(
                validator.iter_errors(dict(instance)),
                key=lambda error: (tuple(map(str, error.absolute_path)), error.message),
            )
        except SchemaError as exc:
            raise TrustedArtifactError(label + "_trusted_schema_invalid:" + str(exc)) from exc
        if errors:
            first = errors[0]
            path = "/".join(str(part) for part in first.absolute_path)
            raise TrustedArtifactError(
                label + "_schema_validation_failed:" + path + ":" + first.message
            )

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
        if (not isinstance(entry.get("mode"), str)
                or not re.fullmatch(r"[0-7]{6}", entry["mode"])
                or entry.get("object_type") not in ("blob", "commit")
                or entry.get("materialization_kind") not in ("regular_file", "symlink", "gitlink_submodule")):
            raise TrustedArtifactError("source_inventory_entry_metadata_invalid:" + entry["path"])
        _require_hex(entry.get("git_object_oid"), lengths, "source_inventory_git_object_oid")
        content_sha = entry.get("content_sha256")
        if content_sha is not None:
            _require_hex(content_sha, (64,), "source_inventory_content_sha256")
        if entry["materialization_kind"] == "gitlink_submodule" and entry.get("object_type") != "commit":
            raise TrustedArtifactError("source_inventory_gitlink_type_invalid:" + entry["path"])
        if entry["materialization_kind"] != "gitlink_submodule" and entry.get("object_type") != "blob":
            raise TrustedArtifactError("source_inventory_blob_type_invalid:" + entry["path"])
        paths.append(entry["path"])
    if len(paths) != len(set(paths)):
        raise TrustedArtifactError("source_inventory_duplicate_path")
    if paths != sorted(paths, key=lambda item: item.encode("utf-8")):
        raise TrustedArtifactError("source_inventory_order_invalid")
    materialization = manifest.get("materialization")
    if not isinstance(materialization, dict) or materialization.get("status") != "CLEAN":
        raise TrustedArtifactError("source_materialization_not_clean")
    worktree = materialization.get("worktree")
    if (not isinstance(worktree, dict) or worktree.get("clean") is not True
            or worktree.get("changed_entry_count") != 0):
        raise TrustedArtifactError("source_materialization_worktree_not_clean")
    if (materialization.get("checkout_commit_oid") != commit
            or materialization.get("checkout_root_tree_oid") != tree):
        raise TrustedArtifactError("source_materialization_identity_mismatch")
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
    if (not isinstance(authority, dict)
            or authority.get("production_approval") is not False
            or authority.get("atomic_repository_snapshot_established") is not False
            or authority.get("graph_completeness_established") is not False):
        raise TrustedArtifactError("source_authority_flag_invalid")


def _verify_coverage_cross_binding(coverage: Mapping[str, Any], source_entries: list[dict[str, Any]]) -> None:
    """Reconcile every graph coverage row with the exact source inventory row."""
    units = coverage.get("source_units")
    if not isinstance(units, list) or len(units) != len(source_entries):
        raise TrustedArtifactError("graph_source_coverage_denominator_mismatch")
    expected_entries = {entry["path"]: entry for entry in source_entries}
    observed_paths: list[str] = []
    counts: dict[str, int] = {}
    unaccounted_paths: list[str] = []
    for unit in units:
        if not isinstance(unit, dict):
            raise TrustedArtifactError("graph_coverage_unit_invalid")
        path = unit.get("path")
        if not isinstance(path, str) or path not in expected_entries:
            raise TrustedArtifactError("graph_coverage_path_not_in_source_inventory")
        observed_paths.append(path)
        entry = expected_entries[path]
        if (unit.get("git_object_oid") != entry.get("git_object_oid")
                or unit.get("source_content_sha256") != entry.get("content_sha256")):
            raise TrustedArtifactError("graph_coverage_source_entry_mismatch:" + path)
        status = unit.get("status")
        if status not in {
            "represented", "excluded_symlink", "excluded_sensitive",
            "outside_declared_source_scope", "excluded_by_evidence_inventory",
            "unaccounted",
        }:
            raise TrustedArtifactError("graph_coverage_status_invalid:" + path)
        if status == "represented" and unit.get("reason") is not None:
            raise TrustedArtifactError("graph_represented_reason_must_be_null:" + path)
        if status != "represented" and (not isinstance(unit.get("reason"), str) or not unit["reason"]):
            raise TrustedArtifactError("graph_exclusion_reason_missing:" + path)
        counts[status] = counts.get(status, 0) + 1
        if status == "unaccounted":
            unaccounted_paths.append(path)
    if observed_paths != sorted(expected_entries, key=lambda item: item.encode("utf-8")):
        raise TrustedArtifactError("graph_coverage_source_path_set_or_order_mismatch")
    if coverage.get("status_counts") != dict(sorted(counts.items())):
        raise TrustedArtifactError("graph_coverage_status_counts_mismatch")
    represented = counts.get("represented", 0)
    excluded = sum(value for key, value in counts.items()
                   if key.startswith("excluded") or key == "outside_declared_source_scope")
    unaccounted = counts.get("unaccounted", 0)
    if (coverage.get("represented_count") != represented
            or coverage.get("excluded_count") != excluded
            or coverage.get("unaccounted_count") != unaccounted):
        raise TrustedArtifactError("graph_coverage_aggregate_counts_mismatch")
    limitations = coverage.get("limitations")
    if not isinstance(limitations, dict) or limitations.get("unaccounted_paths") != unaccounted_paths:
        raise TrustedArtifactError("graph_coverage_unaccounted_path_list_mismatch")
    extractor = coverage.get("extractor_coverage")
    if not isinstance(extractor, dict):
        raise TrustedArtifactError("graph_extractor_coverage_missing")
    python_ast = extractor.get("python_ast")
    workflow = extractor.get("workflow_static_scan")
    structured = extractor.get("structured_record_ingestion")
    module_identity = extractor.get("module_identity")
    if not all(isinstance(x, dict) for x in (python_ast, workflow, structured, module_identity)):
        raise TrustedArtifactError("graph_extractor_coverage_invalid")
    if (python_ast.get("failed_count") != python_ast.get("issue_count")
            or python_ast.get("candidate_count") != python_ast.get("parsed_count", 0) + python_ast.get("failed_count", 0)
            or workflow.get("status") != ("complete" if workflow.get("issue_count") == 0 else "incomplete")
            or structured.get("status") != ("complete" if structured.get("issue_count") == 0 else "incomplete")
            or module_identity.get("status") != ("complete" if module_identity.get("issue_count") == 0 else "incomplete")):
        raise TrustedArtifactError("graph_extractor_coverage_counts_inconsistent")


def validate_publication_artifact(
    source_manifest: Mapping[str, Any],
    graph_manifest: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate manifests against independently retrieved GitHub run metadata.

    The caller must validate mappings against schemas from the trusted publisher
    checkout before calling this function. Workflow identity and conclusion are
    independently enforced here.
    """
    required = ("repository", "default_branch", "head_branch", "head_repository",
                "ref", "event", "head_sha", "run_id", "run_attempt", "run_number",
                "workflow_id", "workflow_path", "conclusion")
    if any(expected.get(key) in (None, "") for key in required):
        raise TrustedArtifactError("upstream_run_metadata_missing")
    if expected["conclusion"] != "success":
        raise TrustedArtifactError("upstream_workflow_not_successful")
    try:
        workflow_id = int(expected["workflow_id"])
    except (TypeError, ValueError) as exc:
        raise TrustedArtifactError("upstream_workflow_id_invalid") from exc
    if (workflow_id != ALLOWED_PRODUCER_WORKFLOW_ID
            or expected["workflow_path"] != ALLOWED_PRODUCER_WORKFLOW_PATH):
        raise TrustedArtifactError("upstream_workflow_not_allowlisted")
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
    if (not isinstance(graph_authority, dict)
            or graph_authority.get("production_approval") is not False
            or graph_authority.get("graph_is_derived_from_source") is not True
            or graph_authority.get("graph_is_canonical_repository_authority") is not False
            or graph_authority.get("negative_findings_permitted_by_default") is not False):
        raise TrustedArtifactError("graph_authority_flag_invalid")
    identity = graph_manifest.get("identity", {})
    if (identity.get("source_commit_oid") != source.get("commit_oid")
            or identity.get("source_root_tree_oid") != source.get("root_tree_oid")):
        raise TrustedArtifactError("graph_identity_source_revision_mismatch")
    graph_meta = graph_manifest.get("graph", {})
    if any(not isinstance(graph_meta.get(key), int) or isinstance(graph_meta.get(key), bool)
           or graph_meta.get(key) < 0 for key in ("node_count", "edge_count")):
        raise TrustedArtifactError("graph_node_edge_count_invalid")
    coverage = graph_manifest.get("coverage", {})
    source_count = len(source_manifest["source_inventory"]["entries"])
    if coverage.get("source_unit_count") != source_count:
        raise TrustedArtifactError("graph_source_coverage_denominator_mismatch")
    _verify_coverage_cross_binding(
        coverage, source_manifest["source_inventory"]["entries"]
    )
    represented = coverage.get("represented_count")
    excluded = coverage.get("excluded_count")
    unaccounted = coverage.get("unaccounted_count")
    if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0
               for x in (represented, excluded, unaccounted)):
        raise TrustedArtifactError("graph_coverage_counts_invalid")
    complete = (coverage.get("status") == "COMPLETE_WITH_DECLARED_EXCLUSIONS"
                and unaccounted == 0)
    if complete:
        extractor = coverage["extractor_coverage"]
        if (extractor["python_ast"]["failed_count"] != 0
                or any(extractor[key]["issue_count"] != 0
                       or extractor[key]["status"] != "complete"
                       for key in ("workflow_static_scan", "structured_record_ingestion", "module_identity"))):
            raise TrustedArtifactError("graph_complete_status_conflicts_with_extractor_issues")
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

#!/usr/bin/env python3
"""Create a source-bound graph identity and coverage manifest (AE-32C Phase 2)."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
import sys
from typing import Any

# Direct script execution places tools/ rather than the repository root on sys.path.
_REPOSITORY_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_CODE_ROOT))

from audit_engine.semantic_audit.ae32c.rule_contracts import (
    build_finding_ledger,
    rule_registry,
    verify_finding_ledger,
)
from audit_engine.semantic_audit.ae32c.lfs_payload_verifier import verify_lfs_payloads

GRAPH_MANIFEST_SCHEMA = "ae32c/graph-snapshot-manifest/v1"
GRAPH_SCHEMA_VERSION = "semantic_graph/v1"
GRAPH_PROJECTION_VERSION = "ae32b/source-evidence-projection/v3"
GRAPH_BUILDER_VERSION = "ae32b/repository-evidence-tools/v1"


class GraphSnapshotError(RuntimeError):
    """A graph snapshot cannot be safely identified or accounted for."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _verify_source_manifest(manifest: dict[str, Any], expected_revision: str | None) -> None:
    if manifest.get("manifest_schema") != "ae32c/source-snapshot-manifest/v1":
        raise GraphSnapshotError("source_manifest_schema_invalid")
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != digest(payload):
        raise GraphSnapshotError("source_manifest_digest_mismatch")
    if manifest.get("status") != "VERIFIED" or manifest.get("verification", {}).get("status") != "VERIFIED":
        raise GraphSnapshotError("source_manifest_not_verified")
    source = manifest.get("source")
    if not isinstance(source, dict) or not source.get("commit_oid") or not source.get("root_tree_oid"):
        raise GraphSnapshotError("source_identity_missing")
    inventory = manifest.get("source_inventory")
    if not isinstance(inventory, dict) or not isinstance(inventory.get("entries"), list):
        raise GraphSnapshotError("source_inventory_invalid")
    if (inventory.get("entry_count") != len(inventory["entries"])
            or inventory.get("sha256") != digest(inventory["entries"])):
        raise GraphSnapshotError("source_inventory_digest_mismatch")
    if source.get("source_inventory_sha256") != inventory.get("sha256"):
        raise GraphSnapshotError("source_inventory_source_binding_mismatch")
    if manifest.get("source_snapshot_id") != digest(source):
        raise GraphSnapshotError("source_snapshot_identity_mismatch")
    if expected_revision and source["commit_oid"].lower() != expected_revision.lower():
        raise GraphSnapshotError("source_revision_mismatch")


def _canonical_graph(graph: Any) -> dict[str, Any]:
    raw = graph.to_dict() if hasattr(graph, "to_dict") else graph
    if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list) or not isinstance(raw.get("edges"), list):
        raise GraphSnapshotError("graph_serialization_invalid")
    nodes = sorted(raw["nodes"], key=lambda item: (str(item.get("id", "")), canonical_bytes(item)))
    edges = sorted(raw["edges"], key=canonical_bytes)
    node_ids = [item.get("id") for item in nodes]
    if any(not isinstance(item, str) or not item for item in node_ids):
        raise GraphSnapshotError("graph_node_identity_invalid")
    if len(node_ids) != len(set(node_ids)):
        raise GraphSnapshotError("graph_node_identity_duplicate")
    known = set(node_ids)
    for edge in edges:
        if edge.get("source") not in known or edge.get("target") not in known:
            raise GraphSnapshotError("graph_dangling_edge")
        if not isinstance(edge.get("relation"), str) or not edge["relation"]:
            raise GraphSnapshotError("graph_relation_invalid")
    return {"nodes": nodes, "edges": edges}



def _verify_lfs_attestation(
    attestation: dict[str, Any],
    *,
    source_snapshot_id: str,
    commit_oid: str,
    source_inventory_sha256: str,
    regular_inventory: list[dict[str, Any]],
) -> None:
    """Validate complete regular-blob classification and exact pointer evidence."""
    if not isinstance(attestation, dict) or attestation.get("schema") != "ae32c/lfs-payload-verification/v2":
        raise GraphSnapshotError("lfs_attestation_schema_invalid")
    payload = {key: value for key, value in attestation.items() if key != "attestation_sha256"}
    if attestation.get("attestation_sha256") != digest(payload):
        raise GraphSnapshotError("lfs_attestation_digest_mismatch")
    if (attestation.get("source_snapshot_id") != source_snapshot_id
            or attestation.get("commit_oid") != commit_oid
            or attestation.get("source_inventory_sha256") != source_inventory_sha256):
        raise GraphSnapshotError("lfs_attestation_source_binding_mismatch")
    if attestation.get("scan_complete") is not True:
        raise GraphSnapshotError("lfs_regular_blob_scan_incomplete")
    expected = [
        {"path": item["path"], "git_object_oid": item["git_object_oid"],
         "content_sha256": item["content_sha256"]}
        for item in regular_inventory
    ]
    actual = attestation.get("regular_blob_inventory")
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise GraphSnapshotError("lfs_regular_blob_inventory_count_mismatch")
    actual_keys = [(item.get("path"), item.get("git_object_oid"), item.get("content_sha256"))
                   for item in actual if isinstance(item, dict)]
    expected_keys = [(item["path"], item["git_object_oid"], item["content_sha256"])
                     for item in expected]
    if len(actual_keys) != len(actual) or len(set(item[0] for item in actual_keys)) != len(actual_keys):
        raise GraphSnapshotError("lfs_regular_blob_inventory_duplicate_or_invalid")
    if actual_keys != expected_keys or any(not isinstance(item.get("is_lfs_pointer"), bool) for item in actual):
        raise GraphSnapshotError("lfs_regular_blob_inventory_mismatch")
    if attestation.get("scanned_regular_blob_count") != len(expected):
        raise GraphSnapshotError("lfs_regular_blob_scan_count_mismatch")
    pointer_paths = [item["path"] for item in actual if item["is_lfs_pointer"]]
    records = attestation.get("records")
    if not isinstance(records, list):
        raise GraphSnapshotError("lfs_pointer_records_invalid")
    record_paths = [item.get("path") for item in records if isinstance(item, dict)]
    if len(record_paths) != len(records) or len(set(record_paths)) != len(record_paths):
        raise GraphSnapshotError("lfs_pointer_records_duplicate_or_invalid")
    if record_paths != pointer_paths:
        raise GraphSnapshotError("lfs_pointer_records_incomplete_or_extra")
    by_path = {item["path"]: item for item in actual}
    verified = 0
    unverified = 0
    for record in records:
        inventory_item = by_path[record["path"]]
        if (record.get("git_object_oid") != inventory_item["git_object_oid"]
                or record.get("pointer_sha256") != inventory_item["content_sha256"]):
            raise GraphSnapshotError("lfs_pointer_record_inventory_mismatch")
        if record.get("status") == "VERIFIED_LOCAL_PAYLOAD":
            oid = record.get("oid")
            size = record.get("expected_size")
            if (not isinstance(oid, str) or not re.fullmatch(r"[0-9a-f]{64}", oid)
                    or record.get("sha256") != oid
                    or not isinstance(size, int) or isinstance(size, bool) or size < 0
                    or record.get("actual_size") != size):
                raise GraphSnapshotError("lfs_verified_payload_record_invalid")
            verified += 1
        elif record.get("status") == "UNVERIFIED" and isinstance(record.get("reason"), str):
            unverified += 1
        else:
            raise GraphSnapshotError("lfs_pointer_record_status_invalid")
    if (attestation.get("pointer_count") != len(records)
            or attestation.get("verified_payload_count") != verified
            or attestation.get("unverified_payload_count") != unverified):
        raise GraphSnapshotError("lfs_pointer_record_counts_mismatch")
    status = attestation.get("status")
    if status == "NOT_SUPPLIED":
        if (attestation.get("object_store_mode") != "NOT_SUPPLIED_NO_NETWORK"
                or verified or unverified != len(records)):
            raise GraphSnapshotError("lfs_not_supplied_status_mismatch")
    elif status == "UNVERIFIED":
        if (attestation.get("object_store_mode") != "EXPLICIT_LOCAL_CACHE_NO_NETWORK"
                or not unverified):
            raise GraphSnapshotError("lfs_unverified_status_mismatch")
    elif status == "VERIFIED_LOCAL_PAYLOADS":
        if (attestation.get("object_store_mode") != "EXPLICIT_LOCAL_CACHE_NO_NETWORK"
                or unverified or verified != len(records)):
            raise GraphSnapshotError("lfs_verified_status_mismatch")
    else:
        raise GraphSnapshotError("lfs_attestation_status_invalid")
    if attestation.get("lfs_payload_verified") is not (status == "VERIFIED_LOCAL_PAYLOADS"):
        raise GraphSnapshotError("lfs_payload_verified_flag_mismatch")
    for forbidden in ("remote_payload_provenance_verified", "atomic_snapshot_established", "production_approval"):
        if attestation.get(forbidden) is not False:
            raise GraphSnapshotError("lfs_forbidden_authority_claim:" + forbidden)


def build_coverage_manifest(
    source_manifest: dict[str, Any],
    evidence_report: dict[str, Any],
    represented_paths: set[str],
    file_hashes: dict[str, str],
    *,
    sensitive_paths: set[str] | None = None,
    structured_issues: list[dict[str, Any]] | None = None,
    module_identity_issues: list[dict[str, Any]] | None = None,
    evidence_index_status: str = "complete",
    lfs_attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Account for every Git tree entry and every AE-32A candidate source unit."""
    sensitive_paths = sensitive_paths or set()
    structured_issues = structured_issues or []
    module_identity_issues = module_identity_issues or []
    rows = {row.get("path"): row for row in evidence_report.get("source_manifest", [])
            if isinstance(row, dict) and isinstance(row.get("path"), str)}
    units: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    unaccounted: list[str] = []
    inventory_entries = source_manifest.get("source_inventory", {}).get("entries", [])
    regular_inventory = [
        item for item in inventory_entries
        if isinstance(item, dict) and item.get("object_type") == "blob"
        and item.get("mode") in {"100644", "100755"}
    ]
    if lfs_attestation is None:
        raise GraphSnapshotError("lfs_attestation_required")
    source = source_manifest.get("source", {})
    _verify_lfs_attestation(
        lfs_attestation,
        source_snapshot_id=source_manifest.get("source_snapshot_id", ""),
        commit_oid=source.get("commit_oid", ""),
        source_inventory_sha256=source_manifest.get("source_inventory", {}).get("sha256", ""),
        regular_inventory=regular_inventory,
    )
    inventory_paths = {
        item.get("path") for item in inventory_entries
        if isinstance(item, dict) and item.get("object_type") == "blob"
        and item.get("mode") in {"100644", "100755"}
    }
    unexpected_paths = (set(represented_paths) | set(file_hashes)) - inventory_paths
    if unexpected_paths:
        sample = sorted(unexpected_paths, key=lambda item: str(item).encode("utf-8"))[:10]
        raise GraphSnapshotError("graph_contains_uncommitted_source_path:" + ",".join(map(str, sample)))
    for entry in inventory_entries:
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            raise GraphSnapshotError("source_inventory_path_invalid")
        row = rows.get(path)
        if entry.get("mode") == "120000":
            status, reason = "excluded_symlink", "git_symlink_not_followed"
        elif path in sensitive_paths:
            status, reason = "excluded_sensitive", "credential_or_sensitive_path_policy"
        elif row is None:
            status, reason = "outside_declared_source_scope", "not_selected_by_ae32a_source_suffix_or_directory_policy"
        elif row.get("status") != "included":
            status, reason = "excluded_by_evidence_inventory", str(row.get("status", "unknown"))
        elif path in represented_paths:
            status, reason = "represented", None
            expected = row.get("sha256")
            observed = file_hashes.get(path)
            if not expected or expected != observed:
                raise GraphSnapshotError("source_to_graph_digest_mismatch:" + path)
        else:
            status, reason = "unaccounted", "included_source_has_no_graph_file_node"
            unaccounted.append(path)
        counts[status] += 1
        units.append({
            "path": path,
            "mode": entry.get("mode"),
            "object_type": entry.get("object_type"),
            "git_object_oid": entry.get("git_object_oid"),
            "source_content_sha256": entry.get("content_sha256"),
            "status": status,
            "reason": reason,
        })
    units.sort(key=lambda item: item["path"].encode("utf-8"))

    audit = evidence_report.get("audit", {})
    parse_issues = evidence_report.get("python_parse_issues", [])
    scope_issues = evidence_report.get("scope_issues", [])
    source_root_issues = evidence_report.get("python_source_root_issues", [])
    workflow_issues = evidence_report.get("workflow_issues", [])
    complete = (
        audit.get("status") == "complete"
        and not unaccounted
        and not parse_issues
        and not scope_issues
        and not source_root_issues
        and not workflow_issues
        and not structured_issues
        and not module_identity_issues
        and evidence_index_status == "complete"
    )
    python_paths = sorted(
        path for path in represented_paths if PurePosixPath(path).suffix.lower() == ".py"
    )
    parse_issue_paths = {item.get("path") for item in parse_issues if isinstance(item, dict)}
    extractor_coverage = {
        "python_ast": {
            "candidate_count": len(python_paths),
            "parsed_count": sum(path not in parse_issue_paths for path in python_paths),
            "failed_count": sum(path in parse_issue_paths for path in python_paths),
            "issue_count": len(parse_issues),
        },
        "workflow_static_scan": {
            "issue_count": len(workflow_issues),
            "status": "complete" if not workflow_issues else "incomplete",
        },
        "structured_record_ingestion": {
            "issue_count": len(structured_issues),
            "status": "complete" if not structured_issues else "incomplete",
        },
        "module_identity": {
            "issue_count": len(module_identity_issues),
            "status": "complete" if not module_identity_issues else "incomplete",
        },
    }
    return {
        "schema": "ae32c/graph-coverage/v1",
        "status": "COMPLETE_WITH_DECLARED_EXCLUSIONS" if complete else "INCOMPLETE",
        "source_unit_count": len(units),
        "represented_count": counts["represented"],
        "excluded_count": sum(value for key, value in counts.items() if key.startswith("excluded") or key == "outside_declared_source_scope"),
        "unaccounted_count": counts["unaccounted"],
        "status_counts": dict(sorted(counts.items())),
        "source_units": units,
        "lfs_payloads": {
            "status": lfs_attestation["status"],
            "scanned_regular_blob_count": lfs_attestation["scanned_regular_blob_count"],
            "pointer_count": lfs_attestation["pointer_count"],
            "verified_payload_count": lfs_attestation["verified_payload_count"],
            "unverified_payload_count": lfs_attestation["unverified_payload_count"],
            "attestation_sha256": lfs_attestation["attestation_sha256"],
        },
        "extractor_coverage": extractor_coverage,
        "limitations": {
            "source_scope_policy": audit.get("scope_policy", {}),
            "negative_findings_permitted_by_default": False,
            "negative_findings_policy": "DENY_UNLESS_A_QUERY_SPECIFIC_CLOSED_WORLD_CONTRACT_IS_PROVED",
            "unaccounted_paths": unaccounted,
        },
    }


def build_graph_snapshot(
    *,
    source_manifest: dict[str, Any],
    graph: Any,
    evidence_report: dict[str, Any],
    represented_paths: set[str],
    file_hashes: dict[str, str],
    sensitive_paths: set[str] | None = None,
    structured_issues: list[dict[str, Any]] | None = None,
    module_identity_issues: list[dict[str, Any]] | None = None,
    evidence_index_status: str = "complete",
    python_runtime: str | None = None,
    lfs_attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _verify_source_manifest(source_manifest, source_manifest.get("source", {}).get("commit_oid"))
    canonical_graph = _canonical_graph(graph)
    coverage = build_coverage_manifest(
        source_manifest, evidence_report, represented_paths, file_hashes,
        sensitive_paths=sensitive_paths, structured_issues=structured_issues,
        module_identity_issues=module_identity_issues,
        evidence_index_status=evidence_index_status,
        lfs_attestation=lfs_attestation,
    )
    graph_content_sha256 = digest({
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "nodes": canonical_graph["nodes"],
        "edges": canonical_graph["edges"],
    })
    coverage_sha256 = digest(coverage)
    source = source_manifest["source"]
    builder = {
        "name": GRAPH_BUILDER_VERSION,
        "projection_contract_version": GRAPH_PROJECTION_VERSION,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "python_runtime": python_runtime or platform.python_version(),
    }
    identity = {
        "source_snapshot_id": source_manifest["source_snapshot_id"],
        "source_commit_oid": source["commit_oid"],
        "source_root_tree_oid": source["root_tree_oid"],
        "builder": builder,
        "graph_content_sha256": graph_content_sha256,
        "coverage_sha256": coverage_sha256,
        "lfs_attestation_sha256": lfs_attestation["attestation_sha256"],
    }
    finding_ledger = build_finding_ledger(
        list(evidence_report.get("findings", [])),
        source_manifest,
        {
            "graph_snapshot_id": digest(identity),
            "source_snapshot_id": source_manifest["source_snapshot_id"],
            "coverage": coverage,
        },
        canonical_graph,
        rule_registry(),
    )
    verify_finding_ledger(finding_ledger)
    result = {
        "manifest_schema": GRAPH_MANIFEST_SCHEMA,
        "status": "CAPTURED",
        "graph_snapshot_id": digest(identity),
        "source_snapshot_id": source_manifest["source_snapshot_id"],
        "source": {
            "repository": source["repository"],
            "commit_oid": source["commit_oid"],
            "root_tree_oid": source["root_tree_oid"],
            "source_inventory_sha256": source_manifest["source_inventory"]["sha256"],
        },
        "builder": builder,
        "graph": {
            "node_count": len(canonical_graph["nodes"]),
            "edge_count": len(canonical_graph["edges"]),
            "content_sha256": graph_content_sha256,
        },
        "coverage": coverage,
        "coverage_sha256": coverage_sha256,
        "lfs_attestation": lfs_attestation,
        "identity": identity,
        "rule_registry_sha256": finding_ledger["rule_registry_sha256"],
        "finding_ledger": finding_ledger,
        "finding_ledger_sha256": finding_ledger["ledger_sha256"],
        "authority": {
            "graph_is_derived_from_source": True,
            "graph_is_canonical_repository_authority": False,
            "graph_completeness_established": coverage["status"] == "COMPLETE_WITH_DECLARED_EXCLUSIONS",
            "negative_findings_permitted_by_default": False,
            "production_approval": False,
        },
    }
    result["manifest_sha256"] = digest(result)
    verify_graph_manifest(result)
    return result


def verify_graph_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("manifest_schema") != GRAPH_MANIFEST_SCHEMA:
        raise GraphSnapshotError("graph_manifest_schema_invalid")
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != digest(payload):
        raise GraphSnapshotError("graph_manifest_digest_mismatch")
    coverage = manifest.get("coverage")
    if not isinstance(coverage, dict) or manifest.get("coverage_sha256") != digest(coverage):
        raise GraphSnapshotError("graph_coverage_digest_mismatch")
    identity = manifest.get("identity")
    if not isinstance(identity, dict) or digest(identity) != manifest.get("graph_snapshot_id"):
        raise GraphSnapshotError("graph_snapshot_identity_mismatch")
    graph = manifest.get("graph", {})
    if identity.get("graph_content_sha256") != graph.get("content_sha256"):
        raise GraphSnapshotError("graph_content_identity_mismatch")
    if identity.get("coverage_sha256") != manifest.get("coverage_sha256"):
        raise GraphSnapshotError("graph_coverage_identity_mismatch")
    if identity.get("source_snapshot_id") != manifest.get("source_snapshot_id"):
        raise GraphSnapshotError("graph_source_identity_mismatch")
    source = manifest.get("source", {})
    if (identity.get("source_commit_oid") != source.get("commit_oid")
            or identity.get("source_root_tree_oid") != source.get("root_tree_oid")
            or not source.get("source_inventory_sha256")):
        raise GraphSnapshotError("graph_source_commit_or_tree_mismatch")
    attestation = manifest.get("lfs_attestation")
    coverage_lfs = coverage.get("lfs_payloads", {})
    if (not isinstance(attestation, dict)
            or identity.get("lfs_attestation_sha256") != attestation.get("attestation_sha256")
            or coverage_lfs.get("attestation_sha256") != attestation.get("attestation_sha256")):
        raise GraphSnapshotError("graph_lfs_attestation_reference_mismatch")
    source_units = coverage.get("source_units", [])
    regular_inventory = [
        {"path": item.get("path"), "git_object_oid": item.get("git_object_oid"),
         "content_sha256": item.get("source_content_sha256")}
        for item in source_units if isinstance(item, dict)
        and item.get("object_type") == "blob" and item.get("mode") in {"100644", "100755"}
    ]
    _verify_lfs_attestation(
        attestation,
        source_snapshot_id=manifest.get("source_snapshot_id", ""),
        commit_oid=source.get("commit_oid", ""),
        source_inventory_sha256=source.get("source_inventory_sha256", ""),
        regular_inventory=regular_inventory,
    )
    ledger = manifest.get("finding_ledger")
    if not isinstance(ledger, dict):
        raise GraphSnapshotError("finding_ledger_missing")
    try:
        verify_finding_ledger(ledger)
    except ValueError as exc:
        raise GraphSnapshotError("finding_ledger_invalid:" + str(exc)) from exc
    if ledger.get("source_snapshot_id") != manifest.get("source_snapshot_id"):
        raise GraphSnapshotError("finding_ledger_source_mismatch")
    if ledger.get("graph_snapshot_id") != manifest.get("graph_snapshot_id"):
        raise GraphSnapshotError("finding_ledger_graph_mismatch")
    if manifest.get("finding_ledger_sha256") != ledger.get("ledger_sha256"):
        raise GraphSnapshotError("finding_ledger_digest_reference_mismatch")
    if manifest.get("rule_registry_sha256") != ledger.get("rule_registry_sha256"):
        raise GraphSnapshotError("rule_registry_digest_reference_mismatch")


def capture(repository: str | Path, source_manifest_path: str | Path,
            expected_source_revision: str | None = None,
            lfs_object_store: str | Path | None = None) -> dict[str, Any]:
    source_manifest = json.loads(Path(source_manifest_path).read_text(encoding="utf-8"))
    _verify_source_manifest(source_manifest, expected_source_revision)
    repository_root = Path(repository).expanduser().resolve(strict=True)
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from audit_engine.semantic_audit.ae32b.evidence_tools import (
        GRAPH_PROJECTION_VERSION as PROJECTION_VERSION,
        SCHEMA_VERSION as BUILDER_VERSION,
        RepositoryEvidenceTools,
        _is_sensitive_path,
    )
    from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceProvider
    if PROJECTION_VERSION != GRAPH_PROJECTION_VERSION or BUILDER_VERSION != GRAPH_BUILDER_VERSION:
        raise GraphSnapshotError("graph_builder_contract_version_mismatch")
    source_provider = GitObjectSourceProvider(repository_root, source_manifest)
    builder = RepositoryEvidenceTools(
        repository_root, source_revision=source_manifest["source"]["commit_oid"],
        graph_backend="reference", source_provider=source_provider,
    )
    if builder.report.get("audit", {}).get("source_revision") != source_manifest["source"]["commit_oid"]:
        raise GraphSnapshotError("evidence_builder_source_revision_mismatch")
    lfs_attestation = verify_lfs_payloads(source_provider, lfs_object_store)
    snapshot = build_graph_snapshot(
        source_manifest=source_manifest,
        graph=builder.graph,
        evidence_report=builder.report,
        represented_paths=set(builder.file_nodes),
        file_hashes=builder.file_hashes,
        sensitive_paths={path for path in builder.manifest_rows if _is_sensitive_path(path)},
        structured_issues=builder.structured_record_issues,
        module_identity_issues=builder.module_identity_issues,
        evidence_index_status=builder.evidence_index_status,
        lfs_attestation=lfs_attestation,
    )
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=".")
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-source-revision")
    parser.add_argument("--lfs-object-store", help="Explicit local Git LFS object-store root; no network fetch is performed")
    args = parser.parse_args(argv)
    try:
        result = capture(args.repository, args.source_manifest, args.expected_source_revision, args.lfs_object_store)
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(result))
        print(json.dumps({
            "status": result["status"],
            "graph_snapshot_id": result["graph_snapshot_id"],
            "source_snapshot_id": result["source_snapshot_id"],
            "graph_content_sha256": result["graph"]["content_sha256"],
            "coverage_status": result["coverage"]["status"],
            "source_unit_count": result["coverage"]["source_unit_count"],
            "represented_count": result["coverage"]["represented_count"],
            "unaccounted_count": result["coverage"]["unaccounted_count"],
        }, sort_keys=True))
        return 0
    except (GraphSnapshotError, OSError, ValueError, KeyError, TypeError) as exc:
        print("graph_snapshot_error:" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

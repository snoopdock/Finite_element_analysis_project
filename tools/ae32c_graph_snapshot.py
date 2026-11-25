#!/usr/bin/env python3
"""Create a source-bound graph identity and coverage manifest (AE-32C Phase 2)."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import sys
from typing import Any

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
    for entry in source_manifest.get("source_inventory", {}).get("entries", []):
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
) -> dict[str, Any]:
    _verify_source_manifest(source_manifest, source_manifest.get("source", {}).get("commit_oid"))
    canonical_graph = _canonical_graph(graph)
    coverage = build_coverage_manifest(
        source_manifest, evidence_report, represented_paths, file_hashes,
        sensitive_paths=sensitive_paths, structured_issues=structured_issues,
        module_identity_issues=module_identity_issues,
        evidence_index_status=evidence_index_status,
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
    }
    result = {
        "manifest_schema": GRAPH_MANIFEST_SCHEMA,
        "status": "CAPTURED",
        "graph_snapshot_id": digest(identity),
        "source_snapshot_id": source_manifest["source_snapshot_id"],
        "source": {
            "repository": source["repository"],
            "commit_oid": source["commit_oid"],
            "root_tree_oid": source["root_tree_oid"],
        },
        "builder": builder,
        "graph": {
            "node_count": len(canonical_graph["nodes"]),
            "edge_count": len(canonical_graph["edges"]),
            "content_sha256": graph_content_sha256,
        },
        "coverage": coverage,
        "coverage_sha256": coverage_sha256,
        "identity": identity,
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


def capture(repository: str | Path, source_manifest_path: str | Path,
            expected_source_revision: str | None = None) -> dict[str, Any]:
    source_manifest = json.loads(Path(source_manifest_path).read_text(encoding="utf-8"))
    _verify_source_manifest(source_manifest, expected_source_revision)
    from audit_engine.semantic_audit.ae32b.evidence_tools import (
        GRAPH_PROJECTION_VERSION as PROJECTION_VERSION,
        SCHEMA_VERSION as BUILDER_VERSION,
        RepositoryEvidenceTools,
        _is_sensitive_path,
    )
    if PROJECTION_VERSION != GRAPH_PROJECTION_VERSION or BUILDER_VERSION != GRAPH_BUILDER_VERSION:
        raise GraphSnapshotError("graph_builder_contract_version_mismatch")
    builder = RepositoryEvidenceTools(
        repository, source_revision=source_manifest["source"]["commit_oid"],
        graph_backend="reference",
    )
    if builder.report.get("audit", {}).get("source_revision") != source_manifest["source"]["commit_oid"]:
        raise GraphSnapshotError("evidence_builder_source_revision_mismatch")
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
    )
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=".")
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-source-revision")
    args = parser.parse_args(argv)
    try:
        result = capture(args.repository, args.source_manifest, args.expected_source_revision)
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

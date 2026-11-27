"""C2: reconstruct and verify the exact B graph snapshot before any C provider dispatch."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from tools.ae32d_deterministic_audit import ROOT, TASK_SCHEMA, REPORT_SCHEMA as CONDITION_REPORT_SCHEMA, _git_head
from tools.ae32d_graph_assisted_audit import (
    GRAPH_BACKEND,
    _runner_revision,
    _scope_snapshot,
)


REPORT_SCHEMA = ROOT / "evaluation" / "ae32d" / "c-snapshot-verification.schema.json"


def verify_c_graph_snapshot(
    task_projection: dict[str, Any],
    b_report: dict[str, Any],
    source_root: str | Path,
) -> dict[str, Any]:
    """Rebuild B's declared-scope graph in isolation and compare exact provenance."""
    task_schema = json.loads(TASK_SCHEMA.read_text(encoding="utf-8"))
    output_schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    condition_report_schema = json.loads(CONDITION_REPORT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(task_schema).validate(task_projection)
    Draft202012Validator(condition_report_schema).validate(b_report)
    Draft202012Validator(condition_report_schema).validate(b_report["baseline_report"])
    Draft202012Validator(output_schema).check_schema(output_schema)
    if task_projection.get("condition") != "C_graph_llm":
        raise ValueError("C_snapshot_verification_requires_C_projection")

    if task_projection["case_id"] != b_report.get("case_id"):
        raise ValueError("C_snapshot_case_mismatch")
    if task_projection["source"]["source_commit_sha"] != b_report.get("source_commit_sha"):
        raise ValueError("C_snapshot_source_mismatch")
    if task_projection["task_contract_digest"] != b_report.get("task_contract_digest"):
        raise ValueError("C_snapshot_task_digest_mismatch")

    root = Path(source_root).resolve(strict=True)
    actual_sha = _git_head(root)
    if actual_sha != task_projection["source"]["source_commit_sha"]:
        raise ValueError("C_snapshot_checkout_revision_mismatch")

    expected = b_report["graph_snapshot"]
    mismatches: list[str] = []
    observed: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="ae32d-c-snapshot-") as temporary:
        graph_root = Path(temporary)
        scope_snapshot = _scope_snapshot(task_projection, root, graph_root)
        baseline_manifest = b_report["baseline_report"]["source_manifest_digest"]
        if scope_snapshot["issues"] or scope_snapshot["digest"] != baseline_manifest:
            mismatches.append("declared_scope_manifest_mismatch")

        if not mismatches:
            tools = RepositoryEvidenceTools(
                graph_root,
                source_revision=actual_sha,
                runner_revision=_runner_revision(),
                graph_backend=GRAPH_BACKEND,
            )
            try:
                summary = tools.invoke("repository_summary", {})
                if summary.get("status") != "ok":
                    mismatches.append("graph_repository_summary_failed")
                else:
                    provenance = summary.get("provenance", {})
                    result = summary.get("result", {})
                    runtime = result.get("graph_runtime", {})
                    observed = {
                        "source_revision": actual_sha,
                        "source_manifest_sha256": provenance.get("source_manifest_sha256"),
                        "graph_fingerprint": provenance.get("graph_fingerprint"),
                        "graph_projection_version": provenance.get("graph_projection_version"),
                        "evidence_index_status": result.get("evidence_index_status"),
                        "graph_backend": runtime.get("active_computation_backend", "unknown"),
                        "graph_node_count": result.get("graph_node_count", 0),
                        "graph_edge_count": result.get("graph_edge_count", 0),
                        "backend_pipeline_wired": bool(runtime.get("backend_pipeline_wired_into_ae32b_query_path", False)),
                    }
                    for key in (
                        "source_revision", "source_manifest_sha256", "graph_fingerprint",
                        "graph_projection_version", "evidence_index_status", "graph_backend",
                        "graph_node_count", "graph_edge_count", "backend_pipeline_wired",
                    ):
                        if observed.get(key) != expected.get(key):
                            mismatches.append("graph_snapshot_mismatch:" + key)
            finally:
                tools.close()
    if _git_head(root) != actual_sha:
        mismatches.append("source_revision_changed_during_C_snapshot_verification")

    output = {
        "schema_version": "ae32d/c-snapshot-verification/v1",
        "status": "verified" if not mismatches else "mismatch",
        "case_id": b_report["case_id"],
        "source_commit_sha": actual_sha,
        "task_contract_digest": b_report["task_contract_digest"],
        "baseline_source_manifest_digest": b_report["baseline_report"]["source_manifest_digest"],
        "expected_graph_snapshot": expected,
        "observed_graph_snapshot": observed,
        "mismatches": sorted(set(mismatches)),
        "provider_dispatch_permitted": False,
        "provider_calls_attempted": 0,
        "credentials_accessed": False,
    }
    Draft202012Validator(output_schema).validate(output)
    return output

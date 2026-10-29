#!/usr/bin/env python3
"""Stamp trusted GitHub Actions revision metadata into AE-32D comparison reports."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHA = re.compile(r"^[0-9a-f]{40}$")
MARKER = "## Execution provenance"

def stamp_report(data: dict[str, Any], source_revision: str, workflow_revision: str,
                 validation_run_id: str, workflow_run_id: str) -> dict[str, Any]:
    if not SHA.fullmatch(source_revision or ""):
        raise ValueError("invalid_source_revision_sha")
    if not SHA.fullmatch(workflow_revision or ""):
        raise ValueError("invalid_workflow_revision_sha")
    attestation = {
        "schema_version": "ae32d/execution-provenance/v1",
        "source_revision": source_revision,
        "source_revision_status": "validated_checkout_commit",
        "workflow_revision": workflow_revision,
        "workflow_revision_status": "github_actions_workflow_checkout_commit",
        "validation_run_id": str(validation_run_id),
        "workflow_run_id": str(workflow_run_id),
        "attested_at_utc": datetime.now(timezone.utc).isoformat(),
        "attestation_source": "GitHub Actions validation-gate outputs and workflow checkout SHA",
    }
    data["source_revision"] = source_revision
    data["source_revision_status"] = "validated_checkout_commit"
    data["workflow_revision"] = workflow_revision
    data["workflow_revision_status"] = "github_actions_workflow_checkout_commit"
    data["execution_provenance"] = dict(attestation)

    graph = data.get("graph_assisted")
    if isinstance(graph, dict):
        report = graph.get("report")
        if isinstance(report, dict):
            report["source_revision"] = source_revision
            report["source_revision_status"] = "validated_checkout_commit"
            report["runner_revision"] = workflow_revision
            report["runner_revision_status"] = "github_actions_workflow_checkout_commit"
            report["validation_run_id"] = str(validation_run_id)
            report["workflow_run_id"] = str(workflow_run_id)
            provenance = report.get("provenance")
            if not isinstance(provenance, dict):
                provenance = {}
                report["provenance"] = provenance
            provenance.update({
                "source_revision": source_revision,
                "source_revision_status": "validated_checkout_commit",
                "runner_revision": workflow_revision,
                "runner_revision_status": "github_actions_workflow_checkout_commit",
                "validation_run_id": str(validation_run_id),
                "workflow_run_id": str(workflow_run_id),
                "revision_attestation_source": "GitHub Actions validation-gate outputs and workflow checkout SHA",
            })
    return attestation

def update_markdown(path: Path, attestation: dict[str, Any]) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        text = text.split(MARKER, 1)[0].rstrip() + "\n\n"
    section = (
        MARKER + "\n\n"
        f"- Validated source revision: `{attestation['source_revision']}` "
        f"(`{attestation['source_revision_status']}`)\n"
        f"- Workflow revision: `{attestation['workflow_revision']}` "
        f"(`{attestation['workflow_revision_status']}`)\n"
        f"- G9.42 validation run: `{attestation['validation_run_id']}`\n"
        f"- Investigation workflow run: `{attestation['workflow_run_id']}`\n"
        "- These fields attest execution identity, not diagnostic correctness.\n"
    )
    path.write_text(text.rstrip() + "\n\n" + section, encoding="utf-8")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--source-revision", required=True)
    ap.add_argument("--workflow-revision", required=True)
    ap.add_argument("--validation-run-id", required=True)
    ap.add_argument("--workflow-run-id", required=True)
    args = ap.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    comparison_paths = sorted(out.rglob("comparison.json"))
    if len(comparison_paths) > 1:
        raise SystemExit(f"expected_at_most_one_comparison_json, found {len(comparison_paths)}")
    attestation = {
        "schema_version": "ae32d/execution-provenance/v1",
        "source_revision": args.source_revision,
        "source_revision_status": "validated_checkout_commit",
        "workflow_revision": args.workflow_revision,
        "workflow_revision_status": "github_actions_workflow_checkout_commit",
        "validation_run_id": str(args.validation_run_id),
        "workflow_run_id": str(args.workflow_run_id),
        "attested_at_utc": datetime.now(timezone.utc).isoformat(),
        "attestation_source": "GitHub Actions validation-gate outputs and workflow checkout SHA",
    }
    if comparison_paths:
        p = comparison_paths[0]
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SystemExit("comparison_json_not_object")
        attestation = stamp_report(data, args.source_revision, args.workflow_revision,
                                   args.validation_run_id, args.workflow_run_id)
        p.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        update_markdown(p.with_name("comparison.md"), attestation)
    sidecar = {
        **attestation,
        "reports_stamped": len(comparison_paths),
        "comparison_report": str(comparison_paths[0].relative_to(out)) if comparison_paths else None,
    }
    (out / "execution-provenance.json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "reports_stamped": sidecar["reports_stamped"],
        "source_revision": sidecar["source_revision"],
        "workflow_revision": sidecar["workflow_revision"],
        "validation_run_id": sidecar["validation_run_id"],
        "workflow_run_id": sidecar["workflow_run_id"],
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Produce an offline, read-only AE-32A/B/C architecture and graph-runtime report."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from audit_engine.semantic_audit.ae32c.runtime_architecture import build_runtime_architecture_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository checkout to inspect.")
    parser.add_argument("--output", help="Optional JSON output path outside the inspected repository.")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).expanduser().resolve(strict=True)
    tools = RepositoryEvidenceTools(root)
    summary_response = tools.invoke("repository_summary", {})
    if summary_response.get("status") != "ok":
        print(json.dumps({"status": "failed", "reason": "repository_summary_failed"}), file=sys.stderr)
        return 2
    summary = summary_response.get("result", {})
    architecture = build_runtime_architecture_report(
        audit_report=tools.report,
        repository_summary=summary if isinstance(summary, dict) else {},
        provider_name=os.environ.get("FEA_LLM_PROVIDER", "not_configured"),
        model_name=os.environ.get("FEA_LLM_MODEL", "not_configured"),
        provider_stats={},
        available_tool_names=tools._handlers,
    )
    payload = {
        "schema_version": "ae32c/offline-runtime-architecture-report/v1",
        "status": "complete" if tools.report.get("audit", {}).get("status") == "complete" else "incomplete",
        "runtime_execution_performed": False,
        "provider_calls_made": False,
        "repository_code_executed": False,
        "source_files_modified": False,
        "audit_summary": tools.report.get("summary", {}),
        "audit_findings": [
            {key: finding.get(key) for key in ("id", "severity", "title")}
            for finding in tools.report.get("findings", []) if isinstance(finding, dict)
        ],
        "repository_summary": summary,
        "runtime_architecture": architecture,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        output = Path(args.output).expanduser()
        if output.is_symlink():
            parser.error("output path must not be a symlink")
        output = output.resolve()
        try:
            output.relative_to(root)
        except ValueError:
            pass
        else:
            parser.error("output must be outside the inspected repository")
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            parser.error("output already exists; choose a new path")
        output.write_text(encoded, encoding="utf-8")
        print(json.dumps({"status": payload["status"], "output": str(output),
                          "source_manifest_sha256": tools.manifest_sha256}, indent=2))
    else:
        print(encoded, end="")
    return 0 if payload["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

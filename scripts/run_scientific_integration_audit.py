#!/usr/bin/env python3
"""Run the repository's pre-Stage-8 scientific integration audits."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITS = [
    ("H1", ROOT / "scripts/audit_h1_scientific_object_composition.py"),
    ("H2", ROOT / "scripts/audit_h2_state_roundtrip.py"),
    ("H3", ROOT / "scripts/audit_h3_provenance_closure.py"),
    ("H4", ROOT / "scripts/audit_h4_writer_compatibility.py"),
    ("H5", ROOT / "scripts/audit_h5_graph_enrichment.py"),
    ("H6", ROOT / "scripts/audit_h6_fem_literature_fixture.py"),
    ("H7", ROOT / "scripts/audit_h7_failure_matrix.py"),
    ("H7.5-field-ownership", ROOT / "scripts/audit_h7_5_field_ownership.py"),
    ("H7.5-scope-inheritance", ROOT / "scripts/audit_h7_5_scope_inheritance.py"),
    ("H7.5-evidence-independence", ROOT / "scripts/audit_h7_5_evidence_independence.py"),
    ("H7.5-scope-aware-contradiction", ROOT / "scripts/audit_h7_5_scope_aware_contradiction.py"),
    ("H7.5-semantic-consistency", ROOT / "scripts/audit_h7_5_semantic_consistency.py"),
]


def main() -> int:
    results = []
    for name, script in AUDITS:
        started = datetime.now(timezone.utc).isoformat()
        if not script.exists():
            results.append({"audit": name, "status": "missing", "started": started})
            continue
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        results.append({
            "audit": name,
            "status": "pass" if completed.returncode == 0 else "fail",
            "started": started,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(ROOT),
        "results": results,
        "readiness": (
            "blocked"
            if any(item["status"] != "pass" for item in results)
            else "ready_for_runtime_validation"
        ),
    }
    output = ROOT / "artifacts" / "scientific_integration_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["readiness"] == "ready_for_runtime_validation" else 1


if __name__ == "__main__":
    raise SystemExit(main())

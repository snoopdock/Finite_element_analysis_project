#!/usr/bin/env python3
"""Fail-fast regression umbrella for the completed R6-R7C attention subsystem."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

AUDITS = [
    "scripts.audit_retrieval_history_integration",
    "scripts.audit_retrieval_attention_contract",
    "scripts.audit_retrieval_attention_provenance_contract",
    "scripts.audit_retrieval_attention_context_contract",
    "scripts.audit_retrieval_attention_context",
    "scripts.audit_retrieval_attention_policy_contract",
    "scripts.audit_retrieval_attention_policy",
    "scripts.audit_retrieval_attention_proposal_contract",
    "scripts.audit_retrieval_attention_persistence_contract",
    "scripts.audit_retrieval_attention_persistence",
    "scripts.audit_retrieval_attention_replay",
    "scripts.audit_retrieval_attention_pipeline_contract",
    "scripts.audit_retrieval_attention_pipeline",
    "scripts.audit_retrieval_attention_full_cycle_contract",
    "scripts.audit_retrieval_attention_full_cycle",
    "scripts.audit_retrieval_attention_runtime_contract",
    "scripts.audit_retrieval_attention_runtime",
    "scripts.audit_retrieval_attention_live_integration",
    "scripts.audit_retrieval_attention_runtime_isolation_contract",
    "scripts.audit_retrieval_attention_runtime_isolation",
]


def main() -> int:
    total = len(AUDITS)

    for index, module_name in enumerate(AUDITS, start=1):
        command = [sys.executable, "-m", module_name]
        print(f"\n[{index}/{total}] {module_name}")
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
        )
        if completed.returncode != 0:
            print(
                f"\nR7C.9 retrieval attention regression: FAIL "
                f"at {module_name} (exit {completed.returncode})",
                file=sys.stderr,
            )
            return completed.returncode or 1

    print(
        f"\nR7C.9 retrieval attention regression: PASS "
        f"({total}/{total} audits passed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

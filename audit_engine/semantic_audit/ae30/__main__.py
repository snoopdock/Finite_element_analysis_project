"""Run the deterministic AE-30 independent evaluation."""
from __future__ import annotations

import sys

from audit_engine.semantic_audit.ae24.contracts import canonical
from .evaluator import run_evaluation


if __name__ == "__main__":
    report = run_evaluation()
    print(canonical(report).decode("utf-8"))
    raise SystemExit(0 if report["acceptance"]["status"] == "passed" else 3)

#!/usr/bin/env python3
"""Audit the R8.7.4.0 AcquisitionAdapter implementation decision."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "specs" / "decisions" / "R8.7.4.0_acquisition_adapter_implementation_decision.yaml"


def main() -> int:
    failures: list[str] = []
    checks = 0

    def require(label: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    text = DECISION.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    required_sections = (
        "implementation_model:",
        "implementation_stages:",
        "receipt_representation:",
        "constraint_translation:",
        "execution_status:",
        "retry_and_history:",
        "architectural_isolation:",
        "file_scope:",
        "test_strategy:",
        "integration:",
        "candidate_implementation_review:",
        "relationships:",
        "scope:",
    )
    for section in required_sections:
        require(f"missing required decision section: {section}", section in text)

    required_rules = (
        "authoritative_input: AcquisitionRequest",
        "legacy_execution_representation: List[str]",
        "execution_provenance: AcquisitionExecutionReceipt",
        "translation_mode: lossy_by_design",
        "Semantic fidelity has priority over representation completeness.",
        "AcquisitionExecutionProjection construction",
        "Classify every material request field",
        "provider preferences",
        "provider-access restrictions",
        "Numeric similarity is not semantic equivalence.",
        "Priority is retained for process execution metadata",
        "operational_only: true",
        "Each call representing an execution attempt receives a new execution_id.",
        "The adapter does not maintain or overwrite historical receipts.",
        "R8.7.4 stops at the explicit adapter boundary.",
        "Existing adapter code created before this decision is treated as a candidate realization",
        "R8.7.3",
        "AcquisitionRequest remains a distinct explicit process object",
    )
    for phrase in required_rules:
        require(f"missing implementation decision rule: {phrase!r}", phrase in normalized)

    forbidden_integration = (
        "main.py runtime orchestration",
        "provider implementations",
        "retrieve_evidence_parallel signature or behavior",
        "EvidenceRecord schema or source-level provenance semantics",
        "LifecycleEvent history",
        "ResearchPlanningDecision",
        "ScientificAttention",
    )
    for phrase in forbidden_integration:
        require(f"missing explicit deferred/prohibited boundary: {phrase!r}", phrase in normalized)

    allowed_files = (
        "analysis/acquisition_adapter.py",
        "tests/test_acquisition_adapter.py",
        "scripts/audit_r8_7_4_acquisition_adapter.py",
    )
    for path in allowed_files:
        require(f"expected implementation file missing from decision: {path}", path in text)

    require("dedicated receipt module is explicitly deferred", "core/acquisition_execution_receipt.py" in text)
    require("research retrieval implementation is explicitly deferred", "research/evidence.py" in text)
    require("main integration is explicitly deferred", "main.py" in text)
    require("provider layer is explicitly deferred", "provider modules" in text)

    if failures:
        print(f"R8.7.4.0 implementation decision audit: FAIL ({checks} checks evaluated)")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"R8.7.4.0 implementation decision audit: PASS ({checks}/{checks} checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

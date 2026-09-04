#!/usr/bin/env python3
"""Audit the R8.8.0 AcquisitionRequest formulation decision."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "specs" / "decisions" / "R8.8.0_acquisition_request_formulation_decision.yaml"


def main() -> int:
    failures: list[str] = []
    checks = 0

    def require(label: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    try:
        text = DECISION.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"R8.8.0 AcquisitionRequest formulation audit: FAIL\n- unable to read decision: {exc}")
        return 1

    normalized = " ".join(text.split())

    for section in (
        "problem_statement:",
        "formation_model:",
        "allowed_decision_type:",
        "required_request_mapping:",
        "provider_semantic_protection:",
        "optional_operational_formulation_input:",
        "provenance:",
        "immutability:",
        "scientific_isolation:",
        "lifecycle_isolation:",
        "execution_isolation:",
        "identity_and_repetition:",
        "validation:",
        "relationship_to_existing_contracts:",
        "file_scope:",
        "scope:",
    ):
        require(f"missing required decision section: {section}", section in text)

    rules = (
        "authoritative_input: ResearchPlanningDecision",
        "output_object: AcquisitionRequest",
        "boundary_role: explicit_request_formulation",
        "execution_authority: none",
        "Only a ResearchPlanningDecision whose decision_type is formulate_acquisition_request",
        "target.query_scope",
        "Planning priority may become AcquisitionRequest process execution priority",
        "Constraints are not inferred",
        "Do not convert target.provider into provider_preferences automatically.",
        "Do not convert target.provider into provider_access_constraints automatically.",
        "Do not infer an alternative provider from rationale prose.",
        "Do not infer execution limits from priority, rationale, or decision type.",
        "origin.research_planning_decision_id",
        "Formulation ends when a valid AcquisitionRequest has been produced.",
        "retrieval provider calls",
        "retrieve_evidence_parallel invocation",
        "AcquisitionExecutionReceipt creation",
        "main.py integration",
    )
    for phrase in rules:
        require(f"missing formulation decision rule: {phrase!r}", phrase in normalized)

    for forbidden in (
        "scientific-state mutation",
        "LifecycleEvent creation",
        "automatic execution of the formulated request",
        "RetrievalEvent changes",
        "EvidenceRecord changes",
    ):
        require(f"missing explicit prohibition: {forbidden!r}", forbidden in normalized)

    audit_paths = (
        "scripts/audit_r8_8_0_acquisition_request_formulation.py",
        "scripts/audit_r8_8_0_acquisition_request_formulation_runtime.py",
    )
    require(
        "planned decision/runtime audit file is not recognized",
        any(path in normalized for path in audit_paths),
    )
    require(
        "AcquisitionAdapter remains the downstream execution boundary",
        "R8.7.4_0".replace("_", ".") in text
        or ("R8.7.4" in normalized and "AcquisitionAdapter" in normalized),
    )
    require(
        "AcquisitionRequest contract remains the output authority",
        "r8_6_2:" in text and "AcquisitionRequest contract" in normalized,
    )

    if failures:
        print(f"R8.8.0 AcquisitionRequest formulation audit: FAIL ({checks} checks evaluated)")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"R8.8.0 AcquisitionRequest formulation audit: PASS ({checks}/{checks} checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

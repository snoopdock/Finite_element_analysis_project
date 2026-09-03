"""Static audit for the R8.6.2 AcquisitionRequest contract.

This audit intentionally inspects only the contract text. It does not import,
execute, or integrate any runtime acquisition code.
"""

from pathlib import Path


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "specs" / "contracts" / "acquisition_request_contract.yaml"

REQUIRED_SNIPPETS = {
    "contract_name": "name: acquisition_request_contract",
    "accepted_status": "status: accepted",
    "request_identity": "acquisition_request_id",
    "decision_origin": "research_planning_decision_id",
    "query_scope": "query_scope",
    "automatic_creation_disabled": "automatic_from_decision: false",
    "explicit_boundary": "explicit_boundary: true",
    "process_priority": "process_execution_priority_only",
    "no_automatic_execution": "automatic execution",
    "future_adapter": "future_acquisition_adapter",
    "retrieval_execution_interface": "current_execution_interface: List[str]",
    "retrieval_request_rejected": "AcquisitionRequest is not RetrievalRequest.",
}

FORBIDDEN_SCIENTIFIC_FIELDS = (
    "confidence",
    "confidence_score",
    "evidence_gap",
    "evidence_strength",
    "evidence_quality",
    "epistemic_status",
    "truth_status",
    "truth_probability",
    "ranking",
    "ranking_score",
    "claim_rank",
    "claim_ranking",
    "convergence",
    "convergence_score",
    "scientific_priority",
    "scientific_importance",
    "scientific_relevance",
    "claim_id",
    "proposition_id",
    "evidence_relation",
)

FORBIDDEN_RUNTIME_COUPLING = (
    "execute retrieval",
    "direct provider calls",
    "network execution",
    "retrieve_evidence_parallel changes",
    "main.py integration",
    "pending_evidence_queries integration",
    "provider-layer changes",
)


def main() -> int:
    text = CONTRACT_PATH.read_text(encoding="utf-8")

    failures: list[str] = []

    for name, snippet in REQUIRED_SNIPPETS.items():
        if snippet not in text:
            failures.append(f"missing required contract condition: {name} ({snippet!r})")

    # Verify that scientific fields are explicitly represented in the forbidden
    # semantic-field section rather than merely appearing somewhere incidentally.
    forbidden_section_start = text.find("forbidden_semantic_fields:")
    semantic_isolation_start = text.find("semantic_isolation:")
    if forbidden_section_start == -1 or semantic_isolation_start == -1:
        failures.append("missing forbidden_semantic_fields or semantic_isolation section")
    else:
        forbidden_section = text[forbidden_section_start:semantic_isolation_start]
        for field in FORBIDDEN_SCIENTIFIC_FIELDS:
            if f"    - {field}" not in forbidden_section:
                failures.append(f"scientific field not explicitly forbidden: {field}")

    for phrase in FORBIDDEN_RUNTIME_COUPLING:
        if phrase not in text:
            failures.append(f"missing explicit runtime exclusion: {phrase!r}")

    # The contract must not reintroduce RetrievalRequest as an acquisition object.
    acquisition_objects_start = text.find("architectural_role:")
    core_invariants_start = text.find("core_invariants:")
    if acquisition_objects_start == -1 or core_invariants_start == -1:
        failures.append("unable to inspect architectural acquisition object declaration")
    else:
        architectural_role = text[acquisition_objects_start:core_invariants_start]
        if "RetrievalRequest" in architectural_role:
            failures.append("RetrievalRequest must not be declared as an acquisition object")

    # Contract-only means no implementation/import of the existing retrieval path.
    if "from core" in text or "import core" in text or "retrieve_evidence_parallel(" in text:
        failures.append("contract contains runtime implementation coupling")

    if failures:
        print("R8.6.2 AcquisitionRequest contract audit: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    checks = len(REQUIRED_SNIPPETS) + len(FORBIDDEN_SCIENTIFIC_FIELDS) + len(FORBIDDEN_RUNTIME_COUPLING) + 3
    print(f"R8.6.2 AcquisitionRequest contract audit: PASS ({checks}/{checks} checks passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

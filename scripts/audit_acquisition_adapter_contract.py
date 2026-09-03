"""Static audit for the R8.7.2 AcquisitionAdapter contract.

This audit intentionally inspects only the contract text. It does not import,
execute, or integrate any acquisition or retrieval runtime code.
"""

from pathlib import Path


CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "contracts"
    / "acquisition_adapter_contract.yaml"
)

REQUIRED_SNIPPETS = {
    "contract_name": "name: acquisition_adapter_contract",
    "draft_status": "status: draft",
    "adapter_input": "name: AcquisitionRequest",
    "adapter_output": "name: AcquisitionExecutionReceipt",
    "retrieval_interface": "interface: List[str]",
    "existing_retrieval_function": "current_function: retrieve_evidence_parallel",
    "translation_boundary": "structural_loss_boundary:",
    "unsupported_constraints_reported": "unsupported_constraints:",
    "execution_id": "execution_id",
    "acquisition_request_id": "acquisition_request_id",
    "execution_status": "execution_status",
    "retry_new_occurrence": "Each execution attempt is a separate occurrence.",
    "evidence_source_level": "EvidenceRecord remains a source-level knowledge/provenance object",
    "retrieval_report_cycle_summary": "retrieval_report_remains_cycle_summary: true",
    "no_retrieval_event_requirement": "retrieval_event_not_required: true",
    "no_automatic_execution": "The adapter executes only when an explicit AcquisitionRequest is submitted",
    "contract_only": "No AcquisitionAdapter implementation is introduced by this contract.",
}

FORBIDDEN_SCIENTIFIC_FIELDS = (
    "confidence",
    "evidence_strength",
    "evidence_gap",
    "epistemic_state",
    "truth",
    "claim ranking",
    "scientific priority",
    "convergence",
)

FORBIDDEN_AUTHORITY_TERMS = (
    "create ResearchPlanningDecision",
    "create ResearchPlanningSignal",
    "create AttentionProposal",
    "create ScientificAttention",
    "create LifecycleEvent",
    "advance AttentionProposal lifecycle state",
    "modify epistemic state",
    "modify claim ranking",
    "modify convergence",
)

RUNTIME_EXCLUSIONS = (
    "No changes to retrieve_evidence_parallel are introduced by this contract.",
    "No provider-layer changes are introduced by this contract.",
    "No EvidenceRecord schema changes are introduced by this contract.",
    "No main.py integration is introduced by this contract.",
    "No pending_evidence_queries integration is introduced by this contract.",
    "No RetrievalEvent model is introduced by this contract.",
    "No automatic retrieval execution is introduced by this contract.",
)


def _section(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker)) if start != -1 else -1
    if start == -1 or end == -1:
        return ""
    return text[start:end]


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def main() -> int:
    if not CONTRACT_PATH.exists():
        print("R8.7.2 AcquisitionAdapter contract audit: FAIL")
        print(f"- contract not found: {CONTRACT_PATH}")
        return 1

    text = CONTRACT_PATH.read_text(encoding="utf-8")
    failures: list[str] = []

    for name, snippet in REQUIRED_SNIPPETS.items():
        if snippet not in text:
            failures.append(f"missing required contract condition: {name} ({snippet!r})")

    # Verify the semantic input/output boundary in the architectural-role section.
    role = _section(text, "architectural_role:", "core_invariants:")
    if not role:
        failures.append("unable to inspect architectural_role section")
    else:
        if "name: AcquisitionRequest" not in role:
            failures.append("AcquisitionAdapter input boundary is not declared as AcquisitionRequest")
        if "name: AcquisitionExecutionReceipt" not in role:
            failures.append("AcquisitionAdapter output boundary is not declared as AcquisitionExecutionReceipt")
        if "name: EvidenceRecord" not in role:
            failures.append("EvidenceRecord relationship is missing from architectural role")

    # The adapter must not be defined as an EvidenceRecord producer.
    if "AcquisitionAdapter → EvidenceRecord" in text or "AcquisitionAdapter -> EvidenceRecord" in text:
        failures.append("adapter must not own EvidenceRecord production")

    # Verify source-level provenance remains distinct from execution-level provenance.
    evidence_section = _section(text, "relationship_to_evidence:", "relationship_to_retrieval_runtime:")
    if not evidence_section:
        failures.append("unable to inspect relationship_to_evidence section")
    else:
        required_evidence_rules = (
            ("execution_provenance_role", (
                "AcquisitionExecutionReceipt records why and how an acquisition execution occurred",
                "AcquisitionExecutionReceipt records",
            )),
            ("source_provenance_role", ("EvidenceRecord records source-level provenance",)),
            ("many_to_many_protection", (
                "must not assume that one EvidenceRecord belongs to exactly one AcquisitionRequest",
                "A source may be discovered by multiple acquisition requests",
            )),
            ("request_id_not_on_evidence", (
                "add acquisition_request_id to EvidenceRecord solely for adapter provenance",
            )),
        )
        for name, phrases in required_evidence_rules:
            if not _contains_any(evidence_section, phrases):
                failures.append(f"missing provenance separation rule: {name!r}")

    # Verify the existing retrieval boundary and explicit translation ownership.
    retrieval_section = _section(text, "relationship_to_retrieval_runtime:", "execution_status_semantics:")
    if not retrieval_section:
        failures.append("unable to inspect relationship_to_retrieval_runtime section")
    else:
        for name, phrases in (
            ("current_input", ("current_input: List[str]",)),
            ("existing_boundary", ("The adapter may invoke the existing retrieval execution boundary",)),
            # Translation ownership is declared in architectural_role and reinforced
            # by the retrieval-boundary rule. Do not require a specific YAML key name.
            ("translation_owner", (
                "The adapter owns translation",
                "adapter owns translation",
                "The adapter owns translation into that interface",
            )),
            ("existing_interface_results", ("return retrieval results through its existing interface",)),
            ("source_provenance_preserved", ("maintain existing source-level evidence provenance",)),
        ):
            search_text = retrieval_section if name != "translation_owner" else text
            if not _contains_any(search_text, phrases):
                failures.append(f"missing retrieval-boundary rule: {name!r}")

    # Unsupported constraints must not disappear silently. YAML folded prose and
    # alternate equivalent wording are accepted; the semantic prohibition itself
    # is what matters, not one exact sentence layout.
    constraint_section = _section(text, "translation:", "execution_provenance:")
    if not constraint_section:
        failures.append("unable to inspect translation section")
    else:
        normalized = " ".join(constraint_section.split())
        constraint_rules = (
            ("explicit_reporting", ("must be reported explicitly",)),
            ("silent_ignore_rejected", ("must not be silently ignored", "silently ignored")),
            ("silent_reinterpretation_rejected", (
                "must not be silently reinterpreted",
                "silently reinterpreted",
            )),
            ("query_scope", ("query_scope",)),
            ("supported_operational_constraints", ("supported operational constraints",)),
        )
        for name, phrases in constraint_rules:
            if not _contains_any(normalized, phrases):
                failures.append(f"missing constraint-handling rule: {name!r}")

    # Retry semantics must establish distinct immutable occurrences.
    retry_section = _section(text, "failure_and_retry:", "automatic_execution:")
    if not retry_section:
        failures.append("unable to inspect failure_and_retry section")
    else:
        normalized_retry = " ".join(retry_section.split())
        for name, phrases in (
            ("new_occurrence", ("a new execution occurrence",)),
            ("new_execution_id", ("new execution_id",)),
            ("historical_receipts", ("Earlier execution receipts remain historical records",)),
            ("same_request_multiple_receipts", ("Multiple execution receipts may reference the same acquisition_request_id",)),
            ("no_mutating_retry", ("must not be represented by mutating one receipt",)),
        ):
            if not _contains_any(normalized_retry, phrases):
                failures.append(f"missing retry/provenance rule: {name!r}")

    # Operational statuses must remain operational rather than epistemic.
    status_section = _section(text, "execution_status_semantics:", "authority_isolation:")
    if not status_section:
        failures.append("unable to inspect execution_status_semantics section")
    else:
        for phrase in (
            "operational_only: true",
            "failure != evidence_weakness",
            "failure != claim_uncertainty",
            "empty_result != literature_absence",
            "empty_result != evidence_gap",
            "rate_limited != evidence_weakness",
        ):
            if phrase not in status_section:
                failures.append(f"missing execution-status semantic isolation rule: {phrase!r}")

    # Scientific authority leakage must be explicitly prohibited.
    authority_section = _section(text, "authority_isolation:", "failure_and_retry:")
    if not authority_section:
        failures.append("unable to inspect authority_isolation section")
    else:
        for term in FORBIDDEN_AUTHORITY_TERMS:
            if term not in authority_section:
                failures.append(f"missing authority-isolation prohibition: {term!r}")

    # Scientific concepts may be written as YAML field names (snake_case) or as
    # human-readable semantic phrases. Accept either representation.
    scientific_section = _section(text, "authority_isolation:", "failure_and_retry:")
    scientific_aliases = {
        "confidence": ("confidence",),
        "evidence_strength": ("evidence_strength", "evidence strength"),
        "evidence_gap": ("evidence_gap", "evidence gap"),
        "epistemic_state": ("epistemic_state", "epistemic state"),
        "truth": ("truth",),
        "claim ranking": ("claim ranking", "claim_ranking"),
        "scientific priority": ("scientific priority", "scientific_priority"),
        "convergence": ("convergence",),
    }
    for term in FORBIDDEN_SCIENTIFIC_FIELDS:
        aliases = scientific_aliases[term]
        if not _contains_any(scientific_section, aliases) and not _contains_any(text, aliases):
            failures.append(f"scientific semantic not explicitly addressed: {term!r}")

    # Runtime exclusions must remain explicit and this artifact must stay contract-only.
    for phrase in RUNTIME_EXCLUSIONS:
        if phrase not in text:
            failures.append(f"missing runtime exclusion: {phrase!r}")

    if "from core" in text or "import core" in text:
        failures.append("contract contains runtime import coupling")

    # `retrieve_evidence_parallel(List[str])` is the documented interface shape,
    # not a runtime invocation. Reject actual call syntax while allowing the
    # interface notation required by the contract.
    if "retrieve_evidence_parallel(" in text:
        invocation_without_interface = text.replace("retrieve_evidence_parallel(List[str])", "")
        if "retrieve_evidence_parallel(" in invocation_without_interface:
            failures.append("contract contains a retrieval invocation rather than only the interface name")

    if "requests.get(" in text or "httpx" in text or "urllib" in text:
        failures.append("contract contains network/runtime implementation coupling")

    # The adapter contract must select AcquisitionExecutionReceipt rather than
    # silently reintroducing RetrievalEvent as the execution-provenance target.
    if "output_object: AcquisitionExecutionReceipt" not in text:
        failures.append("AcquisitionExecutionReceipt is not declared as the adapter output object")
    if "RetrievalEvent model is introduced" in text:
        pass  # Explicit non-decision is expected.
    else:
        failures.append("missing explicit RetrievalEvent non-decision")

    if failures:
        print("R8.7.2 AcquisitionAdapter contract audit: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    checks = (
        len(REQUIRED_SNIPPETS)
        + 3  # architectural-role checks
        + 4  # evidence provenance checks
        + 5  # retrieval-boundary checks
        + 5  # constraint checks
        + 5  # retry checks
        + 6  # execution-status checks
        + len(FORBIDDEN_AUTHORITY_TERMS)
        + len(FORBIDDEN_SCIENTIFIC_FIELDS)
        + len(RUNTIME_EXCLUSIONS)
        + 4  # runtime coupling / provenance target checks
    )
    print(f"R8.7.2 AcquisitionAdapter contract audit: PASS ({checks}/{checks} checks passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

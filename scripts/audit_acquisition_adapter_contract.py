"""Static audit for the R8.7.3 AcquisitionAdapter contract.

The audit validates architectural invariants and semantic relationships rather
than requiring brittle exact prose. It performs no runtime imports, retrieval,
network access, or repository integration.
"""

from __future__ import annotations

from pathlib import Path
import re


CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "contracts"
    / "acquisition_adapter_contract.yaml"
)


def _section(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker)) if start != -1 else -1
    if start == -1 or end == -1:
        return ""
    return text[start:end]


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _require(failures: list[str], label: str, condition: bool) -> None:
    _require.check_count += 1
    if not condition:
        failures.append(label)


_require.check_count = 0


def main() -> int:
    failures: list[str] = []
    _require.check_count = 0

    if not CONTRACT_PATH.exists():
        print("R8.7.3 AcquisitionAdapter contract audit: FAIL")
        print(f"- contract not found: {CONTRACT_PATH}")
        return 1

    text = CONTRACT_PATH.read_text(encoding="utf-8")
    normalized = _normalized(text)

    # ------------------------------------------------------------
    # Contract identity and stage ownership
    # ------------------------------------------------------------
    identity_checks = {
        "contract name": "name: acquisition_adapter_contract",
        "accepted status": "status: accepted",
        "R8.7.3 reference": "relationship_to_r8_7_3:",
        "R8.7.3 contract does not remain draft": "status: draft" not in text,
        "no stale R8.7.2 stage label": "R8.7.2" not in text,
    }
    for label, condition in identity_checks.items():
        if isinstance(condition, bool):
            _require(failures, f"missing identity invariant: {label!r}", condition)
        else:
            _require(failures, f"missing identity invariant: {label!r}", condition in text)

    # ------------------------------------------------------------
    # Authoritative semantic model and boundary ownership
    # ------------------------------------------------------------
    role = _section(text, "architectural_role:", "core_invariants:")
    _require(failures, "architectural_role section missing", bool(role))
    if role:
        for label, phrases in {
            "AcquisitionRequest input": ("name: AcquisitionRequest", "input_object:"),
            "AcquisitionAdapter authority": ("name: AcquisitionAdapter", "authority: acquisition_execution_boundary"),
            "AcquisitionExecutionReceipt output": ("name: AcquisitionExecutionReceipt", "authority: acquisition_execution_history"),
            "legacy retrieval interface": ("interface: List[str]", "current_status: existing_interface"),
            "EvidenceRecord remains separate": ("name: EvidenceRecord", "outside the adapter's semantic output boundary"),
        }.items():
            _require(failures, f"missing boundary invariant: {label!r}", all(p in role for p in phrases))

    core = _section(text, "core_invariants:", "input_boundary:")
    _require(failures, "core_invariants section missing", bool(core))
    if core:
        core_norm = _normalized(core)
        core_rules = (
            "AcquisitionRequest is the authoritative semantic model at this boundary.",
            "Semantic fidelity has priority over representation completeness.",
            "Loss of representation is acceptable only when the loss is explicit and observable.",
            "Existing retrieve_evidence_parallel(List[str]) semantics remain unchanged by this contract.",
        )
        for phrase in core_rules:
            _require(failures, f"missing core invariant: {phrase!r}", phrase in core_norm)

    # ------------------------------------------------------------
    # Translation policy: lossy by design, but semantically truthful
    # ------------------------------------------------------------
    translation = _section(text, "translation:", "field_translation:")
    _require(failures, "translation section missing", bool(translation))
    if translation:
        translation_norm = _normalized(translation)
        translation_rules = {
            "lossy translation mode": ("mode: lossy_by_design",),
            "semantic projection stage": ("construct a precise semantic projection",),
            "translation classification": ("classify material fields as preserved, translated, degraded, or unrepresentable",),
            "legacy projection": ("produce legacy execution representation from the representable projection",),
            "loss preserved as provenance": ("preserve material translation loss as execution provenance",),
            "no reconstruction by retrieval": ("must not be required to reconstruct the AcquisitionRequest from query strings",),
            "truthful distinction": ("requested semantics from semantics actually representable or enforceable",),
        }
        for label, phrases in translation_rules.items():
            _require(failures, f"missing translation invariant: {label!r}", _contains_any(translation_norm, phrases))

        for cls in ("preserved", "translated", "degraded", "unrepresentable"):
            _require(
                failures,
                f"missing translation class: {cls!r}",
                f"  {cls}:" in translation or f"\n    {cls}:" in translation,
            )

        for forbidden in (
            "encode provider preferences into query text",
            "encode provider access restrictions into query text",
            "convert process priority into scientific priority",
            "convert provider failure into evidence weakness",
            "convert empty results into literature absence",
            "convert operational constraints into epistemic claims",
        ):
            _require(
                failures,
                f"missing prohibited translation rule: {forbidden!r}",
                forbidden in translation,
            )

    # ------------------------------------------------------------
    # Concrete field mapping
    # ------------------------------------------------------------
    mapping = _section(text, "field_translation:", "execution_policy:")
    _require(failures, "field_translation section missing", bool(mapping))
    if mapping:
        mapping_norm = _normalized(mapping)
        field_rules = {
            "query_scope projection": (
                "source: AcquisitionRequest.target.query_scope",
                "target: List[str]",
                "class: translated",
            ),
            "provider preferences are unrepresentable": (
                "provider_preferences",
                "current_target_support: unavailable",
                "class_when_unrepresentable: unrepresentable",
            ),
            "provider access constraints are unrepresentable": (
                "provider_access_constraints",
                "current_target_support: unavailable",
                "class_when_unrepresentable: unrepresentable",
            ),
            "execution limits require exact equivalence": (
                "execution_limits",
                "current_target_support: partial_or_unknown",
                "exact semantic equivalent",
            ),
            "priority remains process metadata": (
                "process_priority",
                "current_target_support: adapter_metadata",
                "must not affect scientific ranking",
            ),
        }
        for label, phrases in field_rules.items():
            _require(failures, f"missing field translation invariant: {label!r}", all(p in mapping_norm for p in phrases))

    # ------------------------------------------------------------
    # Loss policy and execution semantics
    # ------------------------------------------------------------
    execution_policy = _section(text, "execution_policy:", "execution_provenance:")
    _require(failures, "execution_policy section missing", bool(execution_policy))
    if execution_policy:
        policy_norm = _normalized(execution_policy)
        for label, phrases in {
            "lossy execution allowed": ("lossy_execution_allowed: true",),
            "unsupported constraints may be lossy": ("does not automatically invalidate the entire AcquisitionRequest",),
            "unsupported loss is reported": ("recording the exact translation loss",),
            "no false enforcement claim": ("never claiming the unsupported constraint was applied",),
            "future mandatory constraint escape hatch": ("execution-mandatory", "future contract"),
            "empty projection does not invoke retrieval": ("retrieval execution must not be invoked merely to manufacture an outcome",),
        }.items():
            _require(failures, f"missing execution-policy invariant: {label!r}", all(p in policy_norm for p in phrases))

    # ------------------------------------------------------------
    # Execution provenance and receipt
    # ------------------------------------------------------------
    provenance = _section(text, "execution_provenance:", "receipt_fields:")
    _require(failures, "execution_provenance section missing", bool(provenance))
    if provenance:
        prov_norm = _normalized(provenance)
        for label, phrases in {
            "receipt output": ("output_object: AcquisitionExecutionReceipt",),
            "execution identity": ("execution_id", "one execution occurrence"),
            "request identity": ("acquisition_request_id", "AcquisitionRequest"),
            "translation provenance": ("translation_provenance", "material translation loss"),
            "separate retry occurrence": ("Each execution attempt is a separate occurrence", "new AcquisitionExecutionReceipt"),
        }.items():
            _require(failures, f"missing provenance invariant: {label!r}", all(p in prov_norm for p in phrases))

    receipt = _section(text, "receipt_fields:", "relationship_to_evidence:")
    _require(failures, "receipt_fields section missing", bool(receipt))
    if receipt:
        receipt_norm = _normalized(receipt)
        for field in (
            "execution_id",
            "acquisition_request_id",
            "started_at",
            "completed_at",
            "execution_status",
            "translation_policy_version",
            "translation_results",
            "translation_losses",
            "generated_query_inputs",
        ):
            _require(failures, f"receipt field not defined: {field!r}", field in receipt_norm)

    # ------------------------------------------------------------
    # Source-level vs execution-level provenance
    # ------------------------------------------------------------
    evidence = _section(text, "relationship_to_evidence:", "relationship_to_retrieval_runtime:")
    _require(failures, "relationship_to_evidence section missing", bool(evidence))
    if evidence:
        evidence_norm = _normalized(evidence)
        for label, phrases in {
            "execution receipt owns execution provenance": ("AcquisitionExecutionReceipt records why and how an acquisition execution occurred",),
            "EvidenceRecord owns source provenance": ("EvidenceRecord records source-level provenance",),
            "many-to-many protection": ("A source may be discovered by multiple acquisition requests or execution occurrences",),
            "no request id on EvidenceRecord": ("add acquisition_request_id to EvidenceRecord solely for adapter provenance",),
            "no translation-loss leakage": ("store translation loss in EvidenceRecord",),
        }.items():
            _require(failures, f"missing evidence-provenance invariant: {label!r}", all(p in evidence_norm for p in phrases))

    # ------------------------------------------------------------
    # Legacy retrieval boundary remains isolated
    # ------------------------------------------------------------
    retrieval = _section(text, "relationship_to_retrieval_runtime:", "execution_status_semantics:")
    _require(failures, "relationship_to_retrieval_runtime section missing", bool(retrieval))
    if retrieval:
        retrieval_norm = _normalized(retrieval)
        for label, phrases in {
            "existing function": ("current_function: retrieve_evidence_parallel",),
            "List[str] interface": ("current_input: List[str]",),
            "function signature preserved": ("does not alter the function signature",),
            "adapter translates": ("The adapter may invoke the existing retrieval execution boundary",),
            "retrieval remains unaware": ("maintain existing source-level evidence provenance",),
        }.items():
            _require(failures, f"missing retrieval-boundary invariant: {label!r}", all(p in retrieval_norm for p in phrases))

    # ------------------------------------------------------------
    # Operational-only statuses
    # ------------------------------------------------------------
    status = _section(text, "execution_status_semantics:", "authority_isolation:")
    _require(failures, "execution_status_semantics section missing", bool(status))
    if status:
        status_norm = _normalized(status)
        for phrase in (
            "operational_only: true",
            "failure != evidence_weakness",
            "failure != claim_uncertainty",
            "empty_result != literature_absence",
            "empty_result != evidence_gap",
            "rate_limited != evidence_weakness",
            "translation_loss != evidence_weakness",
            "translation_loss != evidence_gap",
            "translation_loss != claim_uncertainty",
        ):
            _require(failures, f"missing operational semantic isolation: {phrase!r}", phrase in status_norm)

    # ------------------------------------------------------------
    # Authority isolation
    # ------------------------------------------------------------
    authority = _section(text, "authority_isolation:", "failure_and_retry:")
    _require(failures, "authority_isolation section missing", bool(authority))
    if authority:
        authority_norm = _normalized(authority)
        prohibitions = (
            "create ResearchPlanningDecision",
            "create ResearchPlanningSignal",
            "create AttentionProposal",
            "create ScientificAttention",
            "create LifecycleEvent",
            "modify epistemic state",
            "modify confidence",
            "modify evidence strength",
            "modify claim ranking",
            "modify convergence",
            "rewrite AcquisitionRequest",
        )
        for phrase in prohibitions:
            _require(failures, f"missing authority prohibition: {phrase!r}", phrase in authority_norm)

    # ------------------------------------------------------------
    # Retry and lifecycle isolation
    # ------------------------------------------------------------
    retry = _section(text, "failure_and_retry:", "automatic_execution:")
    _require(failures, "failure_and_retry section missing", bool(retry))
    if retry:
        retry_norm = _normalized(retry)
        for label, phrases in {
            "new receipt per retry": ("new execution_id", "new AcquisitionExecutionReceipt"),
            "historical receipt retained": ("Earlier execution receipts remain historical records",),
            "multiple receipts per request": ("Multiple execution receipts may reference the same acquisition_request_id",),
            "no merge mutation": ("must not be represented by mutating one receipt",),
            "historical translation loss retained": ("must not rewrite what was unrepresentable during an earlier execution occurrence",),
        }.items():
            _require(failures, f"missing retry invariant: {label!r}", all(p in retry_norm for p in phrases))

    lifecycle = _section(text, "lifecycle_isolation:", "persistence:")
    _require(failures, "lifecycle_isolation section missing", bool(lifecycle))
    if lifecycle:
        lifecycle_norm = _normalized(lifecycle)
        for phrase in (
            "AcquisitionExecutionReceipt does not create a LifecycleEvent",
            "Execution success does not imply addressed or closed lifecycle state",
            "Execution failure does not imply open, addressed, or closed lifecycle state",
            "Translation loss does not imply lifecycle state",
            "AcquisitionAdapter has no lifecycle transition authority",
        ):
            _require(failures, f"missing lifecycle isolation rule: {phrase!r}", phrase in lifecycle_norm)

    # ------------------------------------------------------------
    # Contract-only / runtime exclusions
    # ------------------------------------------------------------
    non_decisions = _section(text, "non_decisions:", "relationship_to_r8_6_2:")
    _require(failures, "non_decisions section missing", bool(non_decisions))
    if non_decisions:
        for phrase in (
            "No provider-layer redesign is introduced by this contract.",
            "No EvidenceRecord schema changes are introduced by this contract.",
            "No RetrievalEvent model is required by this contract.",
            "No main.py integration is required by this contract.",
            "No pending_evidence_queries integration is required by this contract.",
            "No scientific interpretation is introduced by this contract.",
            "No lifecycle transition is introduced by this contract.",
        ):
            _require(failures, f"missing scope exclusion: {phrase!r}", phrase in non_decisions)

    # ------------------------------------------------------------
    # Static-only safety checks
    # ------------------------------------------------------------
    for forbidden in (
        "import requests",
        "import httpx",
        "import urllib",
        "requests.get(",
        "httpx.get(",
        "subprocess.run(",
        "from core",
        "import core",
    ):
        _require(failures, f"contract contains forbidden runtime coupling: {forbidden!r}", forbidden not in text)

    # `retrieve_evidence_parallel(List[str])` is interface notation, not an
    # invocation. Reject any additional call-like occurrence.
    call_like = re.findall(r"retrieve_evidence_parallel\s*\(", text)
    _require(
        failures,
        "contract contains retrieval call syntax beyond interface notation",
        len(call_like) <= 1,
    )

    # ------------------------------------------------------------
    # R8.7.3 generalized-method linkage
    # ------------------------------------------------------------
    r8 = _section(text, "relationship_to_r8_7_3:", "scope:")
    _require(failures, "relationship_to_r8_7_3 section missing", bool(r8))
    if r8:
        r8_norm = _normalized(r8)
        linkage_rules = {
            "authoritative semantic model": (
                "AcquisitionRequest is the authoritative semantic model",
                "authoritative semantic model",
            ),
            "deliberate lossy projection": (
                "translation into List[str] is a deliberate lossy projection",
                "deliberate lossy projection",
            ),
            "loss explicitly classified and observable": (
                "Material translation loss is explicitly classified and observable",
                "translation loss",
                "explicitly classified",
                "observable",
            ),
            "unsupported constraints not falsely enforced": (
                "Unsupported constraints are not falsely reported as enforced",
                "not falsely reported as enforced",
            ),
            "adapter remains replaceable": (
                "adapter remains replaceable",
                "The adapter remains replaceable",
                "remains replaceable",
            ),
        }
        for label, phrases in linkage_rules.items():
            _require(
                failures,
                f"missing R8.7.3 decision linkage: {label!r}",
                _contains_any(r8_norm, phrases),
            )

    if failures:
        print("R8.7.3 AcquisitionAdapter contract audit: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        f"R8.7.3 AcquisitionAdapter contract audit: PASS "
        f"({_require.check_count}/{_require.check_count} checks passed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

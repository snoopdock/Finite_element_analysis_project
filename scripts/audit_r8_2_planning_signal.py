#!/usr/bin/env python3
"""Read-only R8.2 audit for the AttentionProposal -> ResearchPlanningSignal boundary.

Run with:
    python -m scripts.audit_r8_2_planning_signal

This audit does not access the network, execute retrieval, mutate state, or
invoke scientific reasoning. It verifies the implemented translation boundary
against the R8.1 contract using synthetic process-attention data.
"""

from __future__ import annotations

import copy

from analysis.retrieval_attention_planning_signal import (
    SIGNAL_TYPE,
    TRANSLATION_POLICY_VERSION,
    translate_attention_proposal,
    validate_research_planning_signal,
)


BASE_PROPOSAL = {
    "attention_id": "attention-r8-audit",
    "policy_version": "r7b-v1",
    "query_scope": "weak form Galerkin FEM",
    "provider": "semantic_scholar",
    "attention_reason": "Repeated provider non-success observations.",
    "observed_condition": "repeated_query_provider_non_success",
    "lifecycle_status": "open",
    "supporting_event_ids": ["E12", "E13"],
    "recommended_acquisition_action": "use_alternate_provider",
}


def _check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS: {name}")


def main() -> None:
    proposal = copy.deepcopy(BASE_PROPOSAL)
    original = copy.deepcopy(proposal)
    signal = translate_attention_proposal(proposal)

    _check("translation produces a signal", isinstance(signal, dict))
    _check("signal type is acquisition_constraint", signal["signal_type"] == SIGNAL_TYPE)
    _check("signal has independent identity", signal["research_planning_signal_id"] != proposal["attention_id"])
    _check("source attention provenance is retained", signal["source_attention_id"] == proposal["attention_id"])
    _check("event provenance is retained", signal["provenance"]["supporting_event_ids"] == ["E12", "E13"])
    _check("provider constraint remains operational", signal["acquisition_constraint"]["provider_access_limitation"] is True)
    _check("translation policy is explicit", signal["translation_policy_version"] == TRANSLATION_POLICY_VERSION)
    _check("source proposal is not mutated", proposal == original)

    forbidden_output_fields = {
        "confidence",
        "confidence_score",
        "evidence_strength",
        "evidence_gap",
        "epistemic_status",
        "truth_status",
        "claim_ranking",
        "ranking_score",
        "convergence_score",
        "scientific_priority",
        "scientific_relevance",
        "scientific_importance",
    }
    _check(
        "scientific fields are absent",
        forbidden_output_fields.isdisjoint(signal),
    )
    _check("lifecycle status is not propagated", "lifecycle_status" not in signal)
    _check("acquisition command is not propagated", "recommended_acquisition_action" not in signal)
    _check("signal validates under R8.1", validate_research_planning_signal(signal) == signal)

    invalid = copy.deepcopy(signal)
    invalid["evidence_gap"] = True
    try:
        validate_research_planning_signal(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("validator accepted forbidden evidence_gap")
    print("PASS: forbidden scientific field is rejected")

    print("R8.2 planning-signal boundary audit: PASS (13 checks)")


if __name__ == "__main__":
    main()

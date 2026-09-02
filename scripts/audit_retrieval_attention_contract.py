#!/usr/bin/env python3
"""Audit the R6.5 retrieval-attention semantic contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "specs" / "contracts" / "retrieval_attention_contract.yaml"


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["version"] == 1
    assert contract["name"] == "retrieval_attention_contract"

    # Attention must remain scoped to query/provider/time rather than a
    # provider-wide or opaque aggregate interpretation.
    dimensions = contract["attention_unit"]["dimensions"]
    assert dimensions == [
        "query_scope",
        "provider",
        "temporal_history",
    ]
    required_context = set(contract["attention_unit"]["required_context"])
    assert {
        "affected_query",
        "affected_provider",
        "supporting_event_ids",
        "observed_temporal_history",
    } <= required_context

    # Trigger semantics must distinguish availability and empty retrieval,
    # and permit explicit repeated-condition detection without choosing a
    # universal threshold at R6.5.
    trigger_classes = set(contract["attention_trigger_classes"]["allowed"])
    assert "provider_unavailable" in trigger_classes
    assert "provider_partially_available" in trigger_classes
    assert "query_returned_empty_result" in trigger_classes
    assert "repeated_query_provider_non_success" in trigger_classes
    assert "repeated_query_provider_empty_result" in trigger_classes

    repetition = contract["repetition_rules"]
    assert "universal numeric repetition threshold" in repetition["threshold_policy"]
    assert "explicit, auditable" in repetition["threshold_policy"]
    assert "historical window" in repetition["temporal_window"]
    assert "prevent an earlier failure from remaining" in repetition["recovery_rule"]

    # The proposal is operational and must be traceable to historical events.
    output = contract["attention_output"]
    assert output["required_fields"] == [
        "attention_id",
        "attention_reason",
        "target_query",
        "affected_provider",
        "observed_condition",
        "recommended_acquisition_action",
        "supporting_event_ids",
    ]

    forbidden = set(output["forbidden_fields"])
    assert {
        "confidence",
        "truth_status",
        "epistemic_status",
        "support_strength",
        "scientific_relevance",
        "scientific_importance",
        "evidence_strength",
        "ranking_score",
        "convergence_status",
        "writer_decision",
    } <= forbidden

    actions = set(contract["action_vocabulary"]["allowed"])
    assert {
        "retry_provider",
        "retry_query",
        "reformulate_query",
        "expand_query_scope",
        "use_alternate_provider",
        "defer_until_provider_recovery",
    } <= actions

    isolation = contract["scientific_isolation"]
    protected = set(isolation["attention_logic_must_not_modify"])
    assert {
        "propositions",
        "evidence_relations",
        "epistemic_state",
        "evidence_strength",
        "truth_status",
        "ranking",
        "convergence",
        "writing_content",
    } <= protected

    interpretations = set(isolation["interpretation_rules"])
    assert "Operational failure is not scientific absence." in interpretations
    assert "Empty retrieval is not scientific absence." in interpretations
    assert "Provider availability is not evidence quality." in interpretations

    shortcuts = set(contract["integration_boundary"]["prohibited_shortcuts"])
    assert "generic_retrieval_quality_score" in shortcuts
    assert "generic_retrieval_confidence" in shortcuts
    assert "direct_rank_adjustment" in shortcuts
    assert "direct_convergence_adjustment" in shortcuts
    assert "direct_writer_instruction" in shortcuts

    excluded = set(contract["scope"]["excluded"])
    assert "numeric universal repetition thresholds" in excluded
    assert "literature coverage claims" in excluded
    assert "evidence quality scoring" in excluded
    assert "epistemic inference" in excluded
    assert "scientific proposition updates" in excluded
    assert "ranking implementation" in excluded
    assert "convergence implementation" in excluded
    assert "writer implementation" in excluded

    print("R6.5 retrieval attention contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Combined audit for the pre-Stage-8 epistemic hardening layer."""

from analysis.epistemic_state import normalize_epistemic_state
from analysis.relationship_support import normalize_relationship_support
from analysis.provenance_trace import normalize_provenance_trace
from analysis.negative_knowledge import normalize_negative_knowledge
from analysis.proposition_epistemic_type import normalize_epistemic_type
from analysis.proposition_temporal_status import normalize_temporal_status
from analysis.proposition_causal_status import normalize_causal_status


def main() -> int:
    epistemic = normalize_epistemic_state({
        "status": "disputed",
        "evidence_strength": "strong",
        "literature_agreement": "mixed",
        "model_confidence": 1.2,
    })
    assert epistemic["status"] == "disputed"
    assert epistemic["evidence_strength"] == "strong"
    assert epistemic["literature_agreement"] == "mixed"
    assert epistemic["model_confidence"] == 1.0

    support = normalize_relationship_support({
        "relationship_id": "R1",
        "proposition_ids": ["P1"],
        "source_ids": ["S1"],
        "evidence_relation_ids": ["ER1"],
        "validity_ids": ["V1"],
        "rationale": "Existing evidence supports this relationship candidate.",
    })
    assert support is not None
    assert support["status"] == "proposed"
    assert support["evidence_relation_ids"] == ["ER1"]

    trace = normalize_provenance_trace({
        "operation": "verify_relationship",
        "input_ids": ["P1", "ER1"],
        "output_ids": ["R1"],
        "model": "example-model",
        "parameters": {"max_tokens": 500},
    })
    assert trace is not None
    assert trace["operation"] == "verify_relationship"
    assert "hidden_reasoning" not in trace

    negative = normalize_negative_knowledge({
        "entity_id": "R1",
        "entity_type": "relationship",
        "status": "rejected_for_insufficient_evidence",
        "reason": "Only lexical similarity was found.",
        "future_recheck": True,
    })
    assert negative is not None
    assert negative["status"] == "rejected_for_insufficient_evidence"

    assert normalize_epistemic_type("causal") == "causal"
    assert normalize_epistemic_type("unknown-label") == "unknown"
    assert normalize_temporal_status("historical") == "historical"
    assert normalize_temporal_status("newer-is-better") == "unknown"
    assert normalize_causal_status("associational") == "associational"
    assert normalize_causal_status("correlation-implies-cause") == "unknown"

    print("Pre-Stage-8 hardening combined audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

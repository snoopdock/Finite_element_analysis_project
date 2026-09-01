#!/usr/bin/env python3
"""Audit persistence of epistemic assessments."""

from core.epistemic_state_store import record_epistemic_state, record_epistemic_states


def main() -> int:
    state = {"knowledge_graph": {"propositions": {"P1": {}}, "relationships": {"R1": {}}}}
    assert record_epistemic_state(
        state,
        "P1",
        {"status": "supported", "evidence_strength": "strong"},
        entity_type="proposition",
    )
    assert record_epistemic_state(
        state,
        "R1",
        {"status": "disputed", "literature_agreement": "mixed"},
        entity_type="relationship",
    )
    saved = state["knowledge_graph"]["epistemic_states"]
    assert saved["proposition:P1"]["status"] == "supported"
    assert saved["relationship:R1"]["status"] == "disputed"
    assert state["knowledge_graph"]["propositions"]["P1"] == {}
    assert state["knowledge_graph"]["relationships"]["R1"] == {}

    count = record_epistemic_states(
        state,
        [
            {"entity_id": "P2", "status": "conditional"},
            {"entity_id": "P3", "status": "unknown"},
        ],
        max_records=2,
    )
    assert count == 2
    assert len(state["knowledge_graph"]["epistemic_states"]) == 2

    assert record_epistemic_states(state, [], max_records=0) == 0
    assert state["knowledge_graph"]["epistemic_states"] == {}

    print("Stage 7.5B epistemic-state store audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

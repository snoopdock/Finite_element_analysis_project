#!/usr/bin/env python3
"""Audit persistence of scientific-attention signals."""

from core.scientific_attention_state import record_scientific_attention


def main() -> int:
    state = {"knowledge_graph": {}}
    assert record_scientific_attention(
        state,
        "section-1",
        {"evidence_gap": 1.2, "disagreement": 0.6},
        entity_type="section",
    )
    saved = state["knowledge_graph"]["scientific_attention"]["section:section-1"]
    assert saved["signals"]["evidence_gap"] == 1.0
    assert saved["signals"]["disagreement"] == 0.6
    assert 0.0 <= saved["priority_hint"] <= 1.0
    assert saved["entity_type"] == "section"

    assert record_scientific_attention(
        state,
        "P1",
        {"importance": 0.9},
        entity_type="proposition",
    )
    assert "proposition:P1" in state["knowledge_graph"]["scientific_attention"]

    assert not record_scientific_attention(state, "", {})

    print("Scientific attention state audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

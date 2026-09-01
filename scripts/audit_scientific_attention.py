#!/usr/bin/env python3
"""Audit non-scalar scientific attention signals."""

from analysis.scientific_attention import ScientificAttention, attention_priority, normalize_attention


def main() -> int:
    raw = {
        "evidence_gap": 1.4,
        "disagreement": -1,
        "contextual_complexity": 0.5,
        "verification_need": "0.25",
        "importance": "bad",
        "decision_consequence": 0.75,
    }
    normalized = normalize_attention(raw)
    assert normalized["evidence_gap"] == 1.0
    assert normalized["disagreement"] == 0.0
    assert normalized["verification_need"] == 0.25
    assert normalized["importance"] == 0.0
    assert 0.0 <= attention_priority(raw) <= 1.0

    object_form = ScientificAttention(importance=1.0)
    assert normalize_attention(object_form)["importance"] == 1.0

    # Signals remain separately observable; the derived score does not replace them.
    assert set(normalized) == {
        "evidence_gap",
        "disagreement",
        "contextual_complexity",
        "verification_need",
        "importance",
        "decision_consequence",
    }

    print("Scientific attention audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

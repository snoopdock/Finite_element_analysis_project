#!/usr/bin/env python3
"""Audit separation of epistemic dimensions."""

from analysis.epistemic_state import (
    EPISTEMIC_STATUSES,
    EVIDENCE_STRENGTHS,
    LITERATURE_AGREEMENT,
    EpistemicState,
    normalize_epistemic_state,
)


def main() -> int:
    assert "disputed" in EPISTEMIC_STATUSES
    assert "insufficient_evidence" in EPISTEMIC_STATUSES
    assert "strong" in EVIDENCE_STRENGTHS
    assert "mixed" in LITERATURE_AGREEMENT

    state = EpistemicState(
        status="disputed",
        evidence_strength="moderate",
        literature_agreement="mixed",
        model_confidence=1.7,
        independent_support="mixed",
        limitations=["limited domain", "limited domain"],
    ).normalized()
    assert state["status"] == "disputed"
    assert state["evidence_strength"] == "moderate"
    assert state["literature_agreement"] == "mixed"
    assert state["model_confidence"] == 1.0
    assert state["limitations"] == ["limited domain"]

    unknown = normalize_epistemic_state({
        "status": "not-a-status",
        "evidence_strength": "not-a-strength",
        "literature_agreement": "not-an-agreement",
        "model_confidence": "not-a-number",
    })
    assert unknown["status"] == "unknown"
    assert unknown["evidence_strength"] == "unknown"
    assert unknown["literature_agreement"] == "unknown"
    assert unknown["model_confidence"] is None

    print("Stage 7.5A epistemic-state audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

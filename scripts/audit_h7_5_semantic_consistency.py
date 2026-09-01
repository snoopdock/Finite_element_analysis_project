#!/usr/bin/env python3
"""Cross-layer semantic consistency checks for the scientific graph."""

from analysis.epistemic_state import normalize_epistemic_state
from analysis.scope_inheritance_policy import validate_no_implicit_inheritance
from analysis.scope_aware_contradiction import classify_proposition_pair


def main() -> int:
    # Evidence support and a disputed epistemic state may coexist.
    disputed = normalize_epistemic_state({
        "status": "disputed",
        "evidence_strength": "strong",
        "literature_agreement": "mixed",
        "model_confidence": 0.9,
    })
    assert disputed["status"] == "disputed"
    assert disputed["evidence_strength"] == "strong"

    # Conditional validity and strong support are compatible.
    conditional = normalize_epistemic_state({
        "status": "supported",
        "evidence_strength": "strong",
    })
    assert conditional["status"] == "supported"

    # Alternative relationships do not imply mutually exclusive truth status.
    relationship = {
        "type": "alternative_to",
        "reason": "different formulations",
    }
    assert validate_no_implicit_inheritance(relationship) == []

    # A relationship cannot smuggle validity or epistemic state into its endpoints.
    forbidden = {
        "type": "alternative_to",
        "validity_scope": {"type": "conditional"},
        "epistemic_state": {"status": "supported"},
    }
    assert len(validate_no_implicit_inheritance(forbidden)) == 2

    # Different validity conditions can explain an apparent disagreement.
    left = {
        "statement": "method a is stable",
        "validity_scope": {"framework": "F", "conditions": ["small deformation"]},
    }
    right = {
        "statement": "method a is unstable",
        "validity_scope": {"framework": "F", "conditions": ["large deformation"]},
    }
    result = classify_proposition_pair(left, right)
    assert result["classification"] == "scope_mismatch"
    assert result["scientific_truth_resolved"] is False

    print("H7.5 semantic-consistency audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

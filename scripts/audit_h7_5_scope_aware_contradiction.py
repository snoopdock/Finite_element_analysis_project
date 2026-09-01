#!/usr/bin/env python3
"""Audit scope-aware contradiction classification."""

from analysis.scope_aware_contradiction import classify_proposition_pair, classify_scope_relationship


def main() -> int:
    a = {"framework": "FEM", "conditions": ["linear"]}
    b = {"framework": "FEM", "conditions": ["nonlinear"]}
    assert classify_scope_relationship(a, b) == "scope_mismatch"

    c = {"framework": "FEM", "conditions": ["linear", "coercive"]}
    d = {"framework": "FEM", "conditions": ["coercive"]}
    assert classify_scope_relationship(c, d) == "potential_conflict"

    e = {"framework": "FEM", "conditions": []}
    assert classify_scope_relationship(c, e) == "insufficient_information"

    same = {
        "statement": "method a is stable",
        "validity_scope": {"framework": "FEM", "conditions": ["linear"]},
    }
    assert classify_proposition_pair(same, dict(same))["classification"] == "no_conflict"

    x = {
        "statement": "method a is stable",
        "validity_scope": {"framework": "FEM", "conditions": ["linear"]},
    }
    y = {
        "statement": "method a is unstable",
        "validity_scope": {"framework": "FEM", "conditions": ["linear"]},
    }
    result = classify_proposition_pair(x, y)
    assert result["classification"] == "potential_conflict"
    assert result["scientific_truth_resolved"] is False

    print("H7.5 scope-aware contradiction audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit conservative comparison of validity scopes."""

from analysis.validity_scope_conflicts import compare_validity_scopes, compare_scope_pairs


def main() -> int:
    base = {
        "validity_id": "V1",
        "proposition_id": "P1",
        "type": "conditional",
        "framework": "FEM",
        "conditions": ["coercivity"],
    }
    nested = {
        "validity_id": "V2",
        "proposition_id": "P1",
        "type": "conditional",
        "framework": "FEM",
        "conditions": ["coercivity", "bounded domain"],
    }
    result = compare_validity_scopes(base, nested)
    assert result["status"] == "compatible_or_overlapping"
    assert result["scientific_resolution"] == "not_performed"

    other_framework = dict(base, validity_id="V3", framework="FVM")
    result = compare_validity_scopes(base, other_framework)
    assert result["status"] == "different_framework"
    assert "different_framework" in result["conflict_signals"]

    disjoint = dict(base, validity_id="V4", conditions=["condition A"])
    other = dict(base, validity_id="V5", conditions=["condition B"])
    result = compare_validity_scopes(disjoint, other)
    assert result["status"] == "disjoint_conditions"

    different_prop = dict(base, proposition_id="P2", validity_id="V6")
    result = compare_validity_scopes(base, different_prop)
    assert result["status"] == "not_comparable"

    sparse = {"validity_id": "V7", "proposition_id": "P1"}
    sparse2 = {"validity_id": "V8", "proposition_id": "P1"}
    result = compare_validity_scopes(sparse, sparse2)
    assert result["status"] == "insufficient_scope_information"

    pairs = compare_scope_pairs([base, nested, other_framework], max_pairs=2)
    assert len(pairs) == 2

    print("Stage 4.5E validity conflict audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

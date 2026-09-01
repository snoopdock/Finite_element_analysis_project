#!/usr/bin/env python3
"""Audit relationship-support provenance and normalization."""

from analysis.relationship_support import normalize_relationship_support


def main() -> int:
    record = normalize_relationship_support({
        "relationship_id": "R1",
        "proposition_ids": ["P2", "P1", "P1"],
        "source_ids": ["S2", "S1"],
        "evidence_relation_ids": ["ER2", "ER1"],
        "validity_ids": ["V1"],
        "mechanism": "same formulation",
        "conditions": ["coercivity", "coercivity"],
        "rationale": "Supported by independent propositions.",
    })
    assert record is not None
    assert record["proposition_ids"] == ["P1", "P2"]
    assert record["source_ids"] == ["S1", "S2"]
    assert record["evidence_relation_ids"] == ["ER1", "ER2"]
    assert record["conditions"] == ["coercivity"]
    assert record["status"] == "proposed"

    # Support records must retain provenance rather than imply verification.
    assert "verified" not in record
    assert "scientifically_confirmed" not in record

    assert normalize_relationship_support({"relationship_id": ""}) is None

    print("Stage 7.5C relationship-support audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

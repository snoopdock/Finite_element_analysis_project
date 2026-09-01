#!/usr/bin/env python3
"""Audit evidence-independence grouping and non-consensus aggregation."""

from analysis.evidence_independence import independent_source_count, relation_aggregation_summary


def main() -> int:
    records = [
        {"source_id": "S1", "relationship": "supports"},
        {"source_id": "S2", "relationship": "supports", "cites_source_ids": ["S1"]},
        {"source_id": "S3", "relationship": "challenges"},
        {"source_id": "S4", "relationship": "qualifies", "derived_from_source_ids": ["S3"]},
    ]
    # S1/S2 and S3/S4 are two provenance-connected groups.
    assert independent_source_count(records) == 2

    summary = relation_aggregation_summary(records)
    assert summary["relation_counts"] == {
        "challenges": 1,
        "qualifies": 1,
        "supports": 2,
    }
    assert summary["independent_source_count"] == 2
    assert summary["scientific_consensus_inferred"] is False

    empty = relation_aggregation_summary([])
    assert empty["independent_source_count"] == 0
    assert empty["scientific_consensus_inferred"] is False

    print("H7.5 evidence-independence audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

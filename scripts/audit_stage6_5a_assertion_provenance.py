#!/usr/bin/env python3
"""Audit the Stage 6.5A assertion provenance model."""

from analysis.assertion_provenance import AssertionRecord, normalize_assertion


def main() -> int:
    record = AssertionRecord(
        assertion_id="A1",
        proposition_id="P1",
        source_id="S1",
        role="supports",
        evidence_relation_ids=["ER1", "ER1"],
        passage_ids=["L1", "L1"],
        validity_id="V1",
        provenance={"method": "literature_extraction"},
    )
    assert record.role == "supports"
    assert record.evidence_relation_ids == ["ER1"]
    assert record.passage_ids == ["L1"]
    assert record.proposition_id == "P1"
    assert record.source_id == "S1"

    normalized = normalize_assertion(record.to_dict())
    assert normalized == record.to_dict()

    assert normalize_assertion({
        "assertion_id": "A2",
        "proposition_id": "P1",
        "source_id": "S2",
        "role": "not-a-role",
    }) is None

    try:
        AssertionRecord(
            assertion_id="A3",
            proposition_id="P1",
            source_id="S3",
            role="supports",
            status="verified",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("assertion provenance must not establish verification")

    print("Stage 6.5A assertion provenance audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

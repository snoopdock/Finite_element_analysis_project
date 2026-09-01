#!/usr/bin/env python3
"""Audit typed negative-knowledge states."""

from analysis.negative_knowledge import NEGATIVE_STATUSES, normalize_negative_knowledge


def main() -> int:
    assert "unresolved" in NEGATIVE_STATUSES
    assert "disproven" in NEGATIVE_STATUSES
    assert "superseded" in NEGATIVE_STATUSES

    record = normalize_negative_knowledge({
        "entity_id": "P1",
        "entity_type": "proposition",
        "status": "rejected_for_insufficient_evidence",
        "reason": "Only lexical similarity was found.",
        "evidence_relation_ids": ["ER2", "ER1", "ER1"],
        "provenance_trace_ids": ["T2", "T1"],
        "future_recheck": True,
    })
    assert record is not None
    assert record["status"] == "rejected_for_insufficient_evidence"
    assert record["evidence_relation_ids"] == ["ER1", "ER2"]
    assert record["provenance_trace_ids"] == ["T1", "T2"]
    assert record["future_recheck"] is True
    assert record["entity_id"] == "P1"

    assert normalize_negative_knowledge({
        "entity_id": "P1",
        "entity_type": "proposition",
        "status": "rejected",
        "reason": "x",
    }) is None
    assert normalize_negative_knowledge({
        "entity_id": "P1",
        "entity_type": "proposition",
        "status": "disproven",
        "reason": "",
    }) is None

    print("Stage 7.5E negative-knowledge audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

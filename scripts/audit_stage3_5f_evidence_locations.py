#!/usr/bin/env python3
"""Read-only audit for Stage 3.5F source-local evidence locations."""

from __future__ import annotations

from analysis.evidence_locations import evidence_location_id, make_evidence_location, normalize_evidence_location


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    location = {
        "section_type": "results",
        "section_title": "Convergence study",
        "page": 12,
        "char_start": 1500,
        "char_end": 1740,
        "passage_id": "passage-7",
        "locator_text": "The error decreases as the mesh is refined.",
    }

    first = make_evidence_location("source-001", location)
    second = make_evidence_location("source-001", location)

    check(first["evidence_location_id"] == second["evidence_location_id"], "Location identity is not deterministic")
    check(first["source_id"] == "source-001", "Source identity was lost")
    check(first["page"] == 12, "Page was not preserved")
    check(first["char_start"] == 1500 and first["char_end"] == 1740, "Character range was not preserved")
    check(first["passage_id"] == "passage-7", "Passage identity was lost")

    unknown = normalize_evidence_location({"page": "not-a-number", "char_start": "bad", "char_end": None})
    check(unknown["page"] is None, "Malformed page was invented or preserved incorrectly")
    check(unknown["char_start"] is None, "Malformed character offset was not cleared")
    check(unknown["char_end"] is None, "Missing character end should remain unknown")

    explicit_id = evidence_location_id("source-001", passage_id="passage-7")
    check(explicit_id == evidence_location_id("source-001", passage_id="passage-7"), "Passage-based identity is unstable")

    print("Stage 3.5F evidence-location audit: PASS")


if __name__ == "__main__":
    main()

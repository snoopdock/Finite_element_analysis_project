#!/usr/bin/env python3
"""Audit temporal proposition metadata as descriptive, not truth-ranking."""

from analysis.proposition_temporal_status import (
    TEMPORAL_STATUSES,
    normalize_temporal_metadata,
    normalize_temporal_status,
)


def main() -> int:
    assert "historical" in TEMPORAL_STATUSES
    assert "current" in TEMPORAL_STATUSES
    assert "superseded" in TEMPORAL_STATUSES
    assert normalize_temporal_status(" CURRENT ") == "current"
    assert normalize_temporal_status("newer-is-better") == "unknown"

    metadata = normalize_temporal_metadata({
        "temporal_status": "historical",
        "first_supported_at": "2001",
        "last_reviewed_at": "2026-09-01",
        "superseded_by": "",
        "source_year": 2026,
    })
    assert metadata is not None
    assert metadata["temporal_status"] == "historical"
    assert metadata["source_year"] == 2026
    assert metadata["superseded_by"] is None

    # Dates are retained as metadata; they do not automatically determine status.
    current = normalize_temporal_metadata({"first_supported_at": "2026"})
    assert current["temporal_status"] == "unknown"

    print("Stage 6.5D temporal-status audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

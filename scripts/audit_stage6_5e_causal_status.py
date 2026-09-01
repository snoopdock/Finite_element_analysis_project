#!/usr/bin/env python3
"""Audit causal/descriptive proposition metadata as classification, not truth."""

from analysis.proposition_causal_status import (
    CAUSAL_STATUSES,
    normalize_causal_metadata,
    normalize_causal_status,
)


def main() -> int:
    assert "causal" in CAUSAL_STATUSES
    assert "associational" in CAUSAL_STATUSES
    assert normalize_causal_status(" Associational ") == "associational"
    assert normalize_causal_status("predictive") == "predictive"
    assert normalize_causal_status("correlation-implies-cause") == "unknown"

    metadata = normalize_causal_metadata({
        "causal_status": "associational",
        "causal_mechanism": "",
        "design_basis": "observational comparison",
        "extra": "preserved",
    })
    assert metadata is not None
    assert metadata["causal_status"] == "associational"
    assert metadata["causal_mechanism"] is None
    assert metadata["design_basis"] == "observational comparison"
    assert metadata["extra"] == "preserved"

    # Classification must not create truth or verification semantics.
    assert "verified" not in metadata
    assert "truth" not in metadata

    print("Stage 6.5E causal-status audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

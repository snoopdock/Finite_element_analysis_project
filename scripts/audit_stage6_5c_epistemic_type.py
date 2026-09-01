#!/usr/bin/env python3
"""Audit proposition epistemic-type normalization."""

from analysis.proposition_epistemic_type import (
    PROPOSITION_EPISTEMIC_TYPES,
    normalize_epistemic_type,
    normalize_proposition_epistemic_metadata,
)


def main() -> int:
    assert "observation" in PROPOSITION_EPISTEMIC_TYPES
    assert "causal" in PROPOSITION_EPISTEMIC_TYPES
    assert normalize_epistemic_type(" Causal ") == "causal"
    assert normalize_epistemic_type("not-a-scientific-type") == "unknown"
    metadata = normalize_proposition_epistemic_metadata({
        "epistemic_type": "measurement",
        "basis": "instrument reading",
        "note": "retained",
    })
    assert metadata is not None
    assert metadata["epistemic_type"] == "measurement"
    assert metadata["basis"] == "instrument reading"
    assert metadata["note"] == "retained"

    # Classification must not create a scientific truth/verification field.
    assert "verified" not in metadata
    assert "truth" not in metadata

    print("Stage 6.5C proposition epistemic-type audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

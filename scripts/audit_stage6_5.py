#!/usr/bin/env python3
"""Combined Stage 6.5 scientific provenance/meaning audit."""

from analysis.assertion_provenance import AssertionRecord
from analysis.assertion_identity import assertion_id
from analysis.proposition_epistemic_type import normalize_epistemic_type
from analysis.proposition_temporal_status import normalize_temporal_status
from analysis.proposition_causal_status import normalize_causal_status


def main() -> int:
    assertion = AssertionRecord(
        assertion_id=assertion_id("P1", "S1", "supports", ["L1"]),
        proposition_id="P1",
        source_id="S1",
        role="supports",
        passage_ids=["L1"],
        validity_id="V1",
        provenance={"method": "literature_extraction"},
    )
    assert assertion.assertion_id == assertion_id("P1", "S1", "supports", ["L1"])
    assert normalize_epistemic_type("observation") == "observation"
    assert normalize_epistemic_type("not-valid") == "unknown"
    assert normalize_temporal_status("historical") == "historical"
    assert normalize_temporal_status("newer-wins") == "unknown"
    assert normalize_causal_status("associational") == "associational"
    assert normalize_causal_status("correlation-implies-cause") == "unknown"

    # These metadata layers remain descriptive classifications, not truth assertions.
    assert assertion.status == "proposed"
    print("Stage 6.5 combined audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

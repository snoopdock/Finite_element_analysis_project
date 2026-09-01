#!/usr/bin/env python3
"""Audit auditable provenance traces without hidden-reasoning capture."""

from analysis.provenance_trace import normalize_provenance_trace, trace_id_from_payload


def main() -> int:
    trace = normalize_provenance_trace({
        "operation": "verify_relationship",
        "input_ids": ["P2", "P1", "P1"],
        "output_ids": ["R1"],
        "model": "example-model",
        "parameters": {"max_tokens": 500},
        "timestamp": "2026-09-01T00:00:00Z",
        "software_version": "dev",
        "hidden_reasoning": "must not be treated as provenance",
    })
    assert trace is not None
    assert trace["input_ids"] == ["P1", "P2"]
    assert trace["output_ids"] == ["R1"]
    assert trace["model"] == "example-model"
    assert "hidden_reasoning" not in trace
    expected = trace_id_from_payload(
        "verify_relationship", ["P1", "P2"], ["R1"], {"max_tokens": 500}
    )
    assert trace["trace_id"] == expected

    reordered = normalize_provenance_trace({
        "operation": "verify_relationship",
        "input_ids": ["P2", "P1"],
        "output_ids": ["R1"],
        "parameters": {"max_tokens": 500},
    })
    assert reordered["trace_id"] == trace["trace_id"]

    assert normalize_provenance_trace({"operation": ""}) is None
    print("Stage 7.5D provenance-trace audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

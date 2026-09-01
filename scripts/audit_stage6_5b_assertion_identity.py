#!/usr/bin/env python3
"""Audit deterministic assertion identity and order-independent passage handling."""

from analysis.assertion_identity import assertion_id, attach_assertion_identity


def main() -> int:
    first = assertion_id("P1", "S1", "supports", ["L2", "L1"])
    second = assertion_id("P1", "S1", "supports", ["L1", "L2"])
    assert first == second

    different_role = assertion_id("P1", "S1", "challenges", ["L1", "L2"])
    assert first != different_role

    different_source = assertion_id("P1", "S2", "supports", ["L1", "L2"])
    assert first != different_source

    attached = attach_assertion_identity({
        "proposition_id": "P1",
        "source_id": "S1",
        "role": "supports",
        "passage_ids": ["L2", "L1"],
    })
    assert attached is not None
    assert attached["assertion_id"] == first

    assert attach_assertion_identity({"proposition_id": "P1", "source_id": "", "role": "supports"}) is None

    print("Stage 6.5B assertion identity audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

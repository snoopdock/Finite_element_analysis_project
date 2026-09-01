#!/usr/bin/env python3
"""Audit prevention of implicit scientific scope/status inheritance."""

from analysis.scope_inheritance_policy import inheritance_allowed, validate_no_implicit_inheritance


def main() -> int:
    assert not inheritance_allowed("specializes", "validity_scope")
    assert not inheritance_allowed("related_to", "epistemic_state")
    assert not inheritance_allowed("extends", "evidence_relation_ids")
    assert not inheritance_allowed("alternative_to", "temporal_status")

    relationship = {
        "type": "specializes",
        "relationship_id": "r1",
        "validity_scope": {"type": "conditional"},
        "epistemic_state": {"status": "supported"},
    }
    errors = validate_no_implicit_inheritance(relationship)
    assert len(errors) == 2

    ordinary = {"type": "specializes", "relationship_id": "r2", "reason": "explicit specialization"}
    assert validate_no_implicit_inheritance(ordinary) == []

    print("H7.5 scope-inheritance audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

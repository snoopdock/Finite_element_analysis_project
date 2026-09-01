#!/usr/bin/env python3
"""Audit semantic ownership rules for overlapping scientific fields."""

from analysis.semantic_field_ownership import can_overwrite, field_role


def main() -> int:
    assert field_role("evidence", "conditions") == "reported_by_source"
    assert field_role("validity_scope", "conditions") == "governs_claim_applicability"

    # Different semantic roles must not overwrite each other.
    assert not can_overwrite("validity_scope", "conditions", "evidence")
    assert not can_overwrite("proposition", "framework", "assertion")

    # Unknown fields/layers have no implicit overwrite permission.
    assert field_role("unknown", "conditions") is None
    assert not can_overwrite("proposition", "unknown_field", "evidence")

    print("H7.5 field-ownership audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

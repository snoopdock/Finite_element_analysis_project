#!/usr/bin/env python3
"""Audit the pre-Stage-8 integration harness configuration without running it."""

from pathlib import Path

EXPECTED = [
    "audit_h1_scientific_object_composition.py",
    "audit_h2_state_roundtrip.py",
    "audit_h3_provenance_closure.py",
    "audit_h4_writer_compatibility.py",
    "audit_h5_graph_enrichment.py",
    "audit_h6_fem_literature_fixture.py",
    "audit_h7_failure_matrix.py",
    "audit_h7_5_field_ownership.py",
    "audit_h7_5_scope_inheritance.py",
    "audit_h7_5_evidence_independence.py",
    "audit_h7_5_scope_aware_contradiction.py",
    "audit_h7_5_semantic_consistency.py",
]


def main() -> int:
    scripts_dir = Path(__file__).resolve().parent
    missing = [name for name in EXPECTED if not (scripts_dir / name).exists()]
    assert not missing, f"missing audit scripts: {missing}"

    harness = scripts_dir / "run_scientific_integration_audit.py"
    assert harness.exists(), "missing integration harness"

    text = harness.read_text(encoding="utf-8")
    for name in EXPECTED:
        assert name in text, f"harness does not reference {name}"

    print("H8 harness configuration audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

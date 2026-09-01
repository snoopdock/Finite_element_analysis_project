#!/usr/bin/env python3
"""Audit compatibility of enriched scientific metadata with the legacy writer boundary."""

import inspect

from core.writer_orchestration import _replace_paragraph, phase_write_policy_aware


def main() -> int:
    enriched_section = {
        "section_id": "section-001",
        "content": "Original paragraph.",
        "status": "complete",
        "citations_used": ["S1"],
        "scientific_metadata": {
            "proposition_id": "p-001",
            "validity_scope_ids": ["v-001"],
            "evidence_relation_ids": ["er-001"],
            "assertion_ids": ["a-001"],
            "epistemic_state": {"status": "conditional"},
            "perspective_signature_id": "perspective-001",
        },
    }

    replacement = _replace_paragraph(enriched_section, 0, "Rewritten paragraph.")
    assert replacement is not None
    assert replacement["section_id"] == enriched_section["section_id"]
    assert replacement["scientific_metadata"] == enriched_section["scientific_metadata"]
    assert replacement["content"] == "Rewritten paragraph."

    signature = inspect.signature(phase_write_policy_aware)
    expected = {
        "config", "state", "paths", "provider", "parser", "errors", "delay",
        "budget", "iteration_history", "oaa_loop", "section_topics"
    }
    assert expected.issubset(signature.parameters)

    print("H4 writer compatibility audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

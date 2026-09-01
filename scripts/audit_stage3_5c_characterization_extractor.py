#!/usr/bin/env python3
"""Read-only audit for Stage 3.5C full-text evidence characterization."""

from __future__ import annotations

from analysis.evidence_characterization_extractor import extract_evidence_characterization


class StubProvider:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def budget_exhausted(self) -> bool:
        return False

    def chat(self, messages, *, temperature, max_tokens, model=None):
        self.calls += 1
        return self.response, ""


class StubParser:
    def parse(self, text: str, model_name: str = ""):
        return {
            "study_type": "simulation",
            "evidence_role": "primary",
            "primary_or_secondary": "primary",
            "methodological_description": "Finite element simulations were evaluated.",
            "limitations": ["Limited parameter range."],
            "notes": [],
            "publication_status": "peer_reviewed",
            "replication_status": "replicated",
        }


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    provider = StubProvider('{"study_type":"simulation"}')
    result = extract_evidence_characterization(
        {
            "source_id": "source-001",
            "title": "Example study",
            "source_type": "academic",
        },
        ["The study evaluates the numerical method over several parameter sets."],
        provider,
        StubParser(),
    )

    check(not result["skipped"], "Characterization unexpectedly skipped.")
    characterization = result["characterization"]
    check(characterization["study_type"] == "simulation", "Study type was not extracted.")
    check(characterization["publication_status"] == "unknown", "Publication status was inferred without metadata.")
    check(characterization["replication_status"] == "unknown", "Replication status was inferred without metadata.")
    check(provider.calls == 1, "Unexpected LLM call count.")

    exhausted = StubProvider("{}")
    exhausted.budget_exhausted = lambda: True
    skipped = extract_evidence_characterization(
        {"source_id": "source-002"},
        ["Full text passage."],
        exhausted,
        StubParser(),
    )
    check(skipped["skipped"], "Budget exhaustion did not skip extraction.")
    check(exhausted.calls == 0, "Budget exhaustion still called the provider.")

    missing_text = extract_evidence_characterization(
        {"source_id": "source-003"},
        [],
        StubProvider("{}"),
        StubParser(),
    )
    check(missing_text["skipped"], "Missing source passages did not skip extraction.")

    print("Stage 3.5C evidence characterization extractor audit")
    print("====================================================")
    print("PASS: source-backed extraction, conservative publication/replication handling, budget gating, and missing-text safety passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

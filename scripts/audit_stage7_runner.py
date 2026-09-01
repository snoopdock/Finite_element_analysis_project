#!/usr/bin/env python3
"""Read-only audit for the optional Stage 7 concept-relationship runner."""

from __future__ import annotations

from analysis.run_concept_relationship_analysis import run_concept_relationship_analysis


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class NoCallProvider:
    def __init__(self) -> None:
        self.calls = 0

    def budget_exhausted(self) -> bool:
        return False

    def chat(self, *args, **kwargs):
        self.calls += 1
        return "{}", None


def main() -> int:
    try:
        state = {"knowledge_graph": {"concepts": {}, "propositions": {}, "relationships": {}}}
        provider = NoCallProvider()
        parser = object()

        disabled = run_concept_relationship_analysis(
            state, provider, parser, {"semantic_verification": {"concept_relationship_enabled": False}}
        )
        check(disabled["enabled"] is False, "Disabled runner executed as enabled.")
        check(provider.calls == 0, "Disabled runner consumed provider calls.")

        enabled_config = {
            "semantic_verification": {
                "concept_relationship_enabled": True,
                "max_concept_relationship_pairs_per_cycle": 0,
                "max_concept_relationship_propositions_per_pair": 0,
                "concept_relationship_max_records": 0,
                "concept_relationship_max_tokens": 1,
            }
        }
        enabled = run_concept_relationship_analysis(state, provider, parser, enabled_config)
        check(enabled["enabled"] is True, "Enabled runner did not report enabled state.")
        check(enabled["candidates"] == 0, "Zero pair limit was not enforced.")
        check(provider.calls == 0, "No candidate pairs should mean no provider calls.")

        print("Stage 7 runner audit")
        print("====================")
        print("PASS: disabled no-op behavior and zero-limit configuration safety passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 RUNNER AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

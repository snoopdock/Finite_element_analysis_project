#!/usr/bin/env python3
"""Read-only audit for Stage 3.5D proposition-level evidence relevance."""

from __future__ import annotations

from analysis.evidence_relevance import assess_evidence_relevance


class StubProvider:
    def __init__(self, response: str = "{}", exhausted: bool = False):
        self.response = response
        self.exhausted = exhausted
        self.calls = 0

    def budget_exhausted(self) -> bool:
        return self.exhausted

    def chat(self, messages, *, temperature, max_tokens, model=None):
        self.calls += 1
        return self.response, ""


class StubParser:
    def __init__(self, parsed):
        self.parsed = parsed

    def parse(self, text: str, model_name: str = ""):
        return self.parsed


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def proposition():
    return {
        "proposition_id": "p-001",
        "statement": "Method A improves convergence under condition X.",
        "source_ids": ["source-001"],
        "context": {"conditions": ["X"]},
    }


def main() -> int:
    passages = [
        "Under condition X, Method A reduced the iteration count.",
        "The study used a bounded parameter range.",
    ]

    support_provider = StubProvider('{"relationship":"supports"}')
    support = assess_evidence_relevance(
        proposition(),
        passages,
        support_provider,
        StubParser({
            "relationship": "supports",
            "confidence": 0.88,
            "reason": "The first passage directly reports the claimed effect.",
            "passage_indices": [1, 99],
        }),
    )
    check(not support["skipped"], "Support assessment unexpectedly skipped.")
    check(support["relevance"]["relationship"] == "supports", "Support relationship failed.")
    check(support["relevance"]["passage_indices"] == [1], "Out-of-range passage index was not removed.")
    check(support["relevance"]["confidence"] == 0.88, "Confidence normalization failed.")
    check(support_provider.calls == 1, "Unexpected support call count.")

    qualify = assess_evidence_relevance(
        proposition(),
        passages,
        StubProvider(),
        StubParser({
            "relationship": "qualifies",
            "confidence": 0.71,
            "reason": "The reported result is restricted to the tested range.",
            "passage_indices": [2],
        }),
    )
    check(qualify["relevance"]["relationship"] == "qualifies", "Qualification relationship failed.")

    unrelated = assess_evidence_relevance(
        proposition(),
        ["The article describes a historical overview of finite elements."],
        StubProvider(),
        StubParser({
            "relationship": "does_not_address",
            "confidence": 0.94,
            "reason": "The passage does not discuss the proposition.",
            "passage_indices": [1],
        }),
    )
    check(unrelated["relevance"]["relationship"] == "does_not_address", "Non-addressing result failed.")

    malformed = assess_evidence_relevance(
        proposition(),
        passages,
        StubProvider(),
        StubParser({
            "relationship": "invented_relation",
            "confidence": "not-a-number",
            "reason": 123,
            "passage_indices": "bad",
        }),
    )
    check(malformed["relevance"]["relationship"] == "unknown", "Invalid relationship was not downgraded.")
    check(malformed["relevance"]["confidence"] == 0.0, "Invalid confidence was not downgraded.")
    check(malformed["relevance"]["passage_indices"] == [], "Malformed passage indices were not removed.")

    exhausted = StubProvider(exhausted=True)
    skipped = assess_evidence_relevance(
        proposition(),
        passages,
        exhausted,
        StubParser({"relationship": "supports"}),
    )
    check(skipped["skipped"], "Budget exhaustion did not skip relevance assessment.")
    check(exhausted.calls == 0, "Budget exhaustion still called the provider.")

    missing = assess_evidence_relevance(
        {"proposition_id": "p-002", "statement": ""},
        passages,
        StubProvider(),
        StubParser({}),
    )
    check(missing["skipped"], "Missing proposition statement did not skip assessment.")

    print("Stage 3.5D evidence relevance audit")
    print("====================================")
    print("PASS: support/qualification/non-addressing semantics, normalization, passage bounds, budget gating, and missing-input safety passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

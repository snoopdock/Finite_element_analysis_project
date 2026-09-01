#!/usr/bin/env python3
"""Audit the Stage 4.5C validity extractor with a stubbed provider/parser."""

from analysis.validity_extractor import extract_validity_scope


class StubProvider:
    def __init__(self, response, exhausted=False):
        self.response = response
        self.exhausted = exhausted
        self.calls = 0

    def budget_exhausted(self):
        return self.exhausted

    def generate(self, prompt, *, model=None, max_tokens=700):
        self.calls += 1
        return self.response


def parse_json(value):
    import json
    return json.loads(value)


def main() -> int:
    response = (
        '{"type":"conditional","framework":"Galerkin FEM",'
        '"domain_of_validity":"elliptic PDE",'
        '"conditions":["coercive operator"],"assumptions":[],'
        '"limitations":[],"exceptions":[],"approximation":null,'
        '"evidence_relation_ids":["ER1", "FABRICATED"]}'
    )
    provider = StubProvider(response)
    proposition = {
        "proposition_id": "P1",
        "statement": "Method A is stable.",
        "evidence_relation_ids": ["ER1"],
    }
    evidence = [{
        "source_id": "S1",
        "full_text": "The method is stable for coercive operators.",
        "evidence_relation_ids": ["ER2"],
    }]

    scope = extract_validity_scope(proposition, evidence, provider, parse_json)
    assert scope is not None
    assert scope["proposition_id"] == "P1"
    assert scope["status"] == "proposed"
    assert scope["type"] == "conditional"
    assert scope["evidence_relation_ids"] == ["ER1", "ER2"]
    assert "FABRICATED" not in scope["evidence_relation_ids"]
    assert provider.calls == 1

    provider2 = StubProvider(response)
    abstract_only = [{"source_id": "S2", "abstract": "Method A is stable."}]
    assert extract_validity_scope(proposition, abstract_only, provider2, parse_json) is None
    assert provider2.calls == 0

    provider3 = StubProvider(response, exhausted=True)
    assert extract_validity_scope(proposition, evidence, provider3, parse_json) is None
    assert provider3.calls == 0

    provider4 = StubProvider("not json")
    assert extract_validity_scope(proposition, evidence, provider4, parse_json) is None

    print("Stage 4.5C validity extractor audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

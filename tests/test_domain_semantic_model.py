from core.domain_semantic_model import (
    empty_domain_semantic_model,
    get_authorized_equation_ids,
    ingest_equation_candidates,
    promote_equation_candidate,
    resolve_equation,
    validate_domain_semantic_model,
)


def _candidate(model):
    return next(iter(model["equation_candidates"].values()))


def test_ingestion_creates_candidate_without_authority_escalation():
    model = ingest_equation_candidates(
        empty_domain_semantic_model(),
        [
            {
                "name": "Weak form",
                "latex": "a(u,v)=l(v)",
                "explanation": "Variational statement.",
                "source_ids": ["s1"],
            }
        ],
        {"s1"},
    )

    candidate = _candidate(model)
    assert candidate["status"] == "candidate"
    assert candidate["expression"] == "a(u,v)=l(v)"
    assert model["equations"] == {}
    assert get_authorized_equation_ids(model) == set()


def test_repeated_discovery_merges_evidence_but_preserves_candidate_payload():
    model = ingest_equation_candidates(
        empty_domain_semantic_model(),
        [{"name": "Weak form", "latex": "A", "explanation": "first", "source_ids": ["s1"]}],
        {"s1", "s2"},
    )
    candidate_id = next(iter(model["equation_candidates"]))

    model = ingest_equation_candidates(
        model,
        [{"name": "Weak form", "latex": "A", "explanation": "changed", "source_ids": ["s2"]}],
        {"s1", "s2"},
    )

    assert list(model["equation_candidates"]) == [candidate_id]
    candidate = model["equation_candidates"][candidate_id]
    assert candidate["meaning"] == "first"
    assert candidate["source_ids"] == ["s1", "s2"]


def test_same_name_different_expression_remains_distinct_candidates():
    model = ingest_equation_candidates(
        empty_domain_semantic_model(),
        [
            {"name": "Weak form", "latex": "A", "explanation": "one", "source_ids": ["s1"]},
            {"name": "Weak form", "latex": "B", "explanation": "two", "source_ids": ["s1"]},
        ],
        {"s1"},
    )

    assert len(model["equation_candidates"]) == 2
    assert {item["expression"] for item in model["equation_candidates"].values()} == {"A", "B"}


def test_explicit_promotion_assigns_persistent_equation_identity():
    model = ingest_equation_candidates(
        empty_domain_semantic_model(),
        [{"name": "Weak form", "latex": "A", "explanation": "one", "source_ids": ["s1"]}],
        {"s1"},
    )
    candidate_id = next(iter(model["equation_candidates"]))

    promoted = promote_equation_candidate(model, candidate_id, proposition_ids=["p1"])
    equation_id = promoted["equation_candidates"][candidate_id]["equation_id"]
    repeated = promote_equation_candidate(promoted, candidate_id)

    assert equation_id.startswith("EQ-")
    assert repeated["equation_candidates"][candidate_id]["equation_id"] == equation_id
    assert get_authorized_equation_ids(repeated) == {equation_id}
    equation = resolve_equation(repeated, equation_id)
    assert equation["expression"] == "A"
    assert equation["proposition_ids"] == ["p1"]
    validate_domain_semantic_model(repeated)

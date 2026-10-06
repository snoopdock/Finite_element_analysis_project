from core.domain_semantic_model import (
    empty_domain_semantic_model,
    ingest_equation_candidates,
    promote_equation_candidate,
)
from writing.semantic_authoring_shadow import (
    annotate_legacy_authoring,
    project_shadow_to_legacy,
)


def _authorized_model(expression="Ku=f"):
    model = ingest_equation_candidates(
        empty_domain_semantic_model(),
        [{"name": "Equilibrium", "latex": expression, "explanation": "Balance.", "source_ids": ["s1"]}],
        {"s1"},
    )
    candidate_id = next(iter(model["equation_candidates"]))
    model = promote_equation_candidate(model, candidate_id)
    equation_id = model["equation_candidates"][candidate_id]["equation_id"]
    return model, equation_id


def test_shadow_annotation_round_trips_exact_legacy_text():
    model, equation_id = _authorized_model()
    content = "Balance follows.\n\n$Ku=f$\n\nSupported by [s1]."

    result = annotate_legacy_authoring(content, domain_model=model, source_ids={"s1"})

    assert f"[[EQ:{equation_id}]]" in result.authoring_text
    assert "[[CITE:s1]]" in result.authoring_text
    assert project_shadow_to_legacy(result.authoring_text, domain_model=model) == content


def test_inline_equation_is_not_misrepresented_as_block_occurrence():
    model, equation_id = _authorized_model()
    content = "The inline relation $Ku=f$ is supported by [s1]."

    result = annotate_legacy_authoring(content, domain_model=model, source_ids={"s1"})

    assert f"[[EQ:{equation_id}]]" not in result.authoring_text
    assert "$Ku=f$" in result.authoring_text
    assert "[[CITE:s1]]" in result.authoring_text
    assert any(item.startswith("inline_equation_not_annotated") for item in result.diagnostics)


def test_grouped_citation_becomes_semantic_cluster_and_round_trips_exactly():
    model, _ = _authorized_model()
    content = "Supported by [s1, s2]."
    result = annotate_legacy_authoring(
        content,
        domain_model=model,
        source_ids={"s1", "s2"},
    )

    assert result.authoring_text == "Supported by [[CITES:s1,s2]]."
    assert result.annotated_source_ids == ("s1", "s2")
    assert project_shadow_to_legacy(result.authoring_text, domain_model=model) == content


def test_grouped_citation_fails_closed_when_any_source_is_unknown():
    model, _ = _authorized_model()
    result = annotate_legacy_authoring(
        "Supported by [s1, missing].",
        domain_model=model,
        source_ids={"s1"},
    )

    assert result.authoring_text == "Supported by [s1, missing]."
    assert any(item.startswith("grouped_citation_not_annotated") for item in result.diagnostics)


def test_parenthesized_single_citation_is_canonicalized_then_promoted_semantically():
    model, _ = _authorized_model()
    content = "Supported by (s1)."

    result = annotate_legacy_authoring(content, domain_model=model, source_ids={"s1"})

    assert result.authoring_text == "Supported by [[CITE:s1]]."
    assert result.annotated_source_ids == ("s1",)
    assert "parenthesized_citation_normalized:s1" in result.diagnostics
    # Parentheses are legacy-invalid citation syntax; canonical legacy projection
    # is deliberately bracketed while scientific prose is unchanged.
    assert project_shadow_to_legacy(result.authoring_text, domain_model=model) == "Supported by [s1]."


def test_parenthesized_grouped_citation_is_canonicalized_then_promoted_semantically():
    model, _ = _authorized_model()
    content = "Supported by (s1, s2)."

    result = annotate_legacy_authoring(content, domain_model=model, source_ids={"s1", "s2"})

    assert result.authoring_text == "Supported by [[CITES:s1,s2]]."
    assert result.annotated_source_ids == ("s1", "s2")
    assert "parenthesized_citation_normalized:s1,s2" in result.diagnostics


def test_parenthesized_mixed_known_unknown_citation_is_not_guessed():
    model, _ = _authorized_model()
    content = "Supported by (s1, missing)."

    result = annotate_legacy_authoring(content, domain_model=model, source_ids={"s1"})

    assert result.authoring_text == content
    assert result.annotated_source_ids == ()

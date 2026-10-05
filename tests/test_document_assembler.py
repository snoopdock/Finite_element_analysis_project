import pytest

from core.document_assembler import (
    DocumentAssemblyError,
    assemble_section,
    validate_authoring_text,
)
from core.document_model import (
    CitationOccurrence,
    CitationClusterOccurrence,
    DisplayMath,
    EquationOccurrence,
    EquationProposalReference,
    InlineMath,
    Paragraph,
    Text,
)
from core.semantic_markers import SemanticMarkerError


SECTION_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_assemble_preserves_inline_citations_and_display_equation_order():
    section = assemble_section(
        section_id=SECTION_ID,
        title="Weak Form",
        authoring_text=(
            "The formulation is supported [[CITE:source-1]]. "
            "The governing relation is [[EQ:eq-1]]. "
            "See [[REF:eq-occ-1]] for the corresponding placement."
        ),
        equation_ids={"eq-1"},
        source_ids={"source-1"},
        target_ids={"eq-occ-1"},
    )

    assert [type(child) for child in section.children] == [
        Paragraph,
        EquationOccurrence,
        Paragraph,
    ]
    assert section.children[0].inline_content == [
        Text("The formulation is supported "),
        CitationOccurrence(
            source_id="source-1",
            occurrence_id=section.children[0].inline_content[1].occurrence_id,
        ),
        Text(". The governing relation is "),
    ]
    assert section.children[1].equation_id == "eq-1"
    assert section.children[2].inline_content[1].target_id == "eq-occ-1"


def test_assembly_occurrence_ids_are_deterministic():
    kwargs = dict(
        section_id=SECTION_ID,
        title="Deterministic",
        authoring_text="A [[CITE:source-1]]. [[EQ:eq-1]]",
        equation_ids={"eq-1"},
        source_ids={"source-1"},
        target_ids=set(),
    )

    first = assemble_section(**kwargs).to_dict()
    second = assemble_section(**kwargs).to_dict()

    assert first == second


def test_explicit_legacy_math_migration_structures_inline_and_display_math():
    section = assemble_section(
        section_id=SECTION_ID,
        title="Legacy Math Migration",
        authoring_text=(
            "Let $u_h \\in V_h$ be the approximation.\n\n"
            "$a(u,v)=L(v)$\n\n"
            "Supported [[CITE:source-1]]."
        ),
        equation_ids=set(),
        source_ids={"source-1"},
        target_ids=set(),
        parse_legacy_math=True,
    )

    assert isinstance(section.children[0], Paragraph)
    assert any(
        isinstance(node, InlineMath)
        for node in section.children[0].inline_content
    )
    assert any(isinstance(child, DisplayMath) for child in section.children)
    assert not any(
        isinstance(node, Text) and "$" in node.text
        for child in section.children
        if isinstance(child, Paragraph)
        for node in child.inline_content
    )


def test_semantic_assembly_does_not_parse_legacy_math_unless_explicitly_enabled():
    section = assemble_section(
        section_id=SECTION_ID,
        title="Strict Semantic Assembly",
        authoring_text="Let $u_h$ be the approximation [[CITE:source-1]].",
        equation_ids=set(),
        source_ids={"source-1"},
        target_ids=set(),
    )

    assert isinstance(section.children[0], Paragraph)
    assert section.children[0].inline_content[0] == Text(
        "Let $u_h$ be the approximation "
    )


def test_repeated_references_get_distinct_occurrences():
    section = assemble_section(
        section_id=SECTION_ID,
        title="Repeated",
        authoring_text="[[CITE:source-1]] then [[CITE:source-1]]",
        equation_ids=set(),
        source_ids={"source-1"},
        target_ids=set(),
    )

    citations = [
        node
        for node in section.children[0].inline_content
        if isinstance(node, CitationOccurrence)
    ]

    assert len(citations) == 2
    assert citations[0].occurrence_id != citations[1].occurrence_id


def test_unknown_reference_is_rejected_without_substitution():
    with pytest.raises(DocumentAssemblyError, match="Unknown equation_id"):
        assemble_section(
            section_id=SECTION_ID,
            title="Unknown",
            authoring_text="[[EQ:eq-missing]]",
            equation_ids={"eq-known"},
            source_ids=set(),
            target_ids=set(),
        )


def test_new_equation_proposal_remains_non_renderable_reference():
    section = assemble_section(
        section_id=SECTION_ID,
        title="Draft",
        authoring_text="Derived relation: [[NEW_EQ:proposal-1]]",
        equation_ids=set(),
        source_ids=set(),
        target_ids=set(),
        proposal_ids={"proposal-1"},
    )

    assert isinstance(section.children[1], EquationProposalReference)
    assert section.children[1].proposal_id == "proposal-1"


def test_new_equation_proposal_requires_registered_proposal():
    with pytest.raises(DocumentAssemblyError, match="Unknown equation proposal_id"):
        assemble_section(
            section_id=SECTION_ID,
            title="Draft",
            authoring_text="Derived relation: [[NEW_EQ:proposal-1]]",
            equation_ids=set(),
            source_ids=set(),
            target_ids=set(),
            proposal_ids=set(),
        )


def test_validate_authoring_text_accepts_registered_citation_without_assembly():
    authoring_text = "Supported [[CITE:source-1]]."

    assert validate_authoring_text(
        authoring_text,
        equation_ids=set(),
        source_ids={"source-1"},
        target_ids=set(),
    ) is None
    assert authoring_text == "Supported [[CITE:source-1]]."


def test_validate_authoring_text_rejects_unknown_citation_without_substitution():
    authoring_text = "Supported [[CITE:not-authorized]]."

    with pytest.raises(DocumentAssemblyError, match="Unknown citation source_id"):
        validate_authoring_text(
            authoring_text,
            equation_ids=set(),
            source_ids={"source-1"},
            target_ids=set(),
        )

    assert authoring_text == "Supported [[CITE:not-authorized]]."


@pytest.mark.parametrize(
    ("authoring_text", "registry_kwargs", "error_match"),
    [
        (
            "See [[REF:target-missing]].",
            {"target_ids": {"target-known"}},
            "Unknown cross-reference target_id",
        ),
        (
            "Use [[EQ:eq-missing]].",
            {"equation_ids": {"eq-known"}},
            "Unknown equation_id",
        ),
        (
            "Consider [[NEW_EQ:proposal-missing]].",
            {"proposal_ids": {"proposal-known"}},
            "Unknown equation proposal_id",
        ),
    ],
)
def test_validate_authoring_text_rejects_unknown_registered_marker_types(
    authoring_text, registry_kwargs, error_match
):
    kwargs = {
        "equation_ids": set(),
        "source_ids": set(),
        "target_ids": set(),
        "proposal_ids": set(),
    }
    kwargs.update(registry_kwargs)

    with pytest.raises(DocumentAssemblyError, match=error_match):
        validate_authoring_text(authoring_text, **kwargs)


def test_validate_authoring_text_accepts_all_registered_marker_types():
    validate_authoring_text(
        "[[CITE:source-1]] [[REF:target-1]] [[EQ:eq-1]] [[NEW_EQ:proposal-1]]",
        equation_ids={"eq-1"},
        source_ids={"source-1"},
        target_ids={"target-1"},
        proposal_ids={"proposal-1"},
    )


def test_validate_authoring_text_propagates_syntax_errors():
    with pytest.raises(SemanticMarkerError):
        validate_authoring_text(
            "Broken [[CITE:source-1",
            equation_ids=set(),
            source_ids={"source-1"},
            target_ids=set(),
        )


def test_assemble_grouped_citation_as_semantic_cluster_with_stable_occurrence_identity():
    section_a = assemble_section(
        section_id=SECTION_ID,
        title="Evidence",
        authoring_text="Supported [[CITES:source-1,source-2]].",
        equation_ids=set(),
        source_ids={"source-1", "source-2"},
        target_ids=set(),
    )
    section_b = assemble_section(
        section_id=SECTION_ID,
        title="Evidence",
        authoring_text="Supported [[CITES:source-1,source-2]].",
        equation_ids=set(),
        source_ids={"source-1", "source-2"},
        target_ids=set(),
    )

    cluster_a = section_a.children[0].inline_content[1]
    cluster_b = section_b.children[0].inline_content[1]
    assert isinstance(cluster_a, CitationClusterOccurrence)
    assert cluster_a.source_ids == ("source-1", "source-2")
    assert cluster_a.occurrence_id == cluster_b.occurrence_id
    from uuid import UUID
    assert str(UUID(cluster_a.occurrence_id)) == cluster_a.occurrence_id


def test_validate_authoring_text_rejects_unknown_source_inside_grouped_citation():
    with pytest.raises(DocumentAssemblyError, match="Unknown citation source_id: missing"):
        validate_authoring_text(
            "Supported [[CITES:source-1,missing]].",
            equation_ids=set(),
            source_ids={"source-1"},
            target_ids=set(),
        )


def test_validate_authoring_text_rejects_duplicate_ids_inside_grouped_citation():
    with pytest.raises(DocumentAssemblyError, match="must not contain duplicate"):
        validate_authoring_text(
            "Supported [[CITES:source-1,source-1]].",
            equation_ids=set(),
            source_ids={"source-1"},
            target_ids=set(),
        )

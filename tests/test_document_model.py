import pytest

from core.document_model import (
    CitationOccurrence,
    Document,
    DocumentModelError,
    EquationOccurrence,
    EquationProposal,
    EquationProposalReference,
    Paragraph,
    Section,
    Text,
    assert_renderable,
    document_from_legacy_sections,
    validate_document_references,
)


def test_legacy_sections_preserve_identity_and_lineage_without_inference():
    section_id = "550e8400-e29b-41d4-a716-446655440000"
    parent_id = "550e8400-e29b-41d4-a716-446655440001"
    legacy = [
        {
            "section_id": section_id,
            "parent_section_ids": [parent_id],
            "title": "Assembly",
            "content": "The global system is assembled from elemental contributions.",
            "key_equations": ["should not be inferred"],
            "citations_used": ["source-1"],
        }
    ]

    document = document_from_legacy_sections(legacy)
    section = document.children[0]

    assert section.section_id == section_id
    assert section.parent_section_ids == [parent_id]
    assert section.title == "Assembly"
    assert isinstance(section.children[0], Paragraph)
    assert section.children[0].inline_content == [
        Text("The global system is assembled from elemental contributions.")
    ]
    assert document.to_dict()["children"][0]["section_id"] == section_id


def test_document_preserves_order_and_repeated_equation_occurrences():
    equation_1 = EquationOccurrence("eq-1", occurrence_id="occ-1")
    equation_2 = EquationOccurrence("eq-1", occurrence_id="occ-2")
    section = Section(
        title="Weak Form",
        children=[
            Paragraph.from_text("Before"),
            equation_1,
            Paragraph.from_text("Between"),
            equation_2,
            Paragraph.from_text("After"),
        ],
    )
    document = Document(children=[section])

    document.validate()
    serialized = document.to_dict()
    child_types = [child["type"] for child in serialized["children"][0]["children"]]

    assert child_types == [
        "paragraph",
        "equation_occurrence",
        "paragraph",
        "equation_occurrence",
        "paragraph",
    ]
    assert serialized["children"][0]["children"][1]["occurrence_id"] == "occ-1"
    assert serialized["children"][0]["children"][3]["occurrence_id"] == "occ-2"


def test_unresolved_references_are_reported_without_substitution():
    section = Section(
        title="References",
        children=[
            Paragraph(
                inline_content=[
                    Text("Supported by "),
                    CitationOccurrence("missing-source", occurrence_id="cit-1"),
                ]
            ),
            EquationOccurrence("missing-equation", occurrence_id="eq-occ-1"),
        ],
    )
    document = Document(children=[section])

    errors = validate_document_references(
        document,
        equation_ids={"eq-known"},
        source_ids={"source-known"},
        target_ids=set(),
    )

    assert any("missing-equation" in error for error in errors)
    assert any("missing-source" in error for error in errors)


def test_unresolved_equation_proposal_blocks_rendering():
    section = Section(
        title="Draft",
        children=[
            EquationProposalReference("proposal-1", occurrence_id="proposal-occ-1")
        ],
    )
    document = Document(children=[section])

    proposal = EquationProposal(
        proposal_id="proposal-1",
        expression="K_{eff}=K_1+K_2",
    )
    proposal.validate()

    with pytest.raises(DocumentModelError, match="unresolved equation proposal"):
        assert_renderable(
            document,
            equation_ids=set(),
            source_ids=set(),
            target_ids=set(),
            proposal_ids={proposal.proposal_id},
        )


def test_renderable_document_requires_resolved_references():
    section = Section(
        title="Renderable",
        children=[
            Paragraph(
                inline_content=[
                    Text("See "),
                    CitationOccurrence("source-1", occurrence_id="cit-1"),
                ]
            ),
            EquationOccurrence("eq-1", occurrence_id="eq-occ-1"),
        ],
    )
    document = Document(children=[section])

    assert_renderable(
        document,
        equation_ids={"eq-1"},
        source_ids={"source-1"},
        target_ids=set(),
    )

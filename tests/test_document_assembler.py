import pytest

from core.document_assembler import DocumentAssemblyError, assemble_section
from core.document_model import (
    CitationOccurrence,
    EquationOccurrence,
    EquationProposalReference,
    Paragraph,
    Text,
)


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
        Text(". "),
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

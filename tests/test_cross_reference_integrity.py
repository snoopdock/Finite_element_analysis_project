import json

import pytest

from core.document_model import (
    CrossReferenceOccurrence,
    Document,
    EquationOccurrence,
    Figure,
    Paragraph,
    Section,
    Text,
)
from core.domain_semantic_model import (
    empty_domain_semantic_model,
    ingest_equation_candidates,
    promote_equation_candidate,
)
from core.pipeline import phase_assemble
from processing.document_to_latex_ir import (
    DocumentToLatexIRError,
    project_document_to_latex_ir,
)
from processing.label_registry import LabelRegistryError, build_label_registry
from processing.latex_ir import (
    DocumentModel,
    IRCrossReferenceSpan,
    ParagraphBlock,
    SectionModel,
    validate_document_model,
)
from processing.latex_renderer import render_body


SECTION_A = "11111111-1111-4111-8111-111111111111"
SECTION_B = "22222222-2222-4222-8222-222222222222"


def _state():
    return {"topic": "FEM", "objective": "Guide"}


def _domain_with_equation():
    domain = ingest_equation_candidates(
        empty_domain_semantic_model(),
        [
            {
                "name": "Balance",
                "latex": r"K u = f",
                "explanation": "Balance equation",
                "source_ids": ["s1"],
            }
        ],
        {"s1"},
    )
    candidate_id = next(iter(domain["equation_candidates"]))
    domain = promote_equation_candidate(domain, candidate_id)
    equation_id = domain["equation_candidates"][candidate_id]["equation_id"]
    return domain, equation_id


def test_registry_is_deterministic_and_independent_of_title_and_order():
    first = Document(
        children=[
            Section(section_id=SECTION_A, title="Alpha", children=[]),
            Section(section_id=SECTION_B, title="Beta", children=[]),
        ]
    )
    second = Document(
        children=[
            Section(section_id=SECTION_B, title="Changed title", children=[]),
            Section(section_id=SECTION_A, title="Another title", children=[]),
        ]
    )

    labels_first = {
        record.target_id: record.latex_label
        for record in build_label_registry(first).records
    }
    labels_second = {
        record.target_id: record.latex_label
        for record in build_label_registry(second).records
    }

    assert labels_first == labels_second
    assert labels_first[SECTION_A] == f"sec:{SECTION_A}"
    assert labels_first[SECTION_B] == f"sec:{SECTION_B}"


def test_registry_hashes_unsafe_identity_instead_of_passing_it_to_latex():
    unsafe_id = r"equation occurrence with spaces}{\\input{evil}"
    document = Document(
        children=[
            Section(
                section_id=SECTION_A,
                title="Unsafe ID",
                children=[
                    EquationOccurrence(
                        equation_id="domain-equation-id",
                        occurrence_id=unsafe_id,
                    )
                ],
            )
        ]
    )

    record = build_label_registry(document).resolve(unsafe_id)

    assert record.latex_label.startswith("eq:sha256-")
    assert "input" not in record.latex_label
    assert " " not in record.latex_label
    assert "{" not in record.latex_label


def test_registry_rejects_ambiguous_duplicate_target_identity_across_object_types():
    domain, equation_id = _domain_with_equation()
    del domain  # identity collision is a document problem, not a domain payload problem
    document = Document(
        children=[
            Section(
                section_id=SECTION_A,
                title="Collision",
                children=[
                    EquationOccurrence(
                        equation_id=equation_id,
                        occurrence_id=SECTION_A,
                    )
                ],
            )
        ]
    )

    with pytest.raises(LabelRegistryError, match="duplicate document target_id"):
        build_label_registry(document)


def test_forward_section_reference_preserves_identity_and_renders_label_ref_pair():
    document = Document(
        children=[
            Section(
                section_id=SECTION_A,
                title="First",
                children=[
                    Paragraph(
                        inline_content=[
                            Text("See Section "),
                            CrossReferenceOccurrence(
                                target_id=SECTION_B,
                                occurrence_id="xref-forward",
                            ),
                            Text("."),
                        ]
                    )
                ],
            ),
            Section(section_id=SECTION_B, title="Second", children=[]),
        ]
    )

    ir = project_document_to_latex_ir(
        document,
        state=_state(),
        evidence=[],
        domain_model=empty_domain_semantic_model(),
    )

    span = ir.sections[0].blocks[0].content[1]
    assert isinstance(span, IRCrossReferenceSpan)
    assert span.target_id == SECTION_B
    assert span.target_type == "section"
    assert span.occurrence_id == "xref-forward"
    assert span.label == f"sec:{SECTION_B}"

    rendered = render_body(ir)
    assert rf"\ref{{sec:{SECTION_B}}}" in rendered
    assert rf"\label{{sec:{SECTION_B}}}" in rendered


def test_equation_reference_targets_document_occurrence_not_domain_equation_identity():
    domain, equation_id = _domain_with_equation()
    equation_occurrence_id = "eq-occurrence-001"
    document = Document(
        children=[
            Section(
                section_id=SECTION_A,
                title="Equation",
                children=[
                    EquationOccurrence(
                        equation_id=equation_id,
                        occurrence_id=equation_occurrence_id,
                    ),
                    Paragraph(
                        inline_content=[
                            Text("See equation "),
                            CrossReferenceOccurrence(
                                target_id=equation_occurrence_id,
                                occurrence_id="xref-eq-1",
                            ),
                        ]
                    ),
                ],
            )
        ]
    )

    ir = project_document_to_latex_ir(
        document,
        state=_state(),
        evidence=[],
        domain_model=domain,
    )
    equation_block = ir.sections[0].blocks[0]
    xref = ir.sections[0].blocks[1].content[1]

    assert equation_block.equation_id == equation_id
    assert equation_block.occurrence_id == equation_occurrence_id
    assert equation_block.label == f"eq:{equation_occurrence_id}"
    assert xref.target_id == equation_occurrence_id
    assert xref.target_type == "equation_occurrence"
    assert xref.label == equation_block.label

    rendered = render_body(ir)
    assert rf"\label{{eq:{equation_occurrence_id}}}" in rendered
    assert rf"\ref{{eq:{equation_occurrence_id}}}" in rendered


def test_unresolved_cross_reference_rejects_without_text_matching_or_guessing():
    document = Document(
        children=[
            Section(
                section_id=SECTION_A,
                title="Missing",
                children=[
                    Paragraph(
                        inline_content=[
                            CrossReferenceOccurrence(
                                target_id="not-a-real-object",
                                occurrence_id="xref-missing",
                            )
                        ]
                    )
                ],
            )
        ]
    )

    with pytest.raises(Exception, match="unknown cross-reference|unresolved.*target_id"):
        project_document_to_latex_ir(
            document,
            state=_state(),
            evidence=[],
            domain_model=empty_domain_semantic_model(),
        )


def test_canonical_projection_rejects_manual_equation_latex_label():
    domain, equation_id = _domain_with_equation()
    document = Document(
        children=[
            Section(
                section_id=SECTION_A,
                title="Manual label",
                children=[
                    EquationOccurrence(
                        equation_id=equation_id,
                        occurrence_id="eq-occ-2",
                        label="eq:manual",
                    )
                ],
            )
        ]
    )

    with pytest.raises(DocumentToLatexIRError, match="labels are generated"):
        project_document_to_latex_ir(
            document,
            state=_state(),
            evidence=[],
            domain_model=domain,
        )


def test_ir_validation_rejects_reference_label_target_mismatch():
    ir = DocumentModel(
        topic="FEM",
        objective="Guide",
        sections=(
            SectionModel(
                title="A",
                section_id=SECTION_A,
                label=f"sec:{SECTION_A}",
                blocks=(
                    ParagraphBlock(
                        (
                            IRCrossReferenceSpan(
                                target_id=SECTION_B,
                                target_type="section",
                                label=f"sec:{SECTION_A}",
                                occurrence_id="xref-bad",
                            ),
                        )
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(Exception, match="label/target mismatch"):
        validate_document_model(ir)


def test_figure_reference_path_resolves_after_figure_projection_is_available():
    document = Document(
        children=[
            Section(
                section_id=SECTION_A,
                title="Figure",
                children=[
                    Figure(
                        asset="figure.png",
                        figure_id="figure-1",
                        caption="Finite element mesh",
                    ),
                    Paragraph(
                        inline_content=[
                            CrossReferenceOccurrence(
                                target_id="figure-1",
                                occurrence_id="xref-figure",
                            )
                        ]
                    ),
                ],
            )
        ]
    )

    projected = project_document_to_latex_ir(
        document,
        state=_state(),
        evidence=[],
        domain_model=empty_domain_semantic_model(),
    )
    figure_block, paragraph = projected.sections[0].blocks
    assert figure_block.label == "fig:figure-1"
    assert paragraph.content[0].target_type == "figure"
    assert paragraph.content[0].label == "fig:figure-1"


def test_active_pipeline_resolves_explicit_section_ref_marker(tmp_path):
    state = {
        "topic": "FEM",
        "objective": "Guide",
        "knowledge_graph": {},
        "domain_semantic_model": empty_domain_semantic_model(),
        "sections": [
            {
                "section_id": SECTION_A,
                "title": "Target",
                "content": "Target content.",
                "parent_section_ids": [],
            },
            {
                "section_id": SECTION_B,
                "title": "Referrer",
                "content": f"See Section [[REF:{SECTION_A}]].",
                "parent_section_ids": [],
            },
        ],
    }
    evidence_path = tmp_path / "evidence.json"
    latex_path = tmp_path / "guideline.tex"
    evidence_path.write_text(json.dumps([]), encoding="utf-8")

    assert phase_assemble(
        state,
        {"evidence": evidence_path, "latex": latex_path},
    ) is True

    tex = latex_path.read_text(encoding="utf-8")
    assert rf"\label{{sec:{SECTION_A}}}" in tex
    assert rf"\ref{{sec:{SECTION_A}}}" in tex
    assert "[[REF:" not in tex

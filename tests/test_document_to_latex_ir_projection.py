import json

import pytest

from core.document_model import (
    CitationOccurrence,
    CrossReferenceOccurrence,
    Document,
    EquationOccurrence,
    InlineMath,
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
from core.semantic_document_pipeline import build_semantic_render_document
from processing.document_to_latex_ir import (
    DocumentToLatexIRError,
    project_document_to_latex_ir,
)
from processing.latex_ir import EquationBlock, IRCitationSpan, IRMathSpan, IRTextSpan, ParagraphBlock
from processing.latex_renderer import render_body


SECTION_ID = "550e8400-e29b-41d4-a716-446655440000"


def _evidence():
    return [
        {
            "source_id": "s1",
            "title": "Source One",
            "url": "https://example.com/s1",
            "retriever_module": "test",
            "retrieved_at": "2026-10-03T00:00:00Z",
        }
    ]


def test_document_projection_preserves_inline_text_math_citation_order():
    document = Document(
        document_id="11111111-1111-4111-8111-111111111111",
        children=[
            Section(
                section_id=SECTION_ID,
                title="Weak form",
                children=[
                    Paragraph(
                        inline_content=[
                            Text("Find "),
                            InlineMath(r"u_h \\in V_h"),
                            Text(" as shown in "),
                            CitationOccurrence("s1", occurrence_id="cite-occ-1"),
                            Text("."),
                        ]
                    )
                ],
            )
        ],
    )

    ir = project_document_to_latex_ir(
        document,
        state={"topic": "FEM", "objective": "Guide"},
        evidence=_evidence(),
        domain_model=empty_domain_semantic_model(),
    )

    paragraph = ir.sections[0].blocks[0]
    assert isinstance(paragraph, ParagraphBlock)
    assert isinstance(paragraph.content[0], IRTextSpan)
    assert isinstance(paragraph.content[1], IRMathSpan)
    assert isinstance(paragraph.content[3], IRCitationSpan)
    assert paragraph.content[3].occurrence_id == "cite-occ-1"
    assert ir.source_document_id == document.document_id

    rendered = render_body(ir)
    assert r"Find \(u_h \\in V_h\) as shown in \cite{ref1}." in rendered
    assert r"\$u_h" not in rendered
    assert rendered.index(r"\(u_h") < rendered.index(r"\cite{ref1}")


def test_authoritative_equation_occurrence_resolves_expression_by_equation_id():
    domain = ingest_equation_candidates(
        empty_domain_semantic_model(),
        [
            {
                "name": "Equilibrium",
                "latex": r"K u = f",
                "explanation": "Balance",
                "source_ids": ["s1"],
            }
        ],
        {"s1"},
    )
    candidate_id = next(iter(domain["equation_candidates"]))
    domain = promote_equation_candidate(domain, candidate_id)
    equation_id = domain["equation_candidates"][candidate_id]["equation_id"]

    document = Document(
        children=[
            Section(
                section_id=SECTION_ID,
                title="Equation",
                children=[
                    EquationOccurrence(
                        equation_id=equation_id,
                        occurrence_id="eq-occ-1",
                    )
                ],
            )
        ]
    )

    ir = project_document_to_latex_ir(
        document,
        state={"topic": "FEM", "objective": "Guide"},
        evidence=_evidence(),
        domain_model=domain,
    )

    block = ir.sections[0].blocks[0]
    assert isinstance(block, EquationBlock)
    assert block.equation_id == equation_id
    assert block.occurrence_id == "eq-occ-1"
    assert block.expression == r"K u = f"
    assert r"K u = f" in render_body(ir)


def test_cross_reference_projection_fails_closed_until_label_registry_exists():
    document = Document(
        children=[
            Section(
                section_id=SECTION_ID,
                title="Reference",
                children=[
                    Paragraph(
                        inline_content=[
                            Text("See "),
                            CrossReferenceOccurrence(
                                target_id=SECTION_ID,
                                occurrence_id="ref-occ-1",
                            ),
                        ]
                    )
                ],
            )
        ]
    )

    with pytest.raises(Exception, match="cross-reference|CrossReference|target_id"):
        project_document_to_latex_ir(
            document,
            state={"topic": "FEM", "objective": "Guide"},
            evidence=[],
            domain_model=empty_domain_semantic_model(),
        )


def test_semantic_render_document_promotes_ready_candidate_only_for_rendering():
    state = {
        "topic": "FEM",
        "objective": "Guide",
        "domain_semantic_model": empty_domain_semantic_model(),
        "sections": [
            {
                "section_id": SECTION_ID,
                "title": "Inline",
                "content": r"Let $u_h \\in V_h$ be discrete [s1].",
                "parent_section_ids": [],
            }
        ],
    }

    document, report = build_semantic_render_document(state, evidence=_evidence())

    assert report["status"] == "renderable"
    assert report["authoritative_for_rendering"] is True
    assert document.metadata["publication_role"] == "active_rendering_source"
    assert document.metadata["authoritative_for_rendering"] is True
    assert report["latex_ir_readiness"]["ready"] is True


def test_active_phase_assemble_uses_semantic_ir_and_does_not_escape_or_duplicate_math(tmp_path):
    state = {
        "topic": "FEM",
        "objective": "Guide",
        "knowledge_graph": {},
        "domain_semantic_model": empty_domain_semantic_model(),
        "sections": [
            {
                "section_id": SECTION_ID,
                "title": "Inline Mathematics",
                "content": r"Let $u_h \\in V_h$ satisfy the weak form [s1].",
                # These are legacy derived indexes. Active semantic IR must not
                # append them as duplicate display math/citations.
                "key_equations": [r"u_h \\in V_h"],
                "citations_used": ["s1"],
                "parent_section_ids": [],
            }
        ],
    }
    evidence_path = tmp_path / "evidence.json"
    latex_path = tmp_path / "guideline.tex"
    evidence_path.write_text(json.dumps(_evidence()), encoding="utf-8")

    assert phase_assemble(
        state,
        {"evidence": evidence_path, "latex": latex_path},
    ) is True

    tex = latex_path.read_text(encoding="utf-8")
    assert r"\(u_h \\in V_h\)" in tex
    assert r"\$u_h" not in tex
    assert r"\textbackslash{}in" not in tex
    assert tex.count(r"u_h \\in V_h") == 1
    assert tex.count(r"\cite{ref1}") == 1
    assert state["latex_ir_projection_status"]["status"] == "success"
    assert state["latex_ir_projection_status"]["section_count"] == 1

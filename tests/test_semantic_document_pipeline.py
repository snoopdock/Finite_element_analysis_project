import json

from core.document_model import (
    CitationOccurrence,
    CitationClusterOccurrence,
    EquationOccurrence,
    InlineMath,
    Paragraph,
    Text,
)
from core.domain_semantic_model import (
    empty_domain_semantic_model,
    ingest_equation_candidates,
    promote_equation_candidate,
)
from core.semantic_document_pipeline import (
    analyze_latex_ir_readiness,
    build_semantic_candidate_document,
    persist_semantic_candidate_document,
)


SECTION_ID = "550e8400-e29b-41d4-a716-446655440000"


def _state_with_authorized_equation():
    model = ingest_equation_candidates(
        empty_domain_semantic_model(),
        [{"name": "Equilibrium", "latex": "Ku=f", "explanation": "Balance.", "source_ids": ["s1"]}],
        {"s1"},
    )
    candidate_id = next(iter(model["equation_candidates"]))
    model = promote_equation_candidate(model, candidate_id)
    equation_id = model["equation_candidates"][candidate_id]["equation_id"]
    state = {
        "topic": "FEM",
        "objective": "Guide",
        "domain_semantic_model": model,
        "sections": [
            {
                "section_id": SECTION_ID,
                "title": "Balance",
                "content": "Intro [s1].\n\n$Ku=f$\n\nConclusion.",
                "parent_section_ids": [],
            }
        ],
    }
    return state, equation_id


def test_candidate_document_preserves_ordered_semantic_occurrences_without_mutating_legacy_sections():
    state, equation_id = _state_with_authorized_equation()
    original_sections = json.loads(json.dumps(state["sections"]))

    document, report = build_semantic_candidate_document(
        state,
        evidence=[{"source_id": "s1"}],
    )

    section = document.children[0]
    assert state["sections"] == original_sections
    assert isinstance(section.children[0], Paragraph)
    assert isinstance(section.children[0].inline_content[1], CitationOccurrence)
    assert isinstance(section.children[1], EquationOccurrence)
    assert section.children[1].equation_id == equation_id
    assert report["semantic_marker_count"] == 2
    assert document.metadata["authoritative_for_rendering"] is False


def test_candidate_document_persistence_is_shadow_only(tmp_path):
    state, _ = _state_with_authorized_equation()
    destination = tmp_path / "document.semantic-candidate.json"

    report = persist_semantic_candidate_document(
        state,
        {"semantic_candidate_document": destination},
        evidence=[{"source_id": "s1"}],
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert report["status"] == "candidate"
    assert payload["metadata"]["authoritative_for_rendering"] is False
    assert state["sections"][0]["content"] == "Intro [s1].\n\n$Ku=f$\n\nConclusion."


def test_shadow_generation_does_not_change_active_legacy_assembly(tmp_path):
    from core.pipeline import phase_assemble

    state, _ = _state_with_authorized_equation()
    evidence_path = tmp_path / "evidence.json"
    latex_path = tmp_path / "guideline.tex"
    evidence_path.write_text(
        json.dumps(
            [
                {
                    "source_id": "s1",
                    "title": "Source",
                    "url": "",
                    "retriever_module": "test",
                    "retrieved_at": "N/A",
                }
            ]
        ),
        encoding="utf-8",
    )
    legacy_paths = {"evidence": evidence_path, "latex": latex_path}

    assert phase_assemble(state, legacy_paths) is True
    before = latex_path.read_text(encoding="utf-8")

    persist_semantic_candidate_document(
        state,
        {"semantic_candidate_document": tmp_path / "document.semantic-candidate.json"},
        evidence=json.loads(evidence_path.read_text(encoding="utf-8")),
    )

    assert phase_assemble(state, legacy_paths) is True
    after = latex_path.read_text(encoding="utf-8")
    assert after == before


def test_candidate_document_is_structurally_ready_for_latex_ir_without_raw_math_in_text():
    state = {
        "topic": "FEM",
        "objective": "Guide",
        "domain_semantic_model": empty_domain_semantic_model(),
        "sections": [
            {
                "section_id": SECTION_ID,
                "title": "Inline Math",
                "content": "Let $u_h \\in V_h$ satisfy $a(u_h,v)=L(v)$ [s1].",
                "parent_section_ids": [],
            }
        ],
    }

    document, report = build_semantic_candidate_document(
        state,
        evidence=[{"source_id": "s1"}],
    )
    paragraph = document.children[0].children[0]

    assert isinstance(paragraph, Paragraph)
    assert sum(isinstance(node, InlineMath) for node in paragraph.inline_content) == 2
    assert not any(
        isinstance(node, Text) and "$" in node.text
        for node in paragraph.inline_content
    )
    readiness = analyze_latex_ir_readiness(document)
    assert readiness["ready"] is True
    assert readiness["counts"]["inline_math"] == 2
    assert readiness["counts"]["raw_math_text_nodes"] == 0
    assert report["latex_ir_readiness"] == readiness
    assert document.metadata["latex_ir_readiness"] == readiness


def test_semantic_candidate_promotes_legacy_grouped_citation_to_cluster_occurrence():
    state = {
        "topic": "FEM",
        "objective": "Guide",
        "domain_semantic_model": empty_domain_semantic_model(),
        "sections": [{
            "section_id": SECTION_ID,
            "title": "Evidence",
            "content": "Supported [s1, s2].",
            "parent_section_ids": [],
        }],
    }
    document, report = build_semantic_candidate_document(
        state, evidence=[{"source_id": "s1"}, {"source_id": "s2"}]
    )

    cluster = document.children[0].children[0].inline_content[1]
    assert isinstance(cluster, CitationClusterOccurrence)
    assert cluster.source_ids == ("s1", "s2")
    readiness = report["latex_ir_readiness"]
    assert readiness["counts"]["citation_cluster_occurrences"] == 1
    assert report["sections"][0]["citation_cluster_count"] == 1

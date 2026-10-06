"""Publication-integrity gate tests for generated LaTeX artifacts."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from processing.latex_builder import build_latex_document
from processing.latex_ir import build_document_model
from processing.publication_integrity import (
    PublicationIntegrityError,
    assert_publication_integrity,
    audit_document_model,
    audit_latex_source,
    compile_latex_pdf,
)


def _minimal_document(body: str) -> str:
    return "\n".join(
        [
            r"\documentclass{article}",
            r"\begin{document}",
            body,
            r"\end{document}",
        ]
    )


def _canonical_model_and_tex():
    state = {"topic": "FEM", "objective": "Study ∞-norm behavior", "knowledge_graph": {}}
    sections = [
        {
            "title": "Evidence",
            "blocks": [
                {"type": "text", "text": "Bounded ∞ response."},
                {"type": "math", "expression": r"u \in V"},
                {"type": "citation", "source_ids": ["paper_1"]},
            ],
        }
    ]
    evidence = [{"source_id": "paper_1", "title": "Paper", "retriever_module": "research.article"}]
    return build_document_model(state, sections, evidence), build_latex_document(state, sections, evidence)


def test_canonical_builder_passes_document_and_latex_integrity_gate():
    model, tex = _canonical_model_and_tex()

    assert_publication_integrity(model, tex)

    assert audit_document_model(model) == ()
    assert audit_latex_source(tex) == ()
    assert r"\@safemath" not in tex
    assert r"\newunicodechar" not in tex
    assert r"\usepackage[strings]{underscore}" not in tex
    assert r"\sloppy" not in tex
    assert "∞" not in tex


@pytest.mark.parametrize(
    ("fragment", "code"),
    [
        (r"\sloppy", "GLOBAL_SLOPPY"),
        (r"\newcommand{\@safemath}[1]{}", "GLOBAL_MATH_REDEFINITION"),
        (r"\usepackage[strings]{underscore}", "GLOBAL_UNDERSCORE_PACKAGE"),
        (r"\newunicodechar{∞}{x}", "GLOBAL_UNICODE_MAPPING"),
    ],
)
def test_static_gate_rejects_retired_global_compatibility_mechanisms(fragment, code):
    issues = audit_latex_source(_minimal_document(fragment))
    assert code in {issue.code for issue in issues}


def test_static_gate_rejects_raw_semantic_and_source_markers():
    tex = _minimal_document("Claim [[CITE:paper_1]] and [wiki_finite_element_method].")
    codes = {issue.code for issue in audit_latex_source(tex)}
    assert "RAW_SEMANTIC_MARKER" in codes
    assert "RAW_CITATION_MARKER_IN_TEX" in codes


def test_document_gate_rejects_raw_math_and_citation_markers_in_plain_text():
    model = build_document_model(
        {"topic": "FEM", "objective": "Guide"},
        [{"title": "Bad", "blocks": [{"type": "text", "text": r"Bad \nabla u [wiki_source]."}]}],
        [{"source_id": "wiki_source", "title": "Known"}],
    )
    codes = {issue.code for issue in audit_document_model(model)}
    assert "RAW_MATH_IN_TEXT" in codes
    assert "RAW_CITATION_MARKER" in codes


def test_static_gate_rejects_raw_or_literalized_math_commands_in_tex_prose():
    tex = _minimal_document(r"Bad \nabla u and \textbackslash{}int text.")
    codes = {issue.code for issue in audit_latex_source(tex)}
    assert "RAW_MATH_COMMAND_IN_TEX" in codes
    assert "ESCAPED_RAW_MATH" in codes


def test_static_gate_accepts_math_commands_inside_explicit_math_contexts():
    tex = _minimal_document(
        r"Inline \(\nabla u\), display \[\int_0^1 f(x)\,dx\], "
        r"and contextual \ensuremath{\infty}."
    )
    assert audit_latex_source(tex) == ()


def test_static_gate_rejects_unknown_references_and_citations():
    tex = _minimal_document(r"See \ref{sec:missing} and \cite{src:missing}.")
    codes = {issue.code for issue in audit_latex_source(tex)}
    assert "UNRESOLVED_REFERENCE_LABEL" in codes
    assert "UNRESOLVED_CITATION_KEY" in codes


def test_static_gate_rejects_duplicate_labels_and_bibliography_keys():
    tex = _minimal_document(
        r"\label{sec:a}\label{sec:a}"
        r"\begin{thebibliography}{9}"
        r"\bibitem{src:a} A\bibitem{src:a} B"
        r"\end{thebibliography}"
    )
    codes = {issue.code for issue in audit_latex_source(tex)}
    assert "DUPLICATE_LABEL" in codes
    assert "DUPLICATE_BIBLIOGRAPHY_KEY" in codes


def test_static_gate_rejects_unprojected_unicode_math_glyphs():
    codes = {issue.code for issue in audit_latex_source(_minimal_document("Raw ∞ must not remain."))}
    assert "RAW_MATH_UNICODE" in codes


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex unavailable")
def test_two_pass_compiler_produces_warning_free_pdf(tmp_path: Path):
    tex_path = tmp_path / "guideline.tex"
    pdf_path = tmp_path / "guideline.pdf"
    tex_path.write_text(_minimal_document("Clean document."), encoding="utf-8")

    result = compile_latex_pdf(tex_path, pdf_path, passes=2)

    assert result.engine == "pdflatex"
    assert result.passes == 2
    assert result.warnings == ()
    assert pdf_path.is_file()
    assert pdf_path.stat().st_size > 0


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex unavailable")
def test_two_pass_compiler_rejects_unresolved_reference_warning(tmp_path: Path):
    tex_path = tmp_path / "guideline.tex"
    pdf_path = tmp_path / "guideline.pdf"
    tex_path.write_text(_minimal_document(r"See \ref{missing}."), encoding="utf-8")

    with pytest.raises(PublicationIntegrityError):
        compile_latex_pdf(tex_path, pdf_path, passes=2)


def test_publication_manifest_records_state_identity_contract_and_hashes(tmp_path: Path):
    import hashlib
    import json

    from processing.publication_integrity import (
        PublicationCompilationResult,
        build_publication_manifest,
    )

    output = tmp_path / "output"
    output.mkdir()
    tex_path = output / "guideline.tex"
    pdf_path = output / "guideline.pdf"
    state_path = tmp_path / "state.json"
    semantic_path = tmp_path / "semantic.json"
    contract_path = tmp_path / "contract.yaml"
    tex_path.write_text("\\documentclass{article}\n", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-test")
    state_path.write_text(
        json.dumps({"schema_version": 6, "cycle": 3, "iteration": 4}),
        encoding="utf-8",
    )
    semantic_path.write_text(
        json.dumps({"document_id": "doc-1", "version": 2}),
        encoding="utf-8",
    )
    contract_path.write_text("version: 4\n", encoding="utf-8")

    manifest = build_publication_manifest(
        tex_path=tex_path,
        pdf_path=pdf_path,
        source_issues=(),
        compilation=PublicationCompilationResult(
            engine="pdflatex",
            passes=2,
            pdf_path=str(pdf_path),
            final_log_path=str(output / "guideline.log"),
        ),
        semantic_document_path=semantic_path,
        state_path=state_path,
        ir_contract_path=contract_path,
    )

    assert manifest["status"] == "validated"
    assert manifest["pipeline"] == {
        "cycle": 3,
        "iteration": 4,
        "state_schema_version": 6,
    }
    assert manifest["semantic_document"] == {"document_id": "doc-1", "version": 2}
    assert manifest["latex_ir_contract_version"] == "4"
    assert manifest["tex"]["sha256"] == hashlib.sha256(tex_path.read_bytes()).hexdigest()
    assert manifest["pdf"]["sha256"] == hashlib.sha256(pdf_path.read_bytes()).hexdigest()


def test_static_gate_rejects_grouped_raw_source_ids_in_plain_and_escaped_tex():
    plain = _minimal_document("[wiki_crystal_plasticity, wiki_finite_element_limit_analysis]")
    escaped = _minimal_document(r"[wiki\_crystal\_plasticity, wiki\_finite\_element\_limit\_analysis]")
    assert "RAW_CITATION_MARKER_IN_TEX" in {issue.code for issue in audit_latex_source(plain)}
    assert "RAW_CITATION_MARKER_IN_TEX" in {issue.code for issue in audit_latex_source(escaped)}


def test_static_gate_rejects_uncited_bibliography_entries():
    tex = _minimal_document(
        r"\cite{src:used}"
        r"\begin{thebibliography}{9}"
        r"\bibitem{src:used} Used"
        r"\bibitem{src:unused} Unused"
        r"\end{thebibliography}"
    )
    codes = {issue.code for issue in audit_latex_source(tex)}
    assert "UNCITED_BIBLIOGRAPHY_KEY" in codes


def test_builder_output_is_reproducible_and_does_not_depend_on_wall_clock_date():
    state = {"topic": "FEM", "objective": "Guide", "knowledge_graph": {}}
    sections = [{"title": "Evidence", "blocks": [
        {"type": "text", "text": "Supported."},
        {"type": "citation", "source_ids": ["paper_1"]},
    ]}]
    evidence = [{"source_id": "paper_1", "title": "Paper", "retriever_module": "research.article"}]
    first = build_latex_document(state, sections, evidence)
    second = build_latex_document(state, sections, evidence)
    assert first == second
    assert r"\date{}" in first
    assert r"\today" not in first


def test_document_gate_uses_reference_registry_not_source_name_shape_for_grouped_markers():
    model = build_document_model(
        {"topic": "FEM", "objective": "Guide"},
        [{"title": "Bad", "blocks": [{"type": "text", "text": "Claim [s1, missing]."}]}],
        [{"source_id": "s1", "title": "Known"}],
    )
    codes = {issue.code for issue in audit_document_model(model)}
    assert "RAW_CITATION_MARKER" in codes

@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex unavailable")
def test_compiler_adapts_to_three_pass_toc_label_convergence(tmp_path: Path):
    tex_path = tmp_path / "guideline.tex"
    pdf_path = tmp_path / "guideline.pdf"
    lines = [
        r"\documentclass{article}",
        r"\usepackage{hyperref}",
        r"\begin{document}",
        r"\tableofcontents",
    ]
    # A sufficiently long table of contents changes pagination on pass two,
    # which legitimately requires a third pass for stable labels/page numbers.
    for index in range(1, 81):
        lines.append(rf"\section{{Section {index}}}\label{{sec:{index}}} Text.")
    lines.append(r"\end{document}")
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = compile_latex_pdf(tex_path, pdf_path, passes=2, max_passes=5)

    assert result.passes == 3
    assert result.minimum_passes == 2
    assert result.maximum_passes == 5
    assert result.converged is True
    assert result.auxiliary_state_sha256
    assert pdf_path.is_file()


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex unavailable")
def test_compiler_fails_closed_when_convergence_exceeds_bound(tmp_path: Path):
    tex_path = tmp_path / "guideline.tex"
    pdf_path = tmp_path / "guideline.pdf"
    lines = [
        r"\documentclass{article}",
        r"\usepackage{hyperref}",
        r"\begin{document}",
        r"\tableofcontents",
    ]
    for index in range(1, 81):
        lines.append(rf"\section{{Section {index}}}\label{{sec:{index}}} Text.")
    lines.append(r"\end{document}")
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(PublicationIntegrityError) as exc_info:
        compile_latex_pdf(tex_path, pdf_path, passes=2, max_passes=2)

    assert any(issue.code == "LATEX_CONVERGENCE_NOT_REACHED" for issue in exc_info.value.issues)
    # Failure diagnostics must preserve the final LaTeX log for workflow artifacts.
    assert pdf_path.with_suffix(".log").is_file()


def test_compiler_rejects_maximum_passes_below_minimum(tmp_path: Path):
    tex_path = tmp_path / "guideline.tex"
    pdf_path = tmp_path / "guideline.pdf"
    tex_path.write_text(_minimal_document("Clean document."), encoding="utf-8")

    with pytest.raises(ValueError, match="max_passes"):
        compile_latex_pdf(tex_path, pdf_path, passes=3, max_passes=2)

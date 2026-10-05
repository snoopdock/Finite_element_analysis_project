"""Publication-integrity validation and deterministic PDF compilation.

This module closes the publication boundary after semantic Document -> LaTeX IR
projection. It does not repair malformed semantic content. Instead it rejects
plain-text math/citation leakage, audits the exact generated LaTeX source,
compiles with pdfLaTeX, validates the final log, and emits a machine-readable
artifact receipt.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Iterable

from processing.latex_ir import (
    DocumentModel,
    EquationBlock,
    FigureBlock,
    IRTextSpan,
    ParagraphBlock,
    TableBlock,
    TextBlock,
)
from utils.latex import PLAIN_TEXT_UNICODE_MATH_MAP
from core.authoring_integrity import RAW_MATH_COMMAND_RE


@dataclass(frozen=True)
class PublicationIntegrityIssue:
    severity: str
    code: str
    message: str
    context: str = ""

    def format(self) -> str:
        suffix = f" [{self.context}]" if self.context else ""
        return f"{self.severity.upper()} {self.code}: {self.message}{suffix}"


@dataclass(frozen=True, eq=False)
class PublicationIntegrityReport:
    issues: tuple[PublicationIntegrityIssue, ...] = ()

    @property
    def errors(self) -> tuple[PublicationIntegrityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[PublicationIntegrityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def ok(self) -> bool:
        return not self.errors

    def __iter__(self):
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)

    def __eq__(self, other) -> bool:
        if isinstance(other, PublicationIntegrityReport):
            return self.issues == other.issues
        if isinstance(other, (tuple, list)):
            return self.issues == tuple(other)
        return NotImplemented


class PublicationIntegrityError(ValueError):
    """Raised when generated publication output violates a hard invariant."""

    def __init__(self, issues: Iterable[PublicationIntegrityIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(issue.format() for issue in self.issues))


@dataclass(frozen=True)
class PublicationCompilationResult:
    engine: str
    passes: int
    pdf_path: str
    final_log_path: str
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict:
        return asdict(self)


_RAW_MATH_COMMAND_RE = RAW_MATH_COMMAND_RE
_SOURCE_TOKEN_RE = re.compile(
    r"(?:arxiv|wiki|wikipedia|s2|doi|pmid|book|source)(?:_|:)[A-Za-z0-9_.:/-]+|"
    r"[A-Za-z][A-Za-z0-9.:-]*_[A-Za-z0-9_.:/-]+",
    flags=re.IGNORECASE,
)
_BRACKET_GROUP_RE = re.compile(r"\[(?P<body>[^\[\]]+)\]")


def _raw_source_marker_groups(
    text: str,
    *,
    latex_escaped: bool = False,
    known_source_ids: set[str] | None = None,
):
    """Yield source-ID bracket groups that escaped semantic citation nodes.

    At the semantic/IR gate, exact evidence-registry membership is sufficient
    to identify a leaked citation even when source IDs use short/custom names.
    At the standalone LaTeX gate, conservative source-shaped token recognition
    provides the final defense without inventing an external registry.
    """
    known_source_ids = known_source_ids or set()
    for match in _BRACKET_GROUP_RE.finditer(text):
        body = match.group("body")
        if latex_escaped:
            body = body.replace(r"\_", "_")
        tokens = tuple(part.strip() for part in body.split(","))
        if not tokens or any(not token for token in tokens):
            continue
        source_shaped = all(_SOURCE_TOKEN_RE.fullmatch(token) for token in tokens)
        registry_related = any(token in known_source_ids for token in tokens)
        if source_shaped or registry_related:
            yield match.group(0), tokens


_RAW_SEMANTIC_MARKER_RE = re.compile(r"\[\[(?:CITE|CITES|REF|EQ|NEW_EQ):[^\]]+\]\]")
_ESCAPED_RAW_MATH_RE = re.compile(
    r"\\textbackslash\{\}(?:in|nabla|partial|int|sum|prod|mathbf|frac|sqrt|infty)\b"
)
_FORBIDDEN_GENERATOR_PATTERNS = (
    (r"\@safemath", "GLOBAL_MATH_REDEFINITION"),
    (r"\sloppy", "GLOBAL_SLOPPY"),
    (r"\usepackage[strings]{underscore}", "GLOBAL_UNDERSCORE_PACKAGE"),
    (r"\newunicodechar", "GLOBAL_UNICODE_MAPPING"),
)
_CITE_RE = re.compile(r"\\cite\{([^{}]+)\}")
_BIBITEM_RE = re.compile(r"\\bibitem\{([^{}]+)\}")
_REF_RE = re.compile(r"\\ref\{([^{}]+)\}")
_LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")


def _plain_text_payloads(document: DocumentModel):
    yield "document.topic", document.topic
    yield "document.objective", document.objective
    for section_index, section in enumerate(document.sections):
        yield f"sections[{section_index}].title", section.title
        for block_index, block in enumerate(section.blocks):
            base = f"sections[{section_index}].blocks[{block_index}]"
            if isinstance(block, TextBlock):
                yield f"{base}.text", block.text
            elif isinstance(block, ParagraphBlock):
                for inline_index, inline in enumerate(block.content):
                    if isinstance(inline, IRTextSpan):
                        yield f"{base}.content[{inline_index}].text", inline.text
            elif isinstance(block, EquationBlock) and block.caption:
                yield f"{base}.caption", block.caption
            elif isinstance(block, FigureBlock):
                yield f"{base}.caption", block.caption
            elif isinstance(block, TableBlock):
                yield f"{base}.caption", block.caption
                for column_index, column in enumerate(block.columns):
                    yield f"{base}.columns[{column_index}]", column
                for row_index, row in enumerate(block.rows):
                    for cell_index, cell in enumerate(row):
                        yield f"{base}.rows[{row_index}][{cell_index}]", cell


def audit_document_model(document: DocumentModel) -> PublicationIntegrityReport:
    """Reject raw math commands or source markers in semantic plain text."""
    issues: list[PublicationIntegrityIssue] = []
    reference_ids = {reference.source_id for reference in document.references}
    for context, text in _plain_text_payloads(document):
        if not text:
            continue
        match = _RAW_MATH_COMMAND_RE.search(text)
        if match:
            issues.append(
                PublicationIntegrityIssue(
                    "error",
                    "RAW_MATH_IN_TEXT",
                    f"raw mathematical LaTeX command {match.group(0)!r} requires a typed math node",
                    context,
                )
            )
        semantic_marker = _RAW_SEMANTIC_MARKER_RE.search(text)
        if semantic_marker:
            issues.append(
                PublicationIntegrityIssue(
                    "error",
                    "RAW_SEMANTIC_MARKER",
                    f"semantic authoring marker survived as plain text: {semantic_marker.group(0)}",
                    context,
                )
            )
        for raw_group, tokens in _raw_source_marker_groups(text, known_source_ids=reference_ids):
            known = [token for token in tokens if token in reference_ids]
            relation = "known" if len(known) == len(tokens) else "partially/unresolved"
            issues.append(
                PublicationIntegrityIssue(
                    "error",
                    "RAW_CITATION_MARKER",
                    f"{relation} source token group {raw_group} survived as plain text instead of semantic citation occurrence(s)",
                    context,
                )
            )
    return PublicationIntegrityReport(tuple(issues))


def _strip_math_contexts(tex: str) -> str:
    """Remove explicit generated math regions before prose-command scanning."""
    patterns = (
        r"\\\(.*?\\\)",
        r"\\\[.*?\\\]",
        r"\\begin\{equation\}.*?\\end\{equation\}",
    )
    result = tex
    for pattern in patterns:
        result = re.sub(pattern, "", result, flags=re.DOTALL)
    # Local compatibility fragments emitted by escape_text are legitimate.
    result = re.sub(r"\\ensuremath\{.*?\}", "", result, flags=re.DOTALL)
    return result


def audit_latex_source(tex: str) -> PublicationIntegrityReport:
    """Audit the exact generated LaTeX source without rewriting it."""
    issues: list[PublicationIntegrityIssue] = []
    for pattern, code in _FORBIDDEN_GENERATOR_PATTERNS:
        if pattern in tex:
            issues.append(
                PublicationIntegrityIssue(
                    "error", code, f"generated source contains retired compatibility construct {pattern!r}"
                )
            )

    if _RAW_SEMANTIC_MARKER_RE.search(tex):
        issues.append(
            PublicationIntegrityIssue(
                "error", "RAW_SEMANTIC_MARKER", "semantic authoring marker remains in generated LaTeX"
            )
        )
    for raw_group, tokens in _raw_source_marker_groups(tex, latex_escaped=True):
        issues.append(
            PublicationIntegrityIssue(
                "error",
                "RAW_CITATION_MARKER_IN_TEX",
                f"source token group {raw_group} remains in generated LaTeX instead of \\cite projection",
            )
        )

    prose = _strip_math_contexts(tex)
    if _ESCAPED_RAW_MATH_RE.search(prose):
        issues.append(
            PublicationIntegrityIssue(
                "error",
                "ESCAPED_RAW_MATH",
                "raw mathematical LaTeX was escaped as prose instead of projected from a typed math node",
            )
        )
    # Scan only document body prose for raw mathematical commands; preamble
    # legitimately contains package/configuration commands.
    body_start = prose.find(r"\begin{document}")
    body = prose[body_start:] if body_start >= 0 else prose
    match = _RAW_MATH_COMMAND_RE.search(body)
    if match:
        issues.append(
            PublicationIntegrityIssue(
                "error",
                "RAW_MATH_COMMAND_IN_TEX",
                f"mathematical command outside generated math context: {match.group(0)!r}",
            )
        )

    raw_unicode = sorted({char for char in PLAIN_TEXT_UNICODE_MATH_MAP if char in tex})
    if raw_unicode:
        issues.append(
            PublicationIntegrityIssue(
                "error",
                "RAW_MATH_UNICODE",
                "pdfLaTeX-sensitive mathematical Unicode remains after projection: " + " ".join(raw_unicode),
            )
        )

    citation_keys: list[str] = []
    for group in _CITE_RE.findall(tex):
        citation_keys.extend(key.strip() for key in group.split(",") if key.strip())
    bibliography_keys = _BIBITEM_RE.findall(tex)
    bib_set = set(bibliography_keys)
    missing_citations = sorted(set(citation_keys) - bib_set)
    if missing_citations:
        issues.append(
            PublicationIntegrityIssue(
                "error",
                "UNRESOLVED_CITATION_KEY",
                "citation key(s) have no bibliography item: " + ", ".join(missing_citations),
            )
        )
    duplicate_bib = sorted({key for key in bibliography_keys if bibliography_keys.count(key) > 1})
    if duplicate_bib:
        issues.append(
            PublicationIntegrityIssue(
                "error",
                "DUPLICATE_BIBLIOGRAPHY_KEY",
                "duplicate bibliography key(s): " + ", ".join(duplicate_bib),
            )
        )
    uncited_bibliography = sorted(bib_set - set(citation_keys))
    if uncited_bibliography:
        issues.append(
            PublicationIntegrityIssue(
                "error",
                "UNCITED_BIBLIOGRAPHY_KEY",
                "bibliography key(s) have no semantic citation occurrence: "
                + ", ".join(uncited_bibliography),
            )
        )

    labels = _LABEL_RE.findall(tex)
    label_set = set(labels)
    refs = _REF_RE.findall(tex)
    missing_refs = sorted(set(refs) - label_set)
    if missing_refs:
        issues.append(
            PublicationIntegrityIssue(
                "error",
                "UNRESOLVED_REFERENCE_LABEL",
                "reference label(s) have no emitted anchor: " + ", ".join(missing_refs),
            )
        )
    duplicate_labels = sorted({label for label in labels if labels.count(label) > 1})
    if duplicate_labels:
        issues.append(
            PublicationIntegrityIssue(
                "error", "DUPLICATE_LABEL", "duplicate LaTeX label(s): " + ", ".join(duplicate_labels)
            )
        )
    return PublicationIntegrityReport(tuple(issues))


def assert_latex_integrity(tex: str) -> PublicationIntegrityReport:
    report = audit_latex_source(tex)
    if report.errors:
        raise PublicationIntegrityError(report.errors)
    return report


def assert_publication_integrity(document: DocumentModel, tex: str) -> PublicationIntegrityReport:
    document_report = audit_document_model(document)
    source_report = audit_latex_source(tex)
    report = PublicationIntegrityReport(document_report.issues + source_report.issues)
    if report.errors:
        raise PublicationIntegrityError(report.errors)
    return report


def audit_latex_log(log_text: str, *, strict: bool = True) -> PublicationIntegrityReport:
    """Audit the final pdfLaTeX pass; CI uses strict warning-free mode."""
    issues: list[PublicationIntegrityIssue] = []
    hard_patterns = (
        ("Undefined control sequence", "UNDEFINED_CONTROL_SEQUENCE"),
        ("Fatal error", "LATEX_FATAL_ERROR"),
        ("Emergency stop", "LATEX_EMERGENCY_STOP"),
        ("There were undefined references", "UNDEFINED_REFERENCES"),
        ("There were undefined citations", "UNDEFINED_CITATIONS"),
        ("multiply defined", "MULTIPLY_DEFINED_REFERENCE"),
    )
    for marker, code in hard_patterns:
        if marker in log_text:
            issues.append(PublicationIntegrityIssue("error", code, marker))
    for line in log_text.splitlines():
        if line.startswith("! "):
            issues.append(PublicationIntegrityIssue("error", "LATEX_ERROR", line.strip()))

    for marker in (
        "Overfull \\hbox",
        "Overfull \\vbox",
        "Underfull \\hbox",
        "Underfull \\vbox",
    ):
        count = log_text.count(marker)
        if count:
            issues.append(
                PublicationIntegrityIssue(
                    "error" if strict else "warning",
                    "LAYOUT_WARNING",
                    f"{marker} occurred {count} time(s)",
                )
            )
    for line in sorted({line.strip() for line in log_text.splitlines() if "LaTeX Warning:" in line}):
        issues.append(
            PublicationIntegrityIssue(
                "error" if strict else "warning", "LATEX_WARNING", line
            )
        )
    return PublicationIntegrityReport(tuple(issues))


def _error(code: str, message: str) -> PublicationIntegrityError:
    return PublicationIntegrityError((PublicationIntegrityIssue("error", code, message),))


def compile_latex_pdf(
    tex_path: str | Path,
    output_pdf: str | Path,
    *,
    passes: int = 2,
    engine: str = "pdflatex",
    timeout_seconds: int = 90,
) -> PublicationCompilationResult:
    """Compile in an isolated directory and require a clean final pass."""
    if passes < 2:
        raise ValueError("publication compilation requires at least two passes")
    tex_path = Path(tex_path).resolve()
    output_pdf = Path(output_pdf).resolve()
    if not tex_path.is_file():
        raise _error("LATEX_SOURCE_MISSING", f"LaTeX source does not exist: {tex_path}")
    engine_path = shutil.which(engine)
    if not engine_path:
        raise _error("LATEX_ENGINE_MISSING", f"required LaTeX engine is unavailable: {engine}")

    repo_root = tex_path.parent.parent if tex_path.parent.name == "output" else tex_path.parent
    final_log_copy = output_pdf.with_suffix(".log")
    with tempfile.TemporaryDirectory(prefix="fea-publication-") as temp_dir:
        temp = Path(temp_dir)
        for pass_index in range(1, passes + 1):
            result = subprocess.run(
                [
                    engine_path,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-file-line-error",
                    f"-output-directory={temp}",
                    str(tex_path),
                ],
                cwd=repo_root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
            if result.returncode != 0:
                tail = "\n".join((result.stdout or "").splitlines()[-80:])
                raise _error(
                    "LATEX_COMPILE_FAILED",
                    f"{engine} pass {pass_index} failed with exit code {result.returncode}:\n{tail}",
                )

        compiled_pdf = temp / f"{tex_path.stem}.pdf"
        log_path = temp / f"{tex_path.stem}.log"
        if not compiled_pdf.is_file() or compiled_pdf.stat().st_size == 0:
            raise _error("PDF_NOT_PRODUCED", "LaTeX compilation did not produce a non-empty PDF")
        if not log_path.is_file():
            raise _error("LATEX_LOG_MISSING", "LaTeX compilation did not produce a final log")
        log_report = audit_latex_log(log_path.read_text(encoding="utf-8", errors="replace"), strict=True)
        if log_report.errors:
            raise PublicationIntegrityError(log_report.errors)

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(compiled_pdf, output_pdf)
        shutil.copyfile(log_path, final_log_copy)

    return PublicationCompilationResult(
        engine=engine,
        passes=passes,
        pdf_path=str(output_pdf),
        final_log_path=str(final_log_copy),
        warnings=(),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _json(path: Path | None):
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_publication_manifest(
    *,
    tex_path: str | Path,
    pdf_path: str | Path,
    source_issues: Iterable[PublicationIntegrityIssue],
    compilation: PublicationCompilationResult,
    semantic_document_path: str | Path | None = None,
    state_path: str | Path | None = None,
    ir_contract_path: str | Path | None = None,
) -> dict:
    """Create an audit receipt tying source commit, state, semantic document and artifacts."""
    tex_path = Path(tex_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    repo_root = tex_path.parent.parent if tex_path.parent.name == "output" else tex_path.parent
    state = _json(Path(state_path)) if state_path else None
    semantic = _json(Path(semantic_document_path)) if semantic_document_path else None
    contract_version = None
    if ir_contract_path:
        contract = Path(ir_contract_path)
        if contract.is_file():
            for line in contract.read_text(encoding="utf-8").splitlines():
                if line.startswith("version:"):
                    contract_version = line.split(":", 1)[1].strip()
                    break

    def display(path: Path) -> str:
        try:
            return str(path.relative_to(repo_root))
        except ValueError:
            return str(path)

    return {
        "schema_version": 1,
        "status": "validated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": _git_commit(repo_root),
        "pipeline": {
            "cycle": state.get("cycle") if isinstance(state, dict) else None,
            "iteration": state.get("iteration") if isinstance(state, dict) else None,
            "state_schema_version": state.get("schema_version") if isinstance(state, dict) else None,
        },
        "semantic_document": {
            "document_id": semantic.get("document_id") if isinstance(semantic, dict) else None,
            "version": semantic.get("version") if isinstance(semantic, dict) else None,
        },
        "latex_ir_contract_version": contract_version,
        "tex": {"path": display(tex_path), "sha256": _sha256_file(tex_path), "size_bytes": tex_path.stat().st_size},
        "pdf": {"path": display(pdf_path), "sha256": _sha256_file(pdf_path), "size_bytes": pdf_path.stat().st_size},
        "static_audit": {
            "ok": not any(issue.severity == "error" for issue in source_issues),
            "issues": [asdict(issue) for issue in source_issues],
        },
        "compilation": compilation.to_dict(),
    }

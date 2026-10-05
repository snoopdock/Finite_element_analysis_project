"""Renderer-neutral LaTeX intermediate representation.

The module supports two input generations during migration:

* compatibility blocks (``TextBlock``, ``MathBlock``, ``CitationBlock``,
  ``LegacyLatexBlock``), still accepted by older adapters; and
* ordered semantic paragraph/equation blocks produced from
  ``core.document_model.Document``.

Scientific identity remains outside this module.  The IR carries identifiers
only for traceability and rendering; it never invents or redefines them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Mapping, Sequence

from processing.asset_policy import AssetPathError, validate_figure_asset_path


class DocumentModelError(ValueError):
    """Raised when input cannot satisfy the document-model contract."""


# ---------------------------------------------------------------------------
# Compatibility block language
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class MathBlock:
    """Renderer-neutral display math without authoritative equation identity."""

    expression: str


@dataclass(frozen=True)
class CitationBlock:
    """Compatibility citation block referring to normalized source IDs."""

    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class LegacyLatexBlock:
    """Explicit compatibility block for already-authored LaTeX fragments."""

    source: str


# ---------------------------------------------------------------------------
# Canonical ordered paragraph language used by Document -> LaTeX IR
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRTextSpan:
    text: str


@dataclass(frozen=True)
class IRMathSpan:
    """Inline mathematical presentation with no domain-equation authority."""

    expression: str


@dataclass(frozen=True)
class IRCitationSpan:
    """Inline citation occurrence preserving document ordering and identity."""

    source_ids: tuple[str, ...]
    occurrence_id: str = ""


@dataclass(frozen=True)
class IRCrossReferenceSpan:
    """Resolved internal reference to a labeled semantic document target."""

    target_id: str
    target_type: str
    label: str
    occurrence_id: str = ""


ParagraphInline = IRTextSpan | IRMathSpan | IRCitationSpan | IRCrossReferenceSpan


@dataclass(frozen=True)
class ParagraphBlock:
    """Ordered inline content for one semantic paragraph."""

    content: tuple[ParagraphInline, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EquationBlock:
    """Rendered placement of an authoritative domain equation.

    ``equation_id`` identifies the scientific object. ``occurrence_id``
    identifies this document placement. The resolved expression is copied into
    the IR as rendering payload; the semantic domain model remains authoritative.
    """

    equation_id: str
    expression: str
    occurrence_id: str
    label: str | None = None
    caption: str | None = None


@dataclass(frozen=True)
class FigureBlock:
    """Renderable placement of a semantic figure object."""

    figure_id: str
    asset: str
    caption: str
    label: str
    source_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TableBlock:
    """Renderable placement of a semantic table object."""

    table_id: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    caption: str
    label: str
    source_ids: tuple[str, ...] = field(default_factory=tuple)


DocumentBlock = (
    TextBlock
    | MathBlock
    | CitationBlock
    | LegacyLatexBlock
    | ParagraphBlock
    | EquationBlock
    | FigureBlock
    | TableBlock
)


@dataclass(frozen=True)
class SectionModel:
    title: str
    blocks: tuple[DocumentBlock, ...] = field(default_factory=tuple)
    section_id: str = ""
    label: str | None = None


@dataclass(frozen=True)
class ReferenceModel:
    source_id: str
    title: str
    url: str = ""
    source_type: str = "misc"
    retrieved_at: str = "N/A"
    citation_key: str = ""


@dataclass(frozen=True)
class DocumentModel:
    topic: str
    objective: str
    sections: tuple[SectionModel, ...]
    references: tuple[ReferenceModel, ...] = field(default_factory=tuple)
    source_document_id: str = ""


def _as_text(value: Any, field_name: str, *, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise DocumentModelError(f"{field_name} must be a string")
    return value


def _require_keys(value: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise DocumentModelError(
            f"{context} contains unsupported fields: {', '.join(unknown)}"
        )


def _normalize_inline_content(
    values: Sequence[Mapping[str, Any]],
    *,
    context: str,
) -> tuple[ParagraphInline, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise DocumentModelError(f"{context} must be a sequence")

    result: list[ParagraphInline] = []
    for index, raw in enumerate(values):
        item_context = f"{context}[{index}]"
        if not isinstance(raw, Mapping):
            raise DocumentModelError(f"{item_context} must be a mapping")
        kind = raw.get("type")
        if kind == "text":
            _require_keys(raw, {"type", "text"}, item_context)
            text = _as_text(raw.get("text"), f"{item_context}.text")
            if text:
                result.append(IRTextSpan(text))
        elif kind == "inline_math":
            _require_keys(raw, {"type", "expression"}, item_context)
            expression = _as_text(
                raw.get("expression"), f"{item_context}.expression"
            ).strip()
            if not expression:
                raise DocumentModelError(
                    f"{item_context}.expression must not be empty"
                )
            result.append(IRMathSpan(expression))
        elif kind == "citation":
            _require_keys(raw, {"type", "source_ids", "occurrence_id"}, item_context)
            raw_ids = raw.get("source_ids")
            if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes)):
                raise DocumentModelError(f"{item_context}.source_ids must be a sequence")
            source_ids = tuple(
                _as_text(source_id, f"{item_context}.source_ids[{source_index}]").strip()
                for source_index, source_id in enumerate(raw_ids)
            )
            occurrence_id = _as_text(
                raw.get("occurrence_id"), f"{item_context}.occurrence_id"
            ).strip()
            if not source_ids or any(not source_id for source_id in source_ids):
                raise DocumentModelError(
                    f"{item_context}.source_ids must contain non-empty strings"
                )
            if len(set(source_ids)) != len(source_ids):
                raise DocumentModelError(
                    f"{item_context}.source_ids must not contain duplicates"
                )
            result.append(IRCitationSpan(source_ids, occurrence_id=occurrence_id))
        elif kind == "cross_reference":
            _require_keys(
                raw,
                {"type", "target_id", "target_type", "label", "occurrence_id"},
                item_context,
            )
            target_id = _as_text(
                raw.get("target_id"), f"{item_context}.target_id"
            ).strip()
            target_type = _as_text(
                raw.get("target_type"), f"{item_context}.target_type"
            ).strip()
            label = _as_text(raw.get("label"), f"{item_context}.label").strip()
            occurrence_id = _as_text(
                raw.get("occurrence_id"), f"{item_context}.occurrence_id"
            ).strip()
            if not target_id or not target_type or not label or not occurrence_id:
                raise DocumentModelError(
                    f"{item_context} requires target_id, target_type, label, and occurrence_id"
                )
            result.append(
                IRCrossReferenceSpan(
                    target_id=target_id,
                    target_type=target_type,
                    label=label,
                    occurrence_id=occurrence_id,
                )
            )
        else:
            raise DocumentModelError(
                f"unsupported paragraph inline type {kind!r} in {item_context}"
            )
    if not result:
        raise DocumentModelError(f"{context} must contain at least one renderable item")
    return tuple(result)


def normalize_sections(sections: Sequence[Mapping[str, Any]]) -> tuple[SectionModel, ...]:
    """Normalize the closed section input language without guessing semantics."""

    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
        raise DocumentModelError("sections must be a sequence")

    normalized: list[SectionModel] = []
    for index, section in enumerate(sections):
        if not isinstance(section, Mapping):
            raise DocumentModelError(f"section {index} must be a mapping")
        _require_keys(section, {"title", "blocks", "section_id", "label"}, f"section {index}")
        title = (
            _as_text(
                section.get("title"),
                f"section {index}.title",
                default="Untitled",
            ).strip()
            or "Untitled"
        )
        section_id = _as_text(
            section.get("section_id"), f"section {index}.section_id"
        ).strip()
        label = section.get("label")
        if label is not None and not isinstance(label, str):
            raise DocumentModelError(f"section {index}.label must be a string or null")
        if "blocks" not in section:
            raise DocumentModelError(f"section {index}.blocks is required")
        raw_blocks = section["blocks"]
        if not isinstance(raw_blocks, Sequence) or isinstance(raw_blocks, (str, bytes)):
            raise DocumentModelError(f"section {index}.blocks must be a sequence")
        parsed: list[DocumentBlock] = []
        for block_index, block in enumerate(raw_blocks):
            context = f"section {index}.blocks[{block_index}]"
            if not isinstance(block, Mapping):
                raise DocumentModelError(f"{context} must be a mapping")
            kind = block.get("type")
            if kind == "text":
                _require_keys(block, {"type", "text"}, context)
                text = _as_text(block.get("text"), f"{context}.text")
                if not text:
                    raise DocumentModelError(f"{context}.text must not be empty")
                parsed.append(TextBlock(text))
            elif kind == "math":
                _require_keys(block, {"type", "expression"}, context)
                expression = _as_text(
                    block.get("expression"), f"{context}.expression"
                ).strip()
                if not expression:
                    raise DocumentModelError(
                        f"{context}.expression must not be empty"
                    )
                parsed.append(MathBlock(expression))
            elif kind == "citation":
                _require_keys(block, {"type", "source_ids"}, context)
                raw_ids = block.get("source_ids")
                if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes)):
                    raise DocumentModelError(f"{context}.source_ids must be a sequence")
                source_ids = tuple(
                    _as_text(
                        source_id,
                        f"{context}.source_ids[{source_index}]",
                    ).strip()
                    for source_index, source_id in enumerate(raw_ids)
                )
                if not source_ids or any(not source_id for source_id in source_ids):
                    raise DocumentModelError(
                        f"{context}.source_ids must contain non-empty strings"
                    )
                if len(set(source_ids)) != len(source_ids):
                    raise DocumentModelError(
                        f"{context}.source_ids must not contain duplicates"
                    )
                parsed.append(CitationBlock(source_ids))
            elif kind == "paragraph":
                _require_keys(block, {"type", "content"}, context)
                parsed.append(
                    ParagraphBlock(
                        _normalize_inline_content(
                            block.get("content", ()), context=f"{context}.content"
                        )
                    )
                )
            elif kind == "equation":
                _require_keys(
                    block,
                    {
                        "type",
                        "equation_id",
                        "expression",
                        "occurrence_id",
                        "label",
                        "caption",
                    },
                    context,
                )
                equation_id = _as_text(
                    block.get("equation_id"), f"{context}.equation_id"
                ).strip()
                expression = _as_text(
                    block.get("expression"), f"{context}.expression"
                ).strip()
                occurrence_id = _as_text(
                    block.get("occurrence_id"), f"{context}.occurrence_id"
                ).strip()
                label = block.get("label")
                caption = block.get("caption")
                if not equation_id or not expression or not occurrence_id:
                    raise DocumentModelError(
                        f"{context} requires equation_id, expression, and occurrence_id"
                    )
                if label is not None and not isinstance(label, str):
                    raise DocumentModelError(f"{context}.label must be a string or null")
                if caption is not None and not isinstance(caption, str):
                    raise DocumentModelError(f"{context}.caption must be a string or null")
                parsed.append(
                    EquationBlock(
                        equation_id=equation_id,
                        expression=expression,
                        occurrence_id=occurrence_id,
                        label=label,
                        caption=caption,
                    )
                )
            elif kind == "figure":
                _require_keys(
                    block,
                    {"type", "figure_id", "asset", "caption", "label", "source_ids"},
                    context,
                )
                raw_ids = block.get("source_ids", ())
                if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes)):
                    raise DocumentModelError(f"{context}.source_ids must be a sequence")
                parsed.append(
                    FigureBlock(
                        figure_id=_as_text(block.get("figure_id"), f"{context}.figure_id").strip(),
                        asset=_as_text(block.get("asset"), f"{context}.asset").strip(),
                        caption=_as_text(block.get("caption"), f"{context}.caption").strip(),
                        label=_as_text(block.get("label"), f"{context}.label").strip(),
                        source_ids=tuple(
                            _as_text(source_id, f"{context}.source_ids[{i}]").strip()
                            for i, source_id in enumerate(raw_ids)
                        ),
                    )
                )
            elif kind == "table":
                _require_keys(
                    block,
                    {"type", "table_id", "columns", "rows", "caption", "label", "source_ids"},
                    context,
                )
                raw_columns = block.get("columns")
                raw_rows = block.get("rows")
                raw_ids = block.get("source_ids", ())
                if not isinstance(raw_columns, Sequence) or isinstance(raw_columns, (str, bytes)):
                    raise DocumentModelError(f"{context}.columns must be a sequence")
                if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
                    raise DocumentModelError(f"{context}.rows must be a sequence")
                if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes)):
                    raise DocumentModelError(f"{context}.source_ids must be a sequence")
                rows = []
                for row_index, raw_row in enumerate(raw_rows):
                    if not isinstance(raw_row, Sequence) or isinstance(raw_row, (str, bytes)):
                        raise DocumentModelError(f"{context}.rows[{row_index}] must be a sequence")
                    rows.append(tuple(
                        _as_text(cell, f"{context}.rows[{row_index}][{cell_index}]")
                        for cell_index, cell in enumerate(raw_row)
                    ))
                parsed.append(
                    TableBlock(
                        table_id=_as_text(block.get("table_id"), f"{context}.table_id").strip(),
                        columns=tuple(
                            _as_text(column, f"{context}.columns[{i}]").strip()
                            for i, column in enumerate(raw_columns)
                        ),
                        rows=tuple(rows),
                        caption=_as_text(block.get("caption"), f"{context}.caption").strip(),
                        label=_as_text(block.get("label"), f"{context}.label").strip(),
                        source_ids=tuple(
                            _as_text(source_id, f"{context}.source_ids[{i}]").strip()
                            for i, source_id in enumerate(raw_ids)
                        ),
                    )
                )
            elif kind == "legacy_latex":
                _require_keys(block, {"type", "source"}, context)
                source = _as_text(block.get("source"), f"{context}.source")
                if not source:
                    raise DocumentModelError(f"{context}.source must not be empty")
                parsed.append(LegacyLatexBlock(source))
            else:
                raise DocumentModelError(
                    f"unsupported block type {kind!r} in {context}"
                )
        normalized.append(
            SectionModel(
                title=title,
                blocks=tuple(parsed),
                section_id=section_id,
                label=label,
            )
        )
    return tuple(normalized)


_CITATION_KEY_STEM_RE = re.compile(r"[^A-Za-z0-9._-]+")


def citation_key_for_source_id(source_id: str) -> str:
    """Project authoritative source identity into a stable LaTeX citation key.

    The key is deterministic but is not itself semantic identity.  A readable
    stem is retained for diagnostics and a SHA-256 suffix prevents collisions
    introduced by character normalization or truncation.
    """
    if not isinstance(source_id, str) or not source_id.strip():
        raise DocumentModelError("source_id must be a non-empty string")
    source_id = source_id.strip()
    stem = _CITATION_KEY_STEM_RE.sub("-", source_id).strip("-._")
    if not stem:
        stem = "source"
    stem = stem[:48]
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:12]
    return f"src:{stem}-{digest}"


def normalize_references(evidence: Sequence[Mapping[str, Any]]) -> tuple[ReferenceModel, ...]:
    """Convert retrieval receipts into renderer-neutral reference records."""

    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise DocumentModelError("evidence must be a sequence")

    references: list[ReferenceModel] = []
    seen_source_ids: set[str] = set()
    for index, source in enumerate(evidence):
        if not isinstance(source, Mapping):
            raise DocumentModelError(f"evidence {index} must be a mapping")
        _require_keys(
            source,
            {"source_id", "title", "url", "retriever_module", "retrieved_at"},
            f"evidence {index}",
        )
        source_id = _as_text(source.get("source_id"), "source_id").strip()
        if not source_id:
            raise DocumentModelError(f"evidence {index}.source_id must not be empty")
        if source_id in seen_source_ids:
            raise DocumentModelError(f"duplicate source_id in evidence: {source_id!r}")
        seen_source_ids.add(source_id)
        references.append(
            ReferenceModel(
                source_id=source_id,
                title=_as_text(source.get("title"), "title", default="Unknown Title"),
                url=_as_text(source.get("url"), "url"),
                source_type=_as_text(
                    source.get("retriever_module"),
                    "retriever_module",
                    default="misc",
                ),
                retrieved_at=_as_text(
                    source.get("retrieved_at"), "retrieved_at", default="N/A"
                ),
                citation_key=citation_key_for_source_id(source_id),
            )
        )
    return tuple(references)


def _validate_source_ids(
    source_ids: tuple[str, ...],
    *,
    context: str,
    reference_ids: set[str],
) -> None:
    if not isinstance(source_ids, tuple):
        raise DocumentModelError(f"{context}.source_ids must be a tuple")
    if not source_ids or any(
        not isinstance(source_id, str) or not source_id.strip()
        for source_id in source_ids
    ):
        raise DocumentModelError(
            f"{context}.source_ids must contain non-empty strings"
        )
    if len(set(source_ids)) != len(source_ids):
        raise DocumentModelError(f"{context}.source_ids must not contain duplicates")
    missing = [source_id for source_id in source_ids if source_id not in reference_ids]
    if missing:
        raise DocumentModelError(
            f"{context} references unknown source_id(s): {', '.join(missing)}"
        )


_LATEX_LABEL_RE = re.compile(r"[A-Za-z0-9:._/-]+")
_LATEX_CITATION_KEY_RE = re.compile(r"[A-Za-z0-9:._-]+")


def _validate_ir_label(label: str, *, context: str) -> None:
    if not isinstance(label, str) or not label.strip():
        raise DocumentModelError(f"{context} must be a non-empty string")
    if not _LATEX_LABEL_RE.fullmatch(label):
        raise DocumentModelError(
            f"{context} contains unsupported LaTeX label characters: {label!r}"
        )


def validate_document_model(document: DocumentModel) -> None:
    """Validate structure, field types, labels, and cross-reference integrity."""

    if not isinstance(document, DocumentModel):
        raise DocumentModelError("document must be a DocumentModel")
    if not isinstance(document.topic, str) or not isinstance(document.objective, str):
        raise DocumentModelError("document topic and objective must be strings")
    if not document.topic.strip() or not document.objective.strip():
        raise DocumentModelError(
            "document topic and objective must be non-empty strings"
        )
    if not isinstance(document.source_document_id, str):
        raise DocumentModelError("document source_document_id must be a string")
    if not isinstance(document.sections, tuple) or not isinstance(document.references, tuple):
        raise DocumentModelError("document sections and references must be tuples")

    reference_ids: set[str] = set()
    citation_keys: set[str] = set()
    for index, reference in enumerate(document.references):
        if not isinstance(reference, ReferenceModel):
            raise DocumentModelError(f"reference {index} must be a ReferenceModel")
        for field_name in (
            "source_id",
            "title",
            "url",
            "source_type",
            "retrieved_at",
            "citation_key",
        ):
            if not isinstance(getattr(reference, field_name), str):
                raise DocumentModelError(
                    f"reference {index}.{field_name} must be a string"
                )
        if not reference.source_id.strip():
            raise DocumentModelError(f"reference {index}.source_id must not be empty")
        if reference.source_id in reference_ids:
            raise DocumentModelError(
                f"duplicate source_id in document: {reference.source_id!r}"
            )
        reference_ids.add(reference.source_id)
        if not reference.citation_key.strip() or reference.citation_key in citation_keys:
            raise DocumentModelError(
                f"invalid or duplicate citation_key: {reference.citation_key!r}"
            )
        if not _LATEX_CITATION_KEY_RE.fullmatch(reference.citation_key):
            raise DocumentModelError(
                "citation_key contains unsupported LaTeX key characters: "
                f"{reference.citation_key!r}"
            )
        citation_keys.add(reference.citation_key)

    # Build the emitted-anchor index before validating inline references so
    # forward references are valid and every reference can be checked against
    # the exact target identity carried by the IR.
    anchor_by_label: dict[str, tuple[str, str]] = {}
    seen_section_ids: set[str] = set()
    for section_index, section in enumerate(document.sections):
        if not isinstance(section, SectionModel):
            continue
        if section.section_id:
            if section.section_id in seen_section_ids:
                raise DocumentModelError(
                    f"duplicate section_id in LaTeX IR: {section.section_id!r}"
                )
            seen_section_ids.add(section.section_id)
        if section.label is not None:
            _validate_ir_label(section.label, context=f"section {section_index}.label")
            if not section.section_id.strip():
                raise DocumentModelError(
                    f"section {section_index} cannot carry a label without section_id"
                )
            if section.label in anchor_by_label:
                raise DocumentModelError(
                    f"duplicate LaTeX anchor label: {section.label!r}"
                )
            anchor_by_label[section.label] = ("section", section.section_id)
        for block_index, block in enumerate(section.blocks):
            if isinstance(block, EquationBlock) and block.label is not None:
                _validate_ir_label(
                    block.label,
                    context=f"section {section_index}.blocks[{block_index}].label",
                )
                if block.label in anchor_by_label:
                    raise DocumentModelError(
                        f"duplicate LaTeX anchor label: {block.label!r}"
                    )
                anchor_by_label[block.label] = (
                    "equation_occurrence",
                    block.occurrence_id,
                )
            elif isinstance(block, FigureBlock):
                _validate_ir_label(
                    block.label, context=f"section {section_index}.blocks[{block_index}].label"
                )
                if block.label in anchor_by_label:
                    raise DocumentModelError(f"duplicate LaTeX anchor label: {block.label!r}")
                anchor_by_label[block.label] = ("figure", block.figure_id)
            elif isinstance(block, TableBlock):
                _validate_ir_label(
                    block.label, context=f"section {section_index}.blocks[{block_index}].label"
                )
                if block.label in anchor_by_label:
                    raise DocumentModelError(f"duplicate LaTeX anchor label: {block.label!r}")
                anchor_by_label[block.label] = ("table", block.table_id)

    for section_index, section in enumerate(document.sections):
        if not isinstance(section, SectionModel):
            raise DocumentModelError(f"section {section_index} must be a SectionModel")
        if not isinstance(section.title, str):
            raise DocumentModelError(f"section {section_index}.title must be a string")
        if not section.title.strip():
            raise DocumentModelError(
                f"section {section_index}.title must be a non-empty string"
            )
        if not isinstance(section.section_id, str):
            raise DocumentModelError(
                f"section {section_index}.section_id must be a string"
            )
        if section.label is not None:
            _validate_ir_label(section.label, context=f"section {section_index}.label")
        if not isinstance(section.blocks, tuple):
            raise DocumentModelError(f"section {section_index}.blocks must be a tuple")
        for block_index, block in enumerate(section.blocks):
            context = f"section {section_index}.blocks[{block_index}]"
            if not isinstance(
                block,
                (
                    TextBlock,
                    MathBlock,
                    CitationBlock,
                    LegacyLatexBlock,
                    ParagraphBlock,
                    EquationBlock,
                    FigureBlock,
                    TableBlock,
                ),
            ):
                raise DocumentModelError(f"{context} has an invalid block type")
            if isinstance(block, TextBlock):
                if not isinstance(block.text, str) or not block.text:
                    raise DocumentModelError(
                        f"{context}.text must be a non-empty string"
                    )
            elif isinstance(block, MathBlock):
                if not isinstance(block.expression, str) or not block.expression.strip():
                    raise DocumentModelError(
                        f"{context}.expression must be a non-empty string"
                    )
            elif isinstance(block, LegacyLatexBlock):
                if not isinstance(block.source, str) or not block.source:
                    raise DocumentModelError(
                        f"{context}.source must be a non-empty string"
                    )
            elif isinstance(block, CitationBlock):
                _validate_source_ids(
                    block.source_ids,
                    context=context,
                    reference_ids=reference_ids,
                )
            elif isinstance(block, ParagraphBlock):
                if not isinstance(block.content, tuple) or not block.content:
                    raise DocumentModelError(
                        f"{context}.content must be a non-empty tuple"
                    )
                for inline_index, inline in enumerate(block.content):
                    inline_context = f"{context}.content[{inline_index}]"
                    if isinstance(inline, IRTextSpan):
                        if not isinstance(inline.text, str) or not inline.text:
                            raise DocumentModelError(
                                f"{inline_context}.text must be non-empty"
                            )
                    elif isinstance(inline, IRMathSpan):
                        if (
                            not isinstance(inline.expression, str)
                            or not inline.expression.strip()
                        ):
                            raise DocumentModelError(
                                f"{inline_context}.expression must be non-empty"
                            )
                    elif isinstance(inline, IRCitationSpan):
                        if not isinstance(inline.occurrence_id, str):
                            raise DocumentModelError(
                                f"{inline_context}.occurrence_id must be a string"
                            )
                        _validate_source_ids(
                            inline.source_ids,
                            context=inline_context,
                            reference_ids=reference_ids,
                        )
                    elif isinstance(inline, IRCrossReferenceSpan):
                        for field_name in (
                            "target_id",
                            "target_type",
                            "label",
                            "occurrence_id",
                        ):
                            value = getattr(inline, field_name)
                            if not isinstance(value, str) or not value.strip():
                                raise DocumentModelError(
                                    f"{inline_context}.{field_name} must be a non-empty string"
                                )
                        _validate_ir_label(
                            inline.label, context=f"{inline_context}.label"
                        )
                        if inline.target_type not in {
                            "section",
                            "equation_occurrence",
                            "figure",
                            "table",
                        }:
                            raise DocumentModelError(
                                f"{inline_context}.target_type is unsupported: "
                                f"{inline.target_type!r}"
                            )
                        anchor = anchor_by_label.get(inline.label)
                        if anchor is None:
                            raise DocumentModelError(
                                f"{inline_context} references unresolved label "
                                f"{inline.label!r}"
                            )
                        if anchor != (inline.target_type, inline.target_id):
                            raise DocumentModelError(
                                f"{inline_context} label/target mismatch: "
                                f"label {inline.label!r} resolves to {anchor!r}, not "
                                f"{(inline.target_type, inline.target_id)!r}"
                            )
                    else:
                        raise DocumentModelError(
                            f"{inline_context} has an invalid inline type"
                        )
            elif isinstance(block, EquationBlock):
                if not isinstance(block.equation_id, str) or not block.equation_id.strip():
                    raise DocumentModelError(
                        f"{context}.equation_id must be non-empty"
                    )
                if not isinstance(block.expression, str) or not block.expression.strip():
                    raise DocumentModelError(
                        f"{context}.expression must be non-empty"
                    )
                if (
                    not isinstance(block.occurrence_id, str)
                    or not block.occurrence_id.strip()
                ):
                    raise DocumentModelError(
                        f"{context}.occurrence_id must be non-empty"
                    )
                if block.label is not None and not isinstance(block.label, str):
                    raise DocumentModelError(
                        f"{context}.label must be a string or None"
                    )
                if block.caption is not None and not isinstance(block.caption, str):
                    raise DocumentModelError(
                        f"{context}.caption must be a string or None"
                    )
            elif isinstance(block, FigureBlock):
                for field_name in ("figure_id", "asset", "caption", "label"):
                    value = getattr(block, field_name)
                    if not isinstance(value, str) or not value.strip():
                        raise DocumentModelError(f"{context}.{field_name} must be non-empty")
                _validate_ir_label(block.label, context=f"{context}.label")
                if not isinstance(block.source_ids, tuple):
                    raise DocumentModelError(f"{context}.source_ids must be a tuple")
                if block.source_ids:
                    _validate_source_ids(
                        block.source_ids, context=context, reference_ids=reference_ids
                    )
                try:
                    validate_figure_asset_path(block.asset)
                except AssetPathError as exc:
                    raise DocumentModelError(f"{context}.asset is unsafe: {exc}") from exc
            elif isinstance(block, TableBlock):
                for field_name in ("table_id", "caption", "label"):
                    value = getattr(block, field_name)
                    if not isinstance(value, str) or not value.strip():
                        raise DocumentModelError(f"{context}.{field_name} must be non-empty")
                _validate_ir_label(block.label, context=f"{context}.label")
                if not isinstance(block.source_ids, tuple):
                    raise DocumentModelError(f"{context}.source_ids must be a tuple")
                if block.source_ids:
                    _validate_source_ids(
                        block.source_ids, context=context, reference_ids=reference_ids
                    )
                if not isinstance(block.columns, tuple) or not block.columns:
                    raise DocumentModelError(f"{context}.columns must be a non-empty tuple")
                if any(not isinstance(column, str) or not column.strip() for column in block.columns):
                    raise DocumentModelError(f"{context}.columns must contain non-empty strings")
                if not isinstance(block.rows, tuple) or not block.rows:
                    raise DocumentModelError(f"{context}.rows must be a non-empty tuple")
                for row_index, row in enumerate(block.rows):
                    if not isinstance(row, tuple) or len(row) != len(block.columns):
                        raise DocumentModelError(
                            f"{context}.rows[{row_index}] must match column count {len(block.columns)}"
                        )
                    if any(not isinstance(cell, str) for cell in row):
                        raise DocumentModelError(f"{context}.rows[{row_index}] cells must be strings")


def build_document_model(
    state: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> DocumentModel:
    """Build and validate the renderer-neutral document model from legacy IR input."""

    if not isinstance(state, Mapping):
        raise DocumentModelError("state must be a mapping")
    document = DocumentModel(
        topic=_as_text(
            state.get("topic"),
            "topic",
            default="Finite Element Method Guideline",
        ),
        objective=_as_text(state.get("objective"), "objective"),
        sections=normalize_sections(sections),
        references=normalize_references(evidence),
    )
    validate_document_model(document)
    return document

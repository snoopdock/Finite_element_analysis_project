"""Semantic intermediate representation for generated scientific documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


class DocumentModelError(ValueError):
    """Raised when input cannot satisfy the document-model contract."""


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class MathBlock:
    expression: str


@dataclass(frozen=True)
class CitationBlock:
    """A citation referring to one or more normalized source identifiers."""

    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class LegacyLatexBlock:
    """Explicit compatibility block for already-authored LaTeX fragments."""

    source: str


DocumentBlock = TextBlock | MathBlock | CitationBlock | LegacyLatexBlock


@dataclass(frozen=True)
class SectionModel:
    title: str
    blocks: tuple[DocumentBlock, ...] = field(default_factory=tuple)


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


def normalize_sections(sections: Sequence[Mapping[str, Any]]) -> tuple[SectionModel, ...]:
    """Normalize the closed section input language without guessing semantics."""

    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)):
        raise DocumentModelError("sections must be a sequence")

    normalized: list[SectionModel] = []
    for index, section in enumerate(sections):
        if not isinstance(section, Mapping):
            raise DocumentModelError(f"section {index} must be a mapping")
        _require_keys(section, {"title", "blocks"}, f"section {index}")
        title = _as_text(section.get("title"), f"section {index}.title", default="Untitled").strip() or "Untitled"
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
                expression = _as_text(block.get("expression"), f"{context}.expression").strip()
                if not expression:
                    raise DocumentModelError(f"{context}.expression must not be empty")
                parsed.append(MathBlock(expression))
            elif kind == "citation":
                _require_keys(block, {"type", "source_ids"}, context)
                raw_ids = block.get("source_ids")
                if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes)):
                    raise DocumentModelError(f"{context}.source_ids must be a sequence")
                source_ids = tuple(_as_text(source_id, f"{context}.source_ids[{source_index}]").strip() for source_index, source_id in enumerate(raw_ids))
                if not source_ids or any(not source_id for source_id in source_ids):
                    raise DocumentModelError(f"{context}.source_ids must contain non-empty strings")
                if len(set(source_ids)) != len(source_ids):
                    raise DocumentModelError(f"{context}.source_ids must not contain duplicates")
                parsed.append(CitationBlock(source_ids))
            elif kind == "legacy_latex":
                _require_keys(block, {"type", "source"}, context)
                source = _as_text(block.get("source"), f"{context}.source")
                if not source:
                    raise DocumentModelError(f"{context}.source must not be empty")
                parsed.append(LegacyLatexBlock(source))
            else:
                raise DocumentModelError(f"unsupported block type {kind!r} in {context}")
        normalized.append(SectionModel(title=title, blocks=tuple(parsed)))
    return tuple(normalized)


def normalize_references(evidence: Sequence[Mapping[str, Any]]) -> tuple[ReferenceModel, ...]:
    """Convert retrieval receipts into renderer-neutral reference records."""

    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise DocumentModelError("evidence must be a sequence")

    references: list[ReferenceModel] = []
    seen_source_ids: set[str] = set()
    for index, source in enumerate(evidence[:25]):
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
        references.append(ReferenceModel(source_id=source_id, title=_as_text(source.get("title"), "title", default="Unknown Title"), url=_as_text(source.get("url"), "url"), source_type=_as_text(source.get("retriever_module"), "retriever_module", default="misc"), retrieved_at=_as_text(source.get("retrieved_at"), "retrieved_at", default="N/A"), citation_key=f"ref{index + 1}"))
    return tuple(references)


def validate_document_model(document: DocumentModel) -> None:
    """Validate structure, field types, and cross-reference integrity."""

    if not isinstance(document, DocumentModel):
        raise DocumentModelError("document must be a DocumentModel")
    if not isinstance(document.topic, str) or not isinstance(document.objective, str):
        raise DocumentModelError("document topic and objective must be strings")
    if not document.topic.strip() or not document.objective.strip():
        raise DocumentModelError("document topic and objective must be non-empty strings")
    if not isinstance(document.sections, tuple) or not isinstance(document.references, tuple):
        raise DocumentModelError("document sections and references must be tuples")

    reference_ids: set[str] = set()
    citation_keys: set[str] = set()
    for index, reference in enumerate(document.references):
        if not isinstance(reference, ReferenceModel):
            raise DocumentModelError(f"reference {index} must be a ReferenceModel")
        for field_name in ("source_id", "title", "url", "source_type", "retrieved_at", "citation_key"):
            if not isinstance(getattr(reference, field_name), str):
                raise DocumentModelError(f"reference {index}.{field_name} must be a string")
        if not reference.source_id.strip():
            raise DocumentModelError(f"reference {index}.source_id must not be empty")
        if reference.source_id in reference_ids:
            raise DocumentModelError(f"duplicate source_id in document: {reference.source_id!r}")
        reference_ids.add(reference.source_id)
        if not reference.citation_key.strip() or reference.citation_key in citation_keys:
            raise DocumentModelError(f"invalid or duplicate citation_key: {reference.citation_key!r}")
        citation_keys.add(reference.citation_key)

    for section_index, section in enumerate(document.sections):
        if not isinstance(section, SectionModel):
            raise DocumentModelError(f"section {section_index} must be a SectionModel")
        if not isinstance(section.title, str):
            raise DocumentModelError(f"section {section_index}.title must be a string")
        if not section.title.strip():
            raise DocumentModelError(f"section {section_index}.title must be a non-empty string")
        if not isinstance(section.blocks, tuple):
            raise DocumentModelError(f"section {section_index}.blocks must be a tuple")
        for block_index, block in enumerate(section.blocks):
            context = f"section {section_index}.blocks[{block_index}]"
            if not isinstance(block, (TextBlock, MathBlock, CitationBlock, LegacyLatexBlock)):
                raise DocumentModelError(f"{context} has an invalid block type")
            if isinstance(block, TextBlock):
                if not isinstance(block.text, str) or not block.text:
                    raise DocumentModelError(f"{context}.text must be a non-empty string")
            elif isinstance(block, MathBlock):
                if not isinstance(block.expression, str) or not block.expression.strip():
                    raise DocumentModelError(f"{context}.expression must be a non-empty string")
            elif isinstance(block, LegacyLatexBlock):
                if not isinstance(block.source, str) or not block.source:
                    raise DocumentModelError(f"{context}.source must be a non-empty string")
            else:
                if not isinstance(block.source_ids, tuple):
                    raise DocumentModelError(f"{context}.source_ids must be a tuple")
                if not block.source_ids or any(not isinstance(source_id, str) or not source_id.strip() for source_id in block.source_ids):
                    raise DocumentModelError(f"{context}.source_ids must contain non-empty strings")
                if len(set(block.source_ids)) != len(block.source_ids):
                    raise DocumentModelError(f"{context}.source_ids must not contain duplicates")
                missing = [source_id for source_id in block.source_ids if source_id not in reference_ids]
                if missing:
                    raise DocumentModelError(f"{context} references unknown source_id(s): {', '.join(missing)}")


def build_document_model(state: Mapping[str, Any], sections: Sequence[Mapping[str, Any]], evidence: Sequence[Mapping[str, Any]]) -> DocumentModel:
    """Build and validate the semantic document model consumed by a renderer."""

    document = DocumentModel(topic=_as_text(state.get("topic"), "topic", default="Finite Element Method Guideline"), objective=_as_text(state.get("objective"), "objective"), sections=normalize_sections(sections), references=normalize_references(evidence))
    validate_document_model(document)
    return document

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
    """Compatibility block for already-authored LaTeX fragments."""

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


def normalize_sections(sections: Sequence[Mapping[str, Any]]) -> tuple[SectionModel, ...]:
    """Normalize section dictionaries without guessing their semantics."""

    normalized: list[SectionModel] = []
    for index, section in enumerate(sections):
        if not isinstance(section, Mapping):
            raise DocumentModelError(f"section {index} must be a mapping")

        title = _as_text(section.get("title"), f"section {index}.title", default="Untitled").strip()
        if not title:
            title = "Untitled"

        raw_blocks = section.get("blocks")
        if raw_blocks is None:
            content = _as_text(section.get("content"), f"section {index}.content")
            blocks: tuple[DocumentBlock, ...] = (
                (LegacyLatexBlock(content),) if content.strip() else tuple()
            )
        else:
            if not isinstance(raw_blocks, Sequence) or isinstance(raw_blocks, (str, bytes)):
                raise DocumentModelError(f"section {index}.blocks must be a sequence")
            parsed: list[DocumentBlock] = []
            for block_index, block in enumerate(raw_blocks):
                if not isinstance(block, Mapping):
                    raise DocumentModelError(
                        f"section {index}.blocks[{block_index}] must be a mapping"
                    )
                kind = block.get("type")
                if kind == "text":
                    parsed.append(TextBlock(_as_text(block.get("text"), "text")))
                elif kind == "math":
                    expression = _as_text(block.get("expression"), "expression").strip()
                    if expression:
                        parsed.append(MathBlock(expression))
                elif kind == "citation":
                    raw_ids = block.get("source_ids")
                    if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes)):
                        raise DocumentModelError("citation source_ids must be a sequence")
                    source_ids = tuple(
                        _as_text(source_id, "citation source_id").strip()
                        for source_id in raw_ids
                    )
                    source_ids = tuple(source_id for source_id in source_ids if source_id)
                    if source_ids:
                        parsed.append(CitationBlock(source_ids))
                elif kind == "legacy_latex":
                    parsed.append(LegacyLatexBlock(_as_text(block.get("source"), "source")))
                else:
                    raise DocumentModelError(
                        f"unsupported block type {kind!r} in section {index}.blocks[{block_index}]"
                    )
            blocks = tuple(parsed)

        normalized.append(SectionModel(title=title, blocks=blocks))

    return tuple(normalized)


def normalize_references(evidence: Sequence[Mapping[str, Any]]) -> tuple[ReferenceModel, ...]:
    """Convert retrieval receipts into renderer-neutral reference records."""

    references: list[ReferenceModel] = []
    seen_source_ids: set[str] = set()
    for index, source in enumerate(evidence[:25]):
        if not isinstance(source, Mapping):
            raise DocumentModelError(f"evidence {index} must be a mapping")
        source_id = _as_text(source.get("source_id"), "source_id", default="unknown").strip()
        if source_id in seen_source_ids:
            raise DocumentModelError(f"duplicate source_id in evidence: {source_id!r}")
        seen_source_ids.add(source_id)
        references.append(
            ReferenceModel(
                source_id=source_id,
                title=_as_text(source.get("title"), "title", default="Unknown Title"),
                url=_as_text(source.get("url"), "url"),
                source_type=_as_text(source.get("retriever_module"), "retriever_module", default="misc"),
                retrieved_at=_as_text(source.get("retrieved_at"), "retrieved_at", default="N/A"),
                citation_key=f"ref{index + 1}",
            )
        )
    return tuple(references)


def build_document_model(
    state: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> DocumentModel:
    """Build the semantic document model consumed by a renderer."""

    return DocumentModel(
        topic=_as_text(state.get("topic"), "topic", default="Finite Element Method Guideline"),
        objective=_as_text(state.get("objective"), "objective"),
        sections=normalize_sections(sections),
        references=normalize_references(evidence),
    )

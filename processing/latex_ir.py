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

    normalized: list[SectionModel] = []
    for index, section in enumerate(sections):
        if not isinstance(section, Mapping):
            raise DocumentModelError(f"section {index} must be a mapping")
        _require_keys(section, {"title", "blocks"}, f"section {index}")

        title = _as_text(
            section.get("title"), f"section {index}.title", default="Untitled"
        ).strip()
        if not title:
            title = "Untitled"
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
                    raise DocumentModelError(f"{context}.expression must not be empty")
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

    references: list[ReferenceModel] = []
    seen_source_ids: set[str] = set()
    for index, source in enumerate(evidence[:25]):
        if not isinstance(source, Mapping):
            raise DocumentModelError(f"evidence {index} must be a mapping")
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
                    source.get("retriever_module"), "retriever_module", default="misc"
                ),
                retrieved_at=_as_text(
                    source.get("retrieved_at"), "retrieved_at", default="N/A"
                ),
                citation_key=f"ref{index + 1}",
            )
        )
    return tuple(references)


def validate_document_model(document: DocumentModel) -> None:
    """Ensure every semantic citation resolves to a normalized reference."""

    reference_ids = {reference.source_id for reference in document.references}
    for section_index, section in enumerate(document.sections):
        for block_index, block in enumerate(section.blocks):
            if not isinstance(block, CitationBlock):
                continue
            missing = [
                source_id
                for source_id in block.source_ids
                if source_id not in reference_ids
            ]
            if missing:
                missing_ids = ", ".join(missing)
                raise DocumentModelError(
                    f"section {section_index}.blocks[{block_index}] "
                    f"references unknown source_id(s): {missing_ids}"
                )


def build_document_model(
    state: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> DocumentModel:
    """Build and validate the semantic document model consumed by a renderer."""

    document = DocumentModel(
        topic=_as_text(
            state.get("topic"), "topic", default="Finite Element Method Guideline"
        ),
        objective=_as_text(state.get("objective"), "objective"),
        sections=normalize_sections(sections),
        references=normalize_references(evidence),
    )
    validate_document_model(document)
    return document

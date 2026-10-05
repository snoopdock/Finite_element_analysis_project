"""Deterministic registry from semantic document object identity to LaTeX labels.

L17-L requires internal document links to originate from semantic object identity,
not from manually-authored LaTeX labels or textual replacement.  This module is
therefore a publication boundary: it observes document object IDs and generates
stable, label-safe LaTeX representations without changing semantic identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable

from core.document_model import Document, EquationOccurrence, Figure, Table


class LabelRegistryError(ValueError):
    """Raised when document object identity cannot form an unambiguous registry."""


_LABEL_SAFE_ID_RE = re.compile(r"[A-Za-z0-9._/-]+")
_LABEL_SAFE_RE = re.compile(r"[A-Za-z0-9:._/-]+")


@dataclass(frozen=True)
class LabelRecord:
    """One deterministic publication label for a semantic document target."""

    target_id: str
    target_type: str
    latex_label: str


class LabelRegistry:
    """Immutable target/label registry with strict one-to-one identity mapping."""

    def __init__(self, records: Iterable[LabelRecord]):
        materialized = tuple(records)
        by_target: dict[str, LabelRecord] = {}
        by_label: dict[str, LabelRecord] = {}
        for record in materialized:
            if not isinstance(record, LabelRecord):
                raise LabelRegistryError("registry records must be LabelRecord instances")
            if not record.target_id.strip():
                raise LabelRegistryError("label target_id must be non-empty")
            if not record.target_type.strip():
                raise LabelRegistryError("label target_type must be non-empty")
            if not _LABEL_SAFE_RE.fullmatch(record.latex_label):
                raise LabelRegistryError(
                    f"generated LaTeX label is not label-safe: {record.latex_label!r}"
                )
            if record.target_id in by_target:
                other = by_target[record.target_id]
                raise LabelRegistryError(
                    "duplicate document target_id is ambiguous: "
                    f"{record.target_id!r} ({other.target_type}, {record.target_type})"
                )
            if record.latex_label in by_label:
                other = by_label[record.latex_label]
                raise LabelRegistryError(
                    "duplicate generated LaTeX label: "
                    f"{record.latex_label!r} for {other.target_id!r} and {record.target_id!r}"
                )
            by_target[record.target_id] = record
            by_label[record.latex_label] = record

        self._records = materialized
        self._by_target = by_target
        self._by_label = by_label

    @property
    def records(self) -> tuple[LabelRecord, ...]:
        return self._records

    @property
    def target_ids(self) -> frozenset[str]:
        return frozenset(self._by_target)

    @property
    def labels(self) -> frozenset[str]:
        return frozenset(self._by_label)

    def resolve(self, target_id: str) -> LabelRecord:
        if not isinstance(target_id, str) or not target_id.strip():
            raise LabelRegistryError("reference target_id must be a non-empty string")
        try:
            return self._by_target[target_id]
        except KeyError as exc:
            raise LabelRegistryError(
                f"unresolved internal document target_id: {target_id!r}"
            ) from exc


def _label_token(target_id: str) -> str:
    """Return a deterministic label token without trusting arbitrary object text."""
    if _LABEL_SAFE_ID_RE.fullmatch(target_id) and len(target_id) <= 96:
        return target_id
    digest = hashlib.sha256(target_id.encode("utf-8")).hexdigest()
    return f"sha256-{digest}"


def _make_label(target_type: str, target_id: str) -> str:
    prefixes = {
        "section": "sec",
        "equation_occurrence": "eq",
        "figure": "fig",
        "table": "tab",
    }
    try:
        prefix = prefixes[target_type]
    except KeyError as exc:
        raise LabelRegistryError(
            f"unsupported label target type: {target_type!r}"
        ) from exc
    return f"{prefix}:{_label_token(target_id)}"


def build_label_registry(document: Document) -> LabelRegistry:
    """Build labels deterministically from semantic document object identity.

    Target IDs are required to be globally unambiguous because
    ``CrossReferenceOccurrence`` intentionally carries only ``target_id``.
    Figure/table identities use the same registry as sections and equation
    occurrences. Their publication projections consume these generated labels
    without introducing a second identity system.
    """
    if not isinstance(document, Document):
        raise LabelRegistryError("document must be a semantic Document")
    document.validate()

    records: list[LabelRecord] = []
    for section in document.children:
        section_id = section.section_id or ""
        records.append(
            LabelRecord(
                target_id=section_id,
                target_type="section",
                latex_label=_make_label("section", section_id),
            )
        )
        for child in section.children:
            if isinstance(child, EquationOccurrence):
                records.append(
                    LabelRecord(
                        target_id=child.occurrence_id,
                        target_type="equation_occurrence",
                        latex_label=_make_label(
                            "equation_occurrence", child.occurrence_id
                        ),
                    )
                )
            elif isinstance(child, Figure):
                records.append(
                    LabelRecord(
                        target_id=child.figure_id,
                        target_type="figure",
                        latex_label=_make_label("figure", child.figure_id),
                    )
                )
            elif isinstance(child, Table):
                records.append(
                    LabelRecord(
                        target_id=child.table_id,
                        target_type="table",
                        latex_label=_make_label("table", child.table_id),
                    )
                )

    return LabelRegistry(records)

"""Strict resolution of semantic cross-reference occurrences through a label registry."""

from __future__ import annotations

from dataclasses import dataclass

from core.document_model import CrossReferenceOccurrence
from processing.label_registry import LabelRegistry, LabelRegistryError


class ReferenceResolutionError(ValueError):
    """Raised when an internal document reference cannot resolve exactly once."""


@dataclass(frozen=True)
class ResolvedReference:
    occurrence_id: str
    target_id: str
    target_type: str
    latex_label: str


class ReferenceResolver:
    """Resolve cross-reference occurrences without text matching or guessing."""

    def __init__(self, registry: LabelRegistry):
        if not isinstance(registry, LabelRegistry):
            raise ReferenceResolutionError("registry must be a LabelRegistry")
        self._registry = registry

    def resolve(self, occurrence: CrossReferenceOccurrence) -> ResolvedReference:
        if not isinstance(occurrence, CrossReferenceOccurrence):
            raise ReferenceResolutionError(
                "reference resolver requires a CrossReferenceOccurrence"
            )
        occurrence.validate()
        try:
            record = self._registry.resolve(occurrence.target_id)
        except LabelRegistryError as exc:
            raise ReferenceResolutionError(str(exc)) from exc
        return ResolvedReference(
            occurrence_id=occurrence.occurrence_id,
            target_id=record.target_id,
            target_type=record.target_type,
            latex_label=record.latex_label,
        )

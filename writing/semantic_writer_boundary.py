#!/usr/bin/env python3
"""Explicit boundary from legacy writer output to semantic document structure.

This module does not change DynamicWriter. It provides a narrow integration
point that callers can apply to a completed writer section while the legacy
section dictionary remains the compatibility surface.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional, Set

from core.document_model import DocumentModelError
from writing.section_document_adapter import legacy_section_to_document_section


SEMANTIC_SECTION_KEY = "document_section"


def attach_semantic_section(
    section: Dict[str, Any],
    *,
    equation_ids: Optional[Set[str]] = None,
    source_ids: Optional[Set[str]] = None,
    target_ids: Optional[Set[str]] = None,
    proposal_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Return a legacy writer section with a semantic shadow projection.

    The input dictionary is not mutated. The returned ``document_section`` is
    the serialized semantic model and is authoritative only for document
    organization; legacy ``content``, ``key_equations`` and ``citations_used``
    remain compatibility projections.

    Sections without explicit semantic markers become opaque prose. When
    markers are present, strict identifier resolution is applied by the
    underlying section-document adapter.
    """
    if not isinstance(section, dict):
        raise DocumentModelError("Writer section must be a dictionary.")

    projected = deepcopy(section)
    semantic_section = legacy_section_to_document_section(
        projected,
        equation_ids=equation_ids,
        source_ids=source_ids,
        target_ids=target_ids,
        proposal_ids=proposal_ids,
    )
    projected[SEMANTIC_SECTION_KEY] = semantic_section.to_dict()
    return projected


def get_semantic_section(section: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return an attached semantic section, if present."""
    if not isinstance(section, dict):
        raise DocumentModelError("Writer section must be a dictionary.")
    value = section.get(SEMANTIC_SECTION_KEY)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DocumentModelError(
            f"{SEMANTIC_SECTION_KEY} must be a dictionary when present."
        )
    return value

#!/usr/bin/env python3
"""Deterministic validation for generated academic writing."""

from __future__ import annotations

import json
import re
from typing import Dict, Optional


class WritingValidationError(ValueError):
    """Raised when generated writing fails structural validation."""


def validate_paragraph(
    text: str,
    *,
    min_words: int = 20,
    max_words: Optional[int] = None,
) -> Dict:
    """Validate one generated paragraph without making semantic claims."""
    if not isinstance(text, str):
        raise WritingValidationError("Paragraph must be a string.")

    normalized = re.sub(
        r"\s+",
        " ",
        text.strip(),
    )

    if not normalized:
        raise WritingValidationError("Paragraph is empty.")

    word_count = len(normalized.split())

    if word_count < min_words:
        raise WritingValidationError(
            f"Paragraph contains only {word_count} words; "
            f"minimum is {min_words}."
        )

    if max_words is not None and word_count > max_words:
        raise WritingValidationError(
            f"Paragraph contains {word_count} words; "
            f"maximum is {max_words}."
        )

    # Reject obvious structured-output leakage.
    stripped = normalized.strip()

    if stripped.startswith("```"):
        raise WritingValidationError(
            "Markdown code fencing detected in paragraph output."
        )

    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
        except json.JSONDecodeError:
            pass
        else:
            raise WritingValidationError(
                "JSON object/list returned where prose was expected."
            )

    if re.search(
        r"(?i)^(?:title|heading|paragraph|answer)\s*:",
        stripped,
    ):
        raise WritingValidationError(
            "Generated output contains a meta heading."
        )

    # Control characters are almost always an indication of malformed output.
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", normalized):
        raise WritingValidationError(
            "Generated output contains control characters."
        )

    return {
        "valid": True,
        "word_count": word_count,
        "text": normalized,
    }


def validate_section_structure(
    section: Dict,
    *,
    min_words: int = 100,
) -> Dict:
    """Validate the structural fields of a generated section."""
    if not isinstance(section, dict):
        raise WritingValidationError(
            "Section must be a dictionary."
        )

    title = section.get("title")
    content = section.get("content")

    if not isinstance(title, str) or not title.strip():
        raise WritingValidationError(
            "Section title is missing."
        )

    if not isinstance(content, str):
        raise WritingValidationError(
            "Section content must be a string."
        )

    word_count = len(
        content.split()
    )

    if word_count < min_words:
        raise WritingValidationError(
            f"Section contains only {word_count} words; "
            f"minimum is {min_words}."
        )

    return {
        "valid": True,
        "word_count": word_count,
        "title": title.strip(),
    }

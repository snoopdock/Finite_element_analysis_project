#!/usr/bin/env python3
"""Deterministic recognition of legacy source-ID citation syntax.

This module owns syntax recognition only. Evidence/source identity remains
external authority. Exact parenthesized source-ID groups may be canonicalized
into the legacy bracket form so the existing semantic citation migration can
promote them without guessing or changing scientific prose.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Iterator


# IMPORTANT: this regex is used only when no evidence registry is available
# (notably at the final generated-LaTeX gate). It therefore must be deliberately
# conservative. Generic underscore identifiers such as u_h and v_h are normal
# finite-element notation and must never be inferred to be citations merely
# because they contain an underscore.
SOURCE_TOKEN_RE = re.compile(
    r"(?:arxiv|wiki|wikipedia|s2|doi|pmid|book|source)(?:_|:)[A-Za-z0-9_.:/-]+",
    flags=re.IGNORECASE,
)
_BRACKET_GROUP_RE = re.compile(r"\[(?P<body>[^\[\]]+)\]")
_PAREN_GROUP_RE = re.compile(r"\((?P<body>[^()]+)\)")


@dataclass(frozen=True)
class RawCitationGroup:
    raw: str
    source_ids: tuple[str, ...]
    delimiter: str
    registry_related: bool
    source_shaped: bool


def _tokens(body: str, *, latex_escaped: bool) -> tuple[str, ...]:
    if latex_escaped:
        body = body.replace(r"\_", "_")
    return tuple(part.strip() for part in body.split(","))


def iter_raw_citation_groups(
    text: str,
    *,
    known_source_ids: Iterable[str] | None = None,
    latex_escaped: bool = False,
) -> Iterator[RawCitationGroup]:
    """Yield bracketed/parenthesized groups that look like leaked source IDs.

    With an evidence registry, any group containing at least one exact known
    source ID is considered registry-related so partially malformed groups fail
    closed. Without a registry (the final LaTeX-source gate), recognition is
    intentionally limited to explicit source namespaces (wiki_, doi:, arxiv_,
    etc.). This avoids false positives on scientific notation such as (u_h,v_h).
    """
    known = {str(source_id) for source_id in (known_source_ids or ()) if source_id}
    for delimiter, pattern in (("bracket", _BRACKET_GROUP_RE), ("parenthesis", _PAREN_GROUP_RE)):
        for match in pattern.finditer(str(text)):
            tokens = _tokens(match.group("body"), latex_escaped=latex_escaped)
            if not tokens or any(not token for token in tokens):
                continue
            source_shaped = all(SOURCE_TOKEN_RE.fullmatch(token) for token in tokens)
            registry_related = any(token in known for token in tokens)
            if source_shaped or registry_related:
                yield RawCitationGroup(
                    raw=match.group(0),
                    source_ids=tokens,
                    delimiter=delimiter,
                    registry_related=registry_related,
                    source_shaped=source_shaped,
                )


def normalize_parenthesized_known_citations(
    text: str,
    *,
    known_source_ids: Iterable[str],
) -> tuple[str, tuple[str, ...]]:
    """Canonicalize exact known ``(source_id[, ...])`` groups to brackets.

    The transformation is deliberately narrow: every token must be a distinct
    exact member of the supplied evidence registry. Unknown, mixed, malformed,
    or explanatory parenthetical text is left untouched for later fail-closed
    validation. Scientific prose outside the citation delimiters is unchanged.
    """
    known = {str(source_id) for source_id in known_source_ids if source_id}
    diagnostics: list[str] = []

    def replace(match: re.Match[str]) -> str:
        raw_body = match.group("body")
        source_ids = tuple(part.strip() for part in raw_body.split(","))
        if (
            source_ids
            and all(source_ids)
            and len(set(source_ids)) == len(source_ids)
            and all(source_id in known for source_id in source_ids)
        ):
            canonical = "[" + ", ".join(source_ids) + "]"
            diagnostics.append(
                "parenthesized_citation_normalized:" + ",".join(source_ids)
            )
            return canonical
        return match.group(0)

    return _PAREN_GROUP_RE.sub(replace, str(text)), tuple(diagnostics)

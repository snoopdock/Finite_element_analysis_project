"""Epistemic assurance contracts for the graph-native audit engine.

This package defines immutable descriptive records only. It has no persistence,
inference, network, solver, or decision-gate side effects.
"""

from .contracts import (
    AssertionPolarity,
    CompletenessClaim,
    CompletenessStatus,
    EvidenceAssertion,
    EvidenceRef,
    GapKind,
    GapState,
    KnowledgeGap,
)

__all__ = [
    "AssertionPolarity",
    "CompletenessClaim",
    "CompletenessStatus",
    "EvidenceAssertion",
    "EvidenceRef",
    "GapKind",
    "GapState",
    "KnowledgeGap",
]

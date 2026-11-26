"""Epistemic assurance contracts for the graph-native audit engine.

This package defines immutable descriptive records only. It has no persistence,
inference, network, solver, or decision-gate side effects.
"""

from .store import (\n    DuplicateRecordError, EpistemicStore, InvalidTransitionError,\n    RevisionConflictError, StorageLimitError, StoreError,\n)\n\nfrom .contracts import (
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
    "DuplicateRecordError",\n    "EpistemicStore",\n    "InvalidTransitionError",\n    "RevisionConflictError",\n    "StorageLimitError",\n    "StoreError",\n    "AssertionPolarity",
    "CompletenessClaim",
    "CompletenessStatus",
    "EvidenceAssertion",
    "EvidenceRef",
    "GapKind",
    "GapState",
    "KnowledgeGap",
]

"""Epistemic assurance contracts for the graph-native audit engine.

The package contains immutable descriptive records and an explicit append-only store.
It does not infer proposition truth or authorize audit decisions.
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
from .evaluation import AdmissibilityDecision, NegativeClaimRequest, evaluate_negative_claim
from .store import (
    DuplicateRecordError,
    EpistemicStore,
    InvalidTransitionError,
    RevisionConflictError,
    StorageLimitError,
    StoreError,
)

__all__ = [
    "AdmissibilityDecision",
    "AssertionPolarity",
    "CompletenessClaim",
    "CompletenessStatus",
    "DuplicateRecordError",
    "EpistemicStore",
    "EvidenceAssertion",
    "EvidenceRef",
    "GapKind",
    "GapState",
    "InvalidTransitionError",
    "KnowledgeGap",
    "NegativeClaimRequest",
    "RevisionConflictError",
    "StorageLimitError",
    "StoreError",
    "evaluate_negative_claim",
]

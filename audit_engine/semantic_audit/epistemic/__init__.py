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
    FreshnessResult,
    FreshnessStatus,
    ProvenanceDependency,
    ProvenanceInvalidation,
    ProvenanceManifest,
    GapKind,
    GapState,
    KnowledgeGap,
)
from .evaluation import (
    AdmissibilityDecision, NegativeClaimRequest, evaluate_negative_claim,
    evaluate_negative_claim_with_freshness,
)
from .assurance import (
    AssuranceClaim, AssuranceContractError, ArgumentAssessment, ArgumentLink,
    ArgumentRelation, Defeater, DefeaterAction, DefeaterEvent, DefeaterKind,
    evaluate_assurance,
)
from .assurance_store import (
    AssuranceDuplicateError, AssuranceStorageLimitError, AssuranceStore,
    AssuranceStoreError,
)
from .coverage import (
    CoverageContractError, CoverageObligation, ObligationDisposition,
    EpistemicCoverageManifest, EpistemicCoverageStatus,
    EpistemicCoverageResult, evaluate_epistemic_coverage,
)
from .rule_coverage import (
    RuleCoverageDerivationError, RuleCoveragePlan,
    derive_rule_coverage_plan, build_rule_derived_coverage_manifest,
    verify_rule_derived_manifest,
)
from .persisted_assurance import (
    PersistedAssuranceResult,
    evaluate_persisted_assurance,
)
from .store import (
    DuplicateRecordError,
    EpistemicStore,
    InvalidTransitionError,
    RevisionConflictError,
    StorageLimitError,
    StoreError,
)

__all__ = [
    "RuleCoverageDerivationError",
    "RuleCoveragePlan",
    "derive_rule_coverage_plan",
    "build_rule_derived_coverage_manifest",
    "verify_rule_derived_manifest",

    "CoverageContractError",
    "CoverageObligation",
    "ObligationDisposition",
    "EpistemicCoverageManifest",
    "EpistemicCoverageStatus",
    "EpistemicCoverageResult",
    "evaluate_epistemic_coverage",

    "PersistedAssuranceResult",
    "evaluate_persisted_assurance",
    "AdmissibilityDecision",
    "AssuranceClaim",
    "AssuranceContractError",
    "AssuranceDuplicateError",
    "AssuranceStorageLimitError",
    "AssuranceStore",
    "AssuranceStoreError",
    "ArgumentAssessment",
    "ArgumentLink",
    "ArgumentRelation",
    "Defeater",
    "DefeaterAction",
    "DefeaterEvent",
    "DefeaterKind",
    "AssertionPolarity",
    "CompletenessClaim",
    "CompletenessStatus",
    "DuplicateRecordError",
    "EpistemicStore",
    "EvidenceAssertion",
    "EvidenceRef",
    "FreshnessResult",
    "FreshnessStatus",
    "ProvenanceDependency",
    "ProvenanceInvalidation",
    "ProvenanceManifest",
    "GapKind",
    "GapState",
    "InvalidTransitionError",
    "KnowledgeGap",
    "NegativeClaimRequest",
    "RevisionConflictError",
    "StorageLimitError",
    "StoreError",
    "evaluate_assurance",
    "evaluate_negative_claim",
    "evaluate_negative_claim_with_freshness",
]

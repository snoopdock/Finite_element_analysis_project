"""Epistemic assurance contracts for the graph-native audit engine.

The package contains immutable descriptive records and an explicit append-only store.
It does not infer proposition truth or authorize audit decisions.
"""

from .contracts import (
    AssertionPolarity, CompletenessClaim, CompletenessStatus, EvidenceAssertion,
    EvidenceRef, FreshnessResult, FreshnessStatus, ProvenanceDependency,
    ProvenanceInvalidation, ProvenanceManifest, GapKind, GapState, KnowledgeGap,
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
    RuleCoverageDerivationError, RuleCoveragePlan, derive_rule_coverage_plan,
    build_rule_derived_coverage_manifest, verify_rule_derived_manifest,
)
from .coverage_dossier import (
    CoverageDossier, CoverageDossierError, CoverageDossierStore,
    build_and_persist_coverage_dossier, verify_dossier_against_current_stores,
)
from .dossier_verification import verify_coverage_dossier_replay
from .source_inventory import (
    SourceExtractorInventoryError, extractor_candidate_registry,
    build_source_extractor_inventory, verify_source_extractor_inventory,
)
from .extractor_execution import (
    ExtractorExecutionError, extractor_executor_registry,
    build_extractor_execution_report, verify_extractor_execution_report,
)
from .execution_obligation_reconciliation import (
    ExecutionObligationReconciliationError, ExecutionObligationReconciliationStore,
    build_execution_obligation_reconciliation,
    build_and_persist_execution_obligation_reconciliation,
    verify_execution_obligation_reconciliation,
)
from .typed_evidence import (
    TypedEvidenceError, TypedEvidenceObservationStore,
    derive_typed_evidence_observations,
    verify_typed_evidence_observation_bundle,
    build_and_persist_typed_evidence_observations,
)
from .semantic_qualification import (
    SemanticQualificationError, semantic_evidence_contract_registry,
    qualify_typed_evidence_observations, verify_semantic_evidence_qualification,
)
from .persisted_assurance import PersistedAssuranceResult, evaluate_persisted_assurance
from .qualification_reconciliation import (
    QualificationReconciliationError, qualification_aggregation_policy_registry,
    reconcile_semantic_qualifications, verify_qualification_obligation_reconciliation,
)
from .qualification_reconciliation_store import (
    QualificationReconciliationStore, QualificationReconciliationStoreError,
    persist_verified_qualification_reconciliation,
    qualification_reconciliation_context,
    verify_persisted_qualification_reconciliation,
    evaluate_persisted_qualification_reconciliation_currentness,
)
from .qualification_consumer_gate import (
    QualificationConsumerCheckStore, QualificationConsumerGateError,
    evaluate_qualification_reconciliation_for_consumer,
)
from .store import (
    DuplicateRecordError, EpistemicStore, InvalidTransitionError,
    RevisionConflictError, StorageLimitError, StoreError,
)

__all__ = [
    "QualificationReconciliationError", "qualification_aggregation_policy_registry",
    "reconcile_semantic_qualifications", "verify_qualification_obligation_reconciliation",
    "QualificationReconciliationStore", "QualificationReconciliationStoreError",
    "persist_verified_qualification_reconciliation",
    "qualification_reconciliation_context",
    "verify_persisted_qualification_reconciliation",
    "evaluate_persisted_qualification_reconciliation_currentness",
    "QualificationConsumerCheckStore", "QualificationConsumerGateError",
    "evaluate_qualification_reconciliation_for_consumer",
    "SemanticQualificationError", "semantic_evidence_contract_registry",
    "qualify_typed_evidence_observations", "verify_semantic_evidence_qualification",
    "TypedEvidenceError", "TypedEvidenceObservationStore",
    "derive_typed_evidence_observations",
    "verify_typed_evidence_observation_bundle",
    "build_and_persist_typed_evidence_observations",
    "ExecutionObligationReconciliationError", "ExecutionObligationReconciliationStore",
    "build_execution_obligation_reconciliation",
    "build_and_persist_execution_obligation_reconciliation",
    "verify_execution_obligation_reconciliation",
    "CoverageDossier", "CoverageDossierError", "CoverageDossierStore",
    "build_and_persist_coverage_dossier", "verify_dossier_against_current_stores",
    "verify_coverage_dossier_replay",
    "SourceExtractorInventoryError", "extractor_candidate_registry",
    "build_source_extractor_inventory", "verify_source_extractor_inventory",
    "ExtractorExecutionError", "extractor_executor_registry",
    "build_extractor_execution_report", "verify_extractor_execution_report",
    "RuleCoverageDerivationError", "RuleCoveragePlan", "derive_rule_coverage_plan",
    "build_rule_derived_coverage_manifest", "verify_rule_derived_manifest",
    "CoverageContractError", "CoverageObligation", "ObligationDisposition",
    "EpistemicCoverageManifest", "EpistemicCoverageStatus",
    "EpistemicCoverageResult", "evaluate_epistemic_coverage",
    "PersistedAssuranceResult", "evaluate_persisted_assurance",
    "AdmissibilityDecision", "AssuranceClaim", "AssuranceContractError",
    "AssuranceDuplicateError", "AssuranceStorageLimitError", "AssuranceStore",
    "AssuranceStoreError", "ArgumentAssessment", "ArgumentLink",
    "ArgumentRelation", "Defeater", "DefeaterAction", "DefeaterEvent",
    "DefeaterKind", "AssertionPolarity", "CompletenessClaim", "CompletenessStatus",
    "DuplicateRecordError", "EpistemicStore", "EvidenceAssertion", "EvidenceRef",
    "FreshnessResult", "FreshnessStatus", "ProvenanceDependency",
    "ProvenanceInvalidation", "ProvenanceManifest", "GapKind", "GapState",
    "InvalidTransitionError", "KnowledgeGap", "NegativeClaimRequest",
    "RevisionConflictError", "StorageLimitError", "StoreError",
    "evaluate_assurance", "evaluate_negative_claim",
    "evaluate_negative_claim_with_freshness",
]

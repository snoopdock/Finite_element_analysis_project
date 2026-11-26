"""Immutable epistemic assurance value objects.

These contracts preserve evidence and scope metadata. They deliberately do not
select a universal truth calculus or make audit/authorization decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """A record violates the local epistemic contract."""


class AssertionPolarity(str, Enum):
    SUPPORTS = "supports"
    CHALLENGES = "challenges"
    NEUTRAL = "neutral"


class GapKind(str, Enum):
    SOURCE_NOT_SUPPLIED = "source_not_supplied"
    SOURCE_UNAVAILABLE = "source_unavailable"
    COLLECTION_NOT_ATTEMPTED = "collection_not_attempted"
    COLLECTION_FAILED = "collection_failed"
    UNSUPPORTED_SOURCE = "unsupported_source"
    PARTIAL_EXTRACTION = "partial_extraction"
    SCOPE_EXCLUDED = "scope_excluded"
    RESOURCE_LIMIT = "resource_limit"
    STALE_EVIDENCE = "stale_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    INDEPENDENCE_NOT_ESTABLISHED = "independence_not_established"
    UNKNOWN_CAUSE = "unknown_cause"
    OTHER = "other"


class GapState(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    ACCEPTED_RESIDUAL = "accepted_residual"


class CompletenessStatus(str, Enum):
    NOT_ASSESSED = "not_assessed"
    SUPPORTED_WITHIN_SCOPE = "supported_within_scope"
    PARTIAL = "partial"
    NOT_SUPPORTED = "not_supported"
    INVALIDATED = "invalidated"


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return None
    return _required(value, field)


def _unique_texts(values: Tuple[str, ...], field: str) -> Tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ContractError(f"{field} must be an immutable tuple")
    normalized = tuple(_required(value, field) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ContractError(f"{field} must not contain duplicates")
    return normalized


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_snapshot_id: str
    producer_id: str
    method_id: str
    observed_at: str
    artifact_sha256: Optional[str] = None
    source_uri: Optional[str] = None
    independence_group: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("evidence_id", "source_snapshot_id", "producer_id", "method_id", "observed_at"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        for name in ("source_uri", "independence_group"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        if self.artifact_sha256 is not None and (
            not isinstance(self.artifact_sha256, str)
            or not _SHA256_RE.fullmatch(self.artifact_sha256)
        ):
            raise ContractError("artifact_sha256 must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True)
class EvidenceAssertion:
    assertion_id: str
    proposition_id: str
    polarity: AssertionPolarity
    evidence_refs: Tuple[EvidenceRef, ...]
    scope_id: str
    method_id: str
    observed_at: str
    limitations: Tuple[str, ...] = ()
    invalidation_triggers: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("assertion_id", "proposition_id", "scope_id", "method_id", "observed_at"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if not isinstance(self.polarity, AssertionPolarity):
            raise ContractError("polarity must be an AssertionPolarity")
        if not isinstance(self.evidence_refs, tuple) or not self.evidence_refs:
            raise ContractError("evidence_refs must be a non-empty immutable tuple")
        if any(not isinstance(ref, EvidenceRef) for ref in self.evidence_refs):
            raise ContractError("every evidence_refs item must be an EvidenceRef")
        evidence_ids = tuple(ref.evidence_id for ref in self.evidence_refs)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ContractError("evidence_refs must not repeat evidence_id values")
        object.__setattr__(self, "limitations", _unique_texts(self.limitations, "limitations"))
        object.__setattr__(self, "invalidation_triggers", _unique_texts(self.invalidation_triggers, "invalidation_triggers"))


@dataclass(frozen=True)
class KnowledgeGap:
    gap_id: str
    subject_id: str
    kind: GapKind
    state: GapState
    scope_id: str
    discovery_method: str
    impact: str
    reason_detail: Optional[str] = None
    source_snapshot_id: Optional[str] = None
    evidence_refs: Tuple[EvidenceRef, ...] = ()
    resolution_evidence_refs: Tuple[EvidenceRef, ...] = ()
    disposition: Optional[str] = None
    authorized_by: Optional[str] = None
    reassessment_triggers: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("gap_id", "subject_id", "scope_id", "discovery_method", "impact"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if not isinstance(self.kind, GapKind) or not isinstance(self.state, GapState):
            raise ContractError("kind and state must use their declared enums")
        for name in ("reason_detail", "source_snapshot_id", "disposition", "authorized_by"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        for name in ("evidence_refs", "resolution_evidence_refs"):
            refs = getattr(self, name)
            if not isinstance(refs, tuple) or any(not isinstance(ref, EvidenceRef) for ref in refs):
                raise ContractError(f"{name} must be a tuple of EvidenceRef values")
            ids = tuple(ref.evidence_id for ref in refs)
            if len(set(ids)) != len(ids):
                raise ContractError(f"{name} must not contain duplicate evidence IDs")
        if self.state is GapState.RESOLVED and not self.resolution_evidence_refs:
            raise ContractError("a resolved gap requires resolution_evidence_refs")
        if self.state is GapState.ACCEPTED_RESIDUAL and (not self.disposition or not self.authorized_by):
            raise ContractError("an accepted residual gap requires disposition and authorized_by")
        object.__setattr__(self, "reassessment_triggers", _unique_texts(self.reassessment_triggers, "reassessment_triggers"))


@dataclass(frozen=True)
class CompletenessClaim:
    claim_id: str
    subject_id: str
    scope_id: str
    source_snapshot_id: str
    enumeration_method: str
    method_version: str
    covered_units: int
    expected_units: Optional[int]
    status: CompletenessStatus
    evidence_refs: Tuple[EvidenceRef, ...] = ()
    verification_method_id: Optional[str] = None
    exclusions: Tuple[str, ...] = ()
    unsupported_constructs: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    invalidation_triggers: Tuple[str, ...] = ()
    predicate_id: Optional[str] = None
    covered_unit_ids: Tuple[str, ...] = ()
    expected_unit_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("claim_id", "subject_id", "scope_id", "source_snapshot_id", "enumeration_method", "method_version"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if not isinstance(self.status, CompletenessStatus):
            raise ContractError("status must be a CompletenessStatus")
        if isinstance(self.covered_units, bool) or not isinstance(self.covered_units, int) or self.covered_units < 0:
            raise ContractError("covered_units must be a non-negative integer")
        if self.expected_units is not None and (
            isinstance(self.expected_units, bool) or not isinstance(self.expected_units, int) or self.expected_units < 0
        ):
            raise ContractError("expected_units must be a non-negative integer or None")
        if self.expected_units is not None and self.covered_units > self.expected_units:
            raise ContractError("covered_units cannot exceed expected_units")
        if not isinstance(self.evidence_refs, tuple) or any(not isinstance(ref, EvidenceRef) for ref in self.evidence_refs):
            raise ContractError("evidence_refs must be a tuple of EvidenceRef values")
        evidence_ids = tuple(ref.evidence_id for ref in self.evidence_refs)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ContractError("evidence_refs must not repeat evidence_id values")
        object.__setattr__(self, "verification_method_id", _optional_text(self.verification_method_id, "verification_method_id"))
        object.__setattr__(self, "predicate_id", _optional_text(self.predicate_id, "predicate_id"))
        object.__setattr__(self, "exclusions", _unique_texts(self.exclusions, "exclusions"))
        object.__setattr__(self, "unsupported_constructs", _unique_texts(self.unsupported_constructs, "unsupported_constructs"))
        object.__setattr__(self, "assumptions", _unique_texts(self.assumptions, "assumptions"))
        object.__setattr__(self, "invalidation_triggers", _unique_texts(self.invalidation_triggers, "invalidation_triggers"))
        object.__setattr__(self, "covered_unit_ids", _unique_texts(self.covered_unit_ids, "covered_unit_ids"))
        object.__setattr__(self, "expected_unit_ids", _unique_texts(self.expected_unit_ids, "expected_unit_ids"))
        if self.covered_unit_ids and len(self.covered_unit_ids) != self.covered_units:
            raise ContractError("covered_unit_ids length must equal covered_units")
        if self.expected_unit_ids and self.expected_units is not None and len(self.expected_unit_ids) != self.expected_units:
            raise ContractError("expected_unit_ids length must equal expected_units")
        if self.status is CompletenessStatus.SUPPORTED_WITHIN_SCOPE:
            if self.expected_units is None or self.covered_units != self.expected_units:
                raise ContractError("supported completeness requires a known denominator and exact coverage")
            if not self.evidence_refs:
                raise ContractError("supported completeness requires evidence_refs")
            if self.verification_method_id is None:
                raise ContractError("supported completeness requires verification_method_id")
            if self.unsupported_constructs:
                raise ContractError("unsupported constructs prevent supported completeness")
            if self.predicate_id is None:
                raise ContractError("supported completeness requires predicate_id")
            if len(self.expected_unit_ids) != self.expected_units:
                raise ContractError("supported completeness requires an exact expected-unit manifest")
            if set(self.covered_unit_ids) != set(self.expected_unit_ids):
                raise ContractError("supported completeness requires exact unit-manifest coverage")
            if any(ref.source_snapshot_id != self.source_snapshot_id for ref in self.evidence_refs):
                raise ContractError("completeness evidence must bind to the claim source snapshot")


@dataclass(frozen=True)
class ProvenanceDependency:
    """A directed edge: dependent_id relies on dependency_id."""

    edge_id: str
    dependent_id: str
    dependency_id: str
    dependency_kind: str
    expected_revision: str

    def __post_init__(self) -> None:
        for name in ("edge_id", "dependent_id", "dependency_id", "dependency_kind", "expected_revision"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if self.dependent_id == self.dependency_id:
            raise ContractError("a provenance node cannot depend on itself")


@dataclass(frozen=True)
class ProvenanceInvalidation:
    """Append-only record that a changed node invalidates a dependent node."""

    invalidation_id: str
    node_id: str
    root_change_id: str
    changed_dependency_id: str
    reason: str
    observed_at: str

    def __post_init__(self) -> None:
        for name in ("invalidation_id", "node_id", "root_change_id", "changed_dependency_id", "reason", "observed_at"):
            object.__setattr__(self, name, _required(getattr(self, name), name))


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    INVALIDATED = "invalidated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FreshnessResult:
    node_id: str
    status: FreshnessStatus
    invalidation_ids: Tuple[str, ...] = ()
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _required(self.node_id, "node_id"))
        if not isinstance(self.status, FreshnessStatus):
            raise ContractError("status must be a FreshnessStatus")
        object.__setattr__(self, "invalidation_ids", _unique_texts(self.invalidation_ids, "invalidation_ids"))
        object.__setattr__(self, "reason", _optional_text(self.reason, "reason"))


@dataclass(frozen=True)
class ProvenanceManifest:
    """Closed declaration of the dependency edges required to assess one node."""

    manifest_id: str
    node_id: str
    edge_ids: Tuple[str, ...]
    manifest_version: str

    def __post_init__(self) -> None:
        for name in ("manifest_id", "node_id", "manifest_version"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        object.__setattr__(self, "edge_ids", _unique_texts(self.edge_ids, "edge_ids"))
        # An explicit empty manifest declares a terminal provenance node.
        # Absence of a manifest remains UNKNOWN; empty is not inferred implicitly.

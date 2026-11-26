"""Fail-closed evaluation of scope-bound negative-claim admissibility.

This module checks declared preconditions. It does not infer proposition truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import (CompletenessClaim, CompletenessStatus, FreshnessResult, FreshnessStatus)


@dataclass(frozen=True)
class NegativeClaimRequest:
    subject_id: str
    predicate_id: str
    scope_id: str
    source_snapshot_id: str
    closed_world_rule_id: str
    rule_allows_closed_world: bool
    active_invalidation_triggers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("subject_id", "predicate_id", "scope_id", "source_snapshot_id", "closed_world_rule_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.rule_allows_closed_world, bool):
            raise ValueError("rule_allows_closed_world must be a bool")
        if not isinstance(self.active_invalidation_triggers, tuple):
            raise ValueError("active_invalidation_triggers must be an immutable tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.active_invalidation_triggers):
            raise ValueError("active invalidation triggers must be non-empty strings")
        if len(set(self.active_invalidation_triggers)) != len(self.active_invalidation_triggers):
            raise ValueError("active invalidation triggers must be unique")


@dataclass(frozen=True)
class AdmissibilityDecision:
    admissible: bool
    reasons: tuple[str, ...]
    claim_id: str


def evaluate_negative_claim(
    claim: CompletenessClaim,
    request: NegativeClaimRequest,
) -> AdmissibilityDecision:
    """Determine whether a negative claim is admissible under declared scope.

    A positive result means only that the supplied completeness claim meets the
    encoded preconditions for a rule-authorized closed-world inference. The
    caller must still apply that rule and preserve the resulting derivation.
    """
    if not isinstance(claim, CompletenessClaim):
        raise TypeError("claim must be a CompletenessClaim")
    if not isinstance(request, NegativeClaimRequest):
        raise TypeError("request must be a NegativeClaimRequest")

    reasons: list[str] = []
    exact_fields = (
        ("subject_id", claim.subject_id, request.subject_id),
        ("predicate_id", claim.predicate_id, request.predicate_id),
        ("scope_id", claim.scope_id, request.scope_id),
        ("source_snapshot_id", claim.source_snapshot_id, request.source_snapshot_id),
    )
    for name, actual, requested in exact_fields:
        if actual != requested:
            reasons.append(f"{name} mismatch")

    if claim.status is not CompletenessStatus.SUPPORTED_WITHIN_SCOPE:
        reasons.append("completeness status is not SUPPORTED_WITHIN_SCOPE")
    if claim.expected_units is None:
        reasons.append("expected denominator is unknown")
    elif claim.covered_units != claim.expected_units:
        reasons.append("covered-unit count differs from expected denominator")
    if not claim.expected_unit_ids:
        if claim.expected_units != 0:
            reasons.append("expected-unit manifest is absent")
    if set(claim.covered_unit_ids) != set(claim.expected_unit_ids):
        reasons.append("covered-unit manifest does not exactly match expected units")
    if len(claim.covered_unit_ids) != claim.covered_units:
        reasons.append("covered-unit identifiers do not account for covered-unit count")
    if not claim.evidence_refs:
        reasons.append("enumeration evidence is absent")
    if any(ref.source_snapshot_id != claim.source_snapshot_id for ref in claim.evidence_refs):
        reasons.append("evidence snapshot does not match completeness snapshot")
    if not claim.verification_method_id:
        reasons.append("verification method is absent")
    if claim.exclusions:
        reasons.append("scope contains declared exclusions")
    if claim.unsupported_constructs:
        reasons.append("scope contains unsupported constructs")
    if claim.assumptions:
        reasons.append("completeness depends on unverified assumptions")
    active = set(request.active_invalidation_triggers)
    declared = set(claim.invalidation_triggers)
    if active & declared:
        reasons.append("one or more completeness invalidation triggers are active")
    if not request.closed_world_rule_id.strip():
        reasons.append("closed-world rule identity is absent")
    if request.rule_allows_closed_world is not True:
        reasons.append("applicable rule does not explicitly authorize closed-world inference")

    return AdmissibilityDecision(
        admissible=not reasons,
        reasons=tuple(reasons),
        claim_id=claim.claim_id,
    )



def evaluate_negative_claim_with_freshness(
    claim: CompletenessClaim,
    request: NegativeClaimRequest,
    freshness: FreshnessResult,
) -> AdmissibilityDecision:
    """Evaluate M7.5.3 preconditions and require an explicit FRESH result.

    UNKNOWN is fail-closed: absence of invalidation records is not evidence of
    freshness unless a dependency declaration establishes what was checked.
    """
    if not isinstance(freshness, FreshnessResult):
        raise TypeError("freshness must be a FreshnessResult")
    if freshness.node_id != f"claim:{claim.claim_id}":
        raise ValueError("freshness result belongs to a different claim")
    decision = evaluate_negative_claim(claim, request)
    if freshness.status is FreshnessStatus.FRESH:
        return decision
    reason = (
        "completeness claim has been invalidated by a dependency change"
        if freshness.status is FreshnessStatus.INVALIDATED
        else "completeness claim freshness is unknown because dependencies are not declared"
    )
    return AdmissibilityDecision(
        admissible=False,
        reasons=decision.reasons + (reason,),
        claim_id=decision.claim_id,
    )

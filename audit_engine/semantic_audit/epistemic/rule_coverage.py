"""Rule-derived epistemic coverage manifests for AE-32C.

The built-in, versioned AE-32C rule registry is the sole derivation source in
this tranche. Caller-supplied rule lists select applicable contracts; callers
cannot redefine contract contents or shrink their required obligation sets.
This is integrity-by-versioned-source, not cryptographic author authentication.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from audit_engine.semantic_audit.ae32c.rule_contracts import (
    RULE_CONTRACT_VERSION,
    RULE_REGISTRY_SCHEMA,
    RuleContractError,
    canonical_bytes,
    resolve_rule,
    rule_registry,
)
from .assurance import AssuranceClaim
from .coverage import (
    CoverageContractError,
    CoverageObligation,
    EpistemicCoverageManifest,
    ObligationDisposition,
)


RULE_COVERAGE_REGISTRY_ID = "ae32c-rule-coverage-registry"
RULE_COVERAGE_PLAN_SCHEMA = "ae32c/rule-derived-coverage-plan/v1"


class RuleCoverageDerivationError(ValueError):
    """A rule-derived coverage plan cannot be established safely."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class RuleCoveragePlan:
    claim_id: str
    source_snapshot_id: str
    graph_snapshot_id: str
    registry_id: str
    registry_version: str
    registry_sha256: str
    rule_ids: tuple[str, ...]
    expected_obligation_ids: tuple[str, ...]
    claim_polarities: tuple[tuple[str, str], ...]
    closed_world_rule_ids: tuple[str, ...]
    plan_sha256: str


def _obligation_id(rule_id: str, dimension: str, requirement: str) -> str:
    return f"rule:{rule_id}:{dimension}:{requirement}"


def derive_rule_coverage_plan(
    claim: AssuranceClaim,
    *,
    source_snapshot_id: str,
    graph_snapshot_id: str,
    rule_ids: tuple[str, ...],
) -> RuleCoveragePlan:
    """Derive the complete finite obligation set from built-in rule contracts.

    The selected rule IDs are caller input, so this function proves coverage
    only for those selected rules. It does not prove the caller selected every
    applicable rule or that source/graph inventories are exhaustive.
    """
    if not isinstance(claim, AssuranceClaim):
        raise TypeError("claim must be an AssuranceClaim")
    if not isinstance(rule_ids, tuple) or not rule_ids:
        raise RuleCoverageDerivationError("rule_ids must be a non-empty immutable tuple")
    if any(not isinstance(x, str) or not x.strip() for x in rule_ids):
        raise RuleCoverageDerivationError("rule_ids must contain non-empty strings")
    selected_ids = tuple(sorted(set(x.strip() for x in rule_ids)))
    if len(selected_ids) != len(rule_ids):
        raise RuleCoverageDerivationError("rule_ids must not contain duplicates")
    for name, value in (("source_snapshot_id", source_snapshot_id), ("graph_snapshot_id", graph_snapshot_id)):
        if not isinstance(value, str) or not value.strip():
            raise RuleCoverageDerivationError(f"{name} must be a non-empty string")

    registry = rule_registry()
    registry_payload = {key: value for key, value in registry.items() if key != "registry_sha256"}
    calculated_registry_sha = _sha256(canonical_bytes(registry_payload))
    if registry.get("schema") != RULE_REGISTRY_SCHEMA or registry.get("registry_sha256") != calculated_registry_sha:
        raise RuleCoverageDerivationError("built_in_rule_registry_integrity_failure")

    obligations: set[str] = set()
    polarities: list[tuple[str, str]] = []
    closed_world: list[str] = []
    for rule_id in selected_ids:
        try:
            contract = resolve_rule(rule_id, registry)
        except RuleContractError as exc:
            raise RuleCoverageDerivationError(str(exc)) from exc
        if contract.get("version") != RULE_CONTRACT_VERSION:
            raise RuleCoverageDerivationError("unsupported_rule_contract_version:" + rule_id)
        polarity = contract.get("claim_polarity")
        if polarity not in {"positive", "absence", "mixed"}:
            raise RuleCoverageDerivationError("invalid_claim_polarity:" + rule_id)
        evidence_kinds = contract.get("required_evidence_kinds")
        coverage_kinds = contract.get("required_coverage")
        if not isinstance(evidence_kinds, list) or not evidence_kinds:
            raise RuleCoverageDerivationError("rule_has_no_required_evidence_kinds:" + rule_id)
        if not isinstance(coverage_kinds, list) or not coverage_kinds:
            raise RuleCoverageDerivationError("rule_has_no_required_coverage:" + rule_id)
        if any(not isinstance(x, str) or not x.strip() for x in evidence_kinds + coverage_kinds):
            raise RuleCoverageDerivationError("rule_contains_invalid_requirement:" + rule_id)
        if len(evidence_kinds) != len(set(evidence_kinds)) or len(coverage_kinds) != len(set(coverage_kinds)):
            raise RuleCoverageDerivationError("rule_contains_duplicate_requirements:" + rule_id)
        for kind in evidence_kinds:
            obligations.add(_obligation_id(rule_id, "evidence", kind))
        for requirement in coverage_kinds:
            obligations.add(_obligation_id(rule_id, "coverage", requirement))
        polarities.append((rule_id, polarity))
        if contract.get("closed_world") is not None:
            # This records that a contract declares a closed-world clause. It
            # does not validate or authorize the clause in this milestone.
            closed_world.append(rule_id)

    expected = tuple(sorted(obligations))
    material = {
        "schema": RULE_COVERAGE_PLAN_SCHEMA,
        "claim_id": claim.claim_id,
        "source_snapshot_id": source_snapshot_id,
        "graph_snapshot_id": graph_snapshot_id,
        "registry_id": RULE_COVERAGE_REGISTRY_ID,
        "registry_version": RULE_CONTRACT_VERSION,
        "registry_sha256": calculated_registry_sha,
        "rule_ids": list(selected_ids),
        "expected_obligation_ids": list(expected),
        "claim_polarities": [list(x) for x in polarities],
        "closed_world_rule_ids": sorted(closed_world),
    }
    return RuleCoveragePlan(
        claim.claim_id, source_snapshot_id, graph_snapshot_id,
        RULE_COVERAGE_REGISTRY_ID, RULE_CONTRACT_VERSION,
        calculated_registry_sha, selected_ids, expected,
        tuple(polarities), tuple(sorted(closed_world)),
        _sha256(canonical_bytes(material)),
    )


def build_rule_derived_coverage_manifest(
    claim: AssuranceClaim,
    plan: RuleCoveragePlan,
    *,
    assessments: Mapping[str, CoverageObligation] | None = None,
) -> EpistemicCoverageManifest:
    """Build an M7.5.8-compatible manifest with registry-derived obligations.

    Unassessed requirements remain absent from the obligation tuple and are
    consequently reported UNKNOWN by the M7.5.8 evaluator. Supplied assessments
    cannot add obligations or change the derived expected-obligation universe.
    """
    if not isinstance(claim, AssuranceClaim) or not isinstance(plan, RuleCoveragePlan):
        raise TypeError("claim and plan must be AssuranceClaim and RuleCoveragePlan")
    if claim.claim_id != plan.claim_id or claim.source_snapshot_id != plan.source_snapshot_id:
        raise RuleCoverageDerivationError("plan_claim_or_source_snapshot_mismatch")
    expected_plan = derive_rule_coverage_plan(
        claim, source_snapshot_id=plan.source_snapshot_id,
        graph_snapshot_id=plan.graph_snapshot_id, rule_ids=plan.rule_ids,
    )
    if expected_plan != plan:
        raise RuleCoverageDerivationError("rule_coverage_plan_integrity_mismatch")
    supplied = dict(assessments or {})
    unexpected = set(supplied) - set(plan.expected_obligation_ids)
    if unexpected:
        raise RuleCoverageDerivationError("assessment_outside_derived_rule_universe:" + ",".join(sorted(unexpected)))
    selected: list[CoverageObligation] = []
    for obligation_id, item in supplied.items():
        if not isinstance(item, CoverageObligation) or item.obligation_id != obligation_id:
            raise RuleCoverageDerivationError("assessment_identity_mismatch:" + obligation_id)
        selected.append(item)
    return EpistemicCoverageManifest(
        manifest_id="rule-derived:" + plan.plan_sha256,
        claim_id=claim.claim_id,
        proposition_id=claim.proposition_id,
        subject_id=claim.subject_id,
        scope_id=claim.scope_id,
        source_snapshot_id=claim.source_snapshot_id,
        registry_id=plan.registry_id,
        registry_version=plan.registry_version,
        registry_sha256=plan.registry_sha256,
        expected_obligation_ids=plan.expected_obligation_ids,
        obligations=tuple(sorted(selected, key=lambda x: x.obligation_id)),
    )


def verify_rule_derived_manifest(
    claim: AssuranceClaim,
    plan: RuleCoveragePlan,
    manifest: EpistemicCoverageManifest,
) -> None:
    """Reject a manifest unless it exactly retains the derived obligation universe."""
    expected_plan = derive_rule_coverage_plan(
        claim, source_snapshot_id=plan.source_snapshot_id,
        graph_snapshot_id=plan.graph_snapshot_id, rule_ids=plan.rule_ids,
    )
    if expected_plan != plan:
        raise RuleCoverageDerivationError("rule_coverage_plan_integrity_mismatch")
    if manifest.claim_id != claim.claim_id:
        raise RuleCoverageDerivationError("manifest_claim_mismatch")
    if manifest.source_snapshot_id != plan.source_snapshot_id:
        raise RuleCoverageDerivationError("manifest_source_snapshot_mismatch")
    if manifest.registry_id != plan.registry_id or manifest.registry_version != plan.registry_version:
        raise RuleCoverageDerivationError("manifest_registry_identity_mismatch")
    if manifest.registry_sha256 != plan.registry_sha256:
        raise RuleCoverageDerivationError("manifest_registry_digest_mismatch")
    if manifest.expected_obligation_ids != plan.expected_obligation_ids:
        raise RuleCoverageDerivationError("manifest_derived_obligation_universe_mismatch")
    if (manifest.proposition_id, manifest.subject_id, manifest.scope_id) != (
        claim.proposition_id, claim.subject_id, claim.scope_id
    ):
        raise RuleCoverageDerivationError("manifest_claim_context_mismatch")

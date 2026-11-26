"""Claim-relative epistemic coverage evaluation.

This layer checks whether every obligation in a declared coverage manifest is
accounted for by persisted, scope-bound and fresh evidence. It does not prove
that the manifest enumerates every real-world obligation or infer proposition
truth.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from .assurance import AssuranceClaim
from .assurance_store import AssuranceStore
from .contracts import AssertionPolarity, EvidenceRef, GapState, FreshnessStatus
from .store import EpistemicStore


class CoverageContractError(ValueError):
    """A coverage manifest violates its local structural contract."""


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoverageContractError(f"{field} must be a non-empty string")
    return value.strip()


def _ids(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise CoverageContractError(f"{field} must be an immutable tuple")
    result = tuple(_text(value, field) for value in values)
    if len(result) != len(set(result)):
        raise CoverageContractError(f"{field} must not contain duplicates")
    return result


class ObligationDisposition(str, Enum):
    EVIDENCE_BOUND = "evidence_bound"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    EXCLUDED = "excluded"
    CONFLICTED = "conflicted"
    BLOCKED = "blocked"
    NOT_ASSESSED = "not_assessed"


class EpistemicCoverageStatus(str, Enum):
    EVIDENCE_COMPLETE_WITHIN_DECLARED_MANIFEST = "evidence_complete_within_declared_manifest"
    UNKNOWN = "unknown"
    CONTESTED = "contested"
    INCOMPLETE = "incomplete"
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class CoverageObligation:
    obligation_id: str
    disposition: ObligationDisposition
    evidence_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()
    limitation: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "obligation_id", _text(self.obligation_id, "obligation_id"))
        if not isinstance(self.disposition, ObligationDisposition):
            raise CoverageContractError("disposition must be an ObligationDisposition")
        object.__setattr__(self, "evidence_ids", _ids(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "gap_ids", _ids(self.gap_ids, "gap_ids"))
        if self.limitation is not None:
            object.__setattr__(self, "limitation", _text(self.limitation, "limitation"))
        if self.disposition is ObligationDisposition.EVIDENCE_BOUND and not self.evidence_ids:
            raise CoverageContractError("EVIDENCE_BOUND obligations require evidence_ids")


@dataclass(frozen=True)
class EpistemicCoverageManifest:
    manifest_id: str
    claim_id: str
    proposition_id: str
    subject_id: str
    scope_id: str
    source_snapshot_id: str
    registry_id: str
    registry_version: str
    registry_sha256: str
    expected_obligation_ids: tuple[str, ...]
    obligations: tuple[CoverageObligation, ...]

    def __post_init__(self) -> None:
        for name in (
            "manifest_id", "claim_id", "proposition_id", "subject_id",
            "scope_id", "source_snapshot_id", "registry_id", "registry_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        digest = self.registry_sha256
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise CoverageContractError("registry_sha256 must be 64 lowercase hexadecimal characters")
        object.__setattr__(self, "expected_obligation_ids", _ids(self.expected_obligation_ids, "expected_obligation_ids"))
        if not self.expected_obligation_ids:
            raise CoverageContractError("expected_obligation_ids must declare a non-empty obligation universe")
        if not isinstance(self.obligations, tuple) or any(not isinstance(x, CoverageObligation) for x in self.obligations):
            raise CoverageContractError("obligations must be an immutable tuple of CoverageObligation values")
        obligation_ids = tuple(x.obligation_id for x in self.obligations)
        if len(obligation_ids) != len(set(obligation_ids)):
            raise CoverageContractError("obligation IDs must be unique")
        unexpected = set(obligation_ids) - set(self.expected_obligation_ids)
        if unexpected:
            raise CoverageContractError("assessed obligations are outside the declared registry universe: " + ", ".join(sorted(unexpected)))

    @property
    def manifest_sha256(self) -> str:
        payload = asdict(self)
        payload["obligations"] = [
            {
                "obligation_id": item.obligation_id,
                "disposition": item.disposition.value,
                "evidence_ids": list(item.evidence_ids),
                "gap_ids": list(item.gap_ids),
                "limitation": item.limitation,
            }
            for item in self.obligations
        ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class EpistemicCoverageResult:
    claim_id: str
    status: EpistemicCoverageStatus
    manifest_sha256: str
    expected_obligation_ids: tuple[str, ...]
    missing_obligation_ids: tuple[str, ...]
    unresolved_obligation_ids: tuple[str, ...]
    contested_obligation_ids: tuple[str, ...]
    freshness_results: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]
    ledger_consistent: bool


def evaluate_epistemic_coverage(
    claim_id: str,
    manifest: EpistemicCoverageManifest,
    assurance_store: AssuranceStore,
    epistemic_store: EpistemicStore,
) -> EpistemicCoverageResult:
    """Evaluate declared epistemic obligations against persisted evidence/gaps.

    A complete result is deliberately named
    EVIDENCE_COMPLETE_WITHIN_DECLARED_MANIFEST. The registry and manifest are
    caller-supplied inputs; this function does not authenticate their authors
    or prove that the declared obligation universe is exhaustive.
    """
    claim_id = _text(claim_id, "claim_id")
    if not isinstance(manifest, EpistemicCoverageManifest):
        raise TypeError("manifest must be an EpistemicCoverageManifest")
    if not isinstance(assurance_store, AssuranceStore):
        raise TypeError("assurance_store must be an AssuranceStore")
    if not isinstance(epistemic_store, EpistemicStore):
        raise TypeError("epistemic_store must be an EpistemicStore")
    if manifest.claim_id != claim_id:
        raise CoverageContractError("manifest claim_id does not match requested claim")

    reasons: list[str] = []
    freshness: dict[str, str] = {}
    missing = tuple(sorted(set(manifest.expected_obligation_ids) - {x.obligation_id for x in manifest.obligations}))
    unresolved: set[str] = set(missing)
    contested: set[str] = set()
    invalidated = False
    unknown = bool(missing)
    incomplete = False

    try:
        assurance_before = assurance_store.snapshot_token()
        epistemic_before = epistemic_store.snapshot_token()
        assurance_records = assurance_store.records_snapshot()
        assertions = epistemic_store.assertion_records_snapshot()
        claims = [x for x in assurance_records if isinstance(x, AssuranceClaim) and x.claim_id == claim_id]
        if len(claims) != 1:
            reasons.append("persisted assurance claim is absent or ambiguous")
            incomplete = True
            claim = None
        else:
            claim = claims[0]
            exact = (
                ("proposition_id", claim.proposition_id, manifest.proposition_id),
                ("subject_id", claim.subject_id, manifest.subject_id),
                ("scope_id", claim.scope_id, manifest.scope_id),
                ("source_snapshot_id", claim.source_snapshot_id, manifest.source_snapshot_id),
            )
            for field, actual, declared in exact:
                if actual != declared:
                    reasons.append(f"manifest {field} does not match persisted assurance claim")
                    incomplete = True

        evidence_by_id: dict[str, list[tuple[Any, EvidenceRef]]] = {}
        for assertion in assertions:
            for ref in assertion.evidence_refs:
                evidence_by_id.setdefault(ref.evidence_id, []).append((assertion, ref))
        dependency_edges = epistemic_store.dependency_history()
        edges_by_dependent: dict[str, set[tuple[str, str, str]]] = {}
        for edge in dependency_edges:
            payload = edge["payload"]
            edges_by_dependent.setdefault(payload["dependent_id"], set()).add((
                payload["dependency_kind"], payload["dependency_id"], payload["expected_revision"],
            ))

        def check_persisted_ref(ref: EvidenceRef, obligation_id: str) -> None:
            records = evidence_by_id.get(ref.evidence_id, [])
            if not records or all(stored_ref != ref for _, stored_ref in records):
                unresolved.add(obligation_id)
                incomplete = True
                reasons.append(f"knowledge-gap resolution evidence {ref.evidence_id} is not persisted with matching metadata")
                return
            node_id = f"evidence:{ref.evidence_id}"
            expected = {
                ("source_snapshot", f"snapshot:{ref.source_snapshot_id}", ref.source_snapshot_id),
                ("evidence_producer", f"producer:{ref.producer_id}", ref.producer_id),
                ("evidence_method", f"method:{ref.method_id}", ref.method_id),
            }
            if ref.artifact_sha256:
                expected.add(("artifact_digest", f"artifact-sha256:{ref.artifact_sha256}", ref.artifact_sha256))
            if edges_by_dependent.get(node_id, set()) != expected:
                unresolved.add(obligation_id)
                incomplete = True
                reasons.append(f"provenance edges for resolution evidence {ref.evidence_id} do not match its metadata")
            closure = epistemic_store.freshness_closure(node_id)
            freshness[ref.evidence_id] = closure.status.value
            if closure.status is FreshnessStatus.INVALIDATED:
                invalidated = True
                reasons.append(f"resolution evidence {ref.evidence_id} provenance is invalidated")
            elif closure.status is FreshnessStatus.UNKNOWN:
                unresolved.add(obligation_id)
                unknown = True
                reasons.append(f"resolution evidence {ref.evidence_id} provenance closure is unknown")

        for obligation in manifest.obligations:
            oid = obligation.obligation_id
            if obligation.disposition is ObligationDisposition.UNKNOWN or obligation.disposition is ObligationDisposition.NOT_ASSESSED:
                unresolved.add(oid)
                unknown = True
                reasons.append(f"obligation {oid} is {obligation.disposition.value}")
            elif obligation.disposition is ObligationDisposition.CONFLICTED:
                contested.add(oid)
                reasons.append(f"obligation {oid} is explicitly conflicted")
            elif obligation.disposition in (ObligationDisposition.UNSUPPORTED, ObligationDisposition.EXCLUDED, ObligationDisposition.BLOCKED):
                unresolved.add(oid)
                incomplete = True
                reasons.append(f"obligation {oid} is {obligation.disposition.value}")
            elif obligation.disposition is ObligationDisposition.EVIDENCE_BOUND:
                for evidence_id in obligation.evidence_ids:
                    records = evidence_by_id.get(evidence_id, [])
                    if not records:
                        unresolved.add(oid)
                        unknown = True
                        reasons.append(f"obligation {oid} references absent persisted evidence {evidence_id}")
                        continue
                    metadata = {ref for _, ref in records}
                    if len(metadata) != 1:
                        unresolved.add(oid)
                        incomplete = True
                        reasons.append(f"evidence {evidence_id} has conflicting persisted metadata")
                    selected_ref = records[0][1]
                    expected_edges = {
                        ("source_snapshot", f"snapshot:{selected_ref.source_snapshot_id}", selected_ref.source_snapshot_id),
                        ("evidence_producer", f"producer:{selected_ref.producer_id}", selected_ref.producer_id),
                        ("evidence_method", f"method:{selected_ref.method_id}", selected_ref.method_id),
                    }
                    if selected_ref.artifact_sha256:
                        expected_edges.add(("artifact_digest", f"artifact-sha256:{selected_ref.artifact_sha256}", selected_ref.artifact_sha256))
                    if edges_by_dependent.get(f"evidence:{evidence_id}", set()) != expected_edges:
                        unresolved.add(oid)
                        incomplete = True
                        reasons.append(f"evidence provenance edges for {evidence_id} do not match its persisted metadata")
                    valid_context = False
                    support_found = False
                    for assertion, ref in records:
                        if claim is not None and (
                            assertion.proposition_id == claim.proposition_id
                            and assertion.scope_id == claim.scope_id
                            and ref.source_snapshot_id == claim.source_snapshot_id
                        ):
                            valid_context = True
                            if assertion.polarity is AssertionPolarity.SUPPORTS:
                                support_found = True
                        elif claim is not None:
                            reasons.append(f"evidence {evidence_id} is not bound to the claim proposition, scope and snapshot")
                            incomplete = True
                        if assertion.polarity is AssertionPolarity.CHALLENGES:
                            contested.add(oid)
                    if not valid_context or not support_found:
                        unresolved.add(oid)
                        incomplete = True
                        if valid_context and not support_found:
                            reasons.append(f"evidence {evidence_id} has no supporting assertion for this claim")
                    closure = epistemic_store.freshness_closure(f"evidence:{evidence_id}")
                    freshness[evidence_id] = closure.status.value
                    if closure.status is FreshnessStatus.INVALIDATED:
                        invalidated = True
                        reasons.append(f"evidence {evidence_id} provenance is invalidated")
                    elif closure.status is FreshnessStatus.UNKNOWN:
                        unresolved.add(oid)
                        unknown = True
                        reasons.append(f"evidence {evidence_id} provenance closure is unknown")
                for gap_id in obligation.gap_ids:
                    gap = epistemic_store.latest_gap(gap_id)
                    if gap is None:
                        unresolved.add(oid)
                        unknown = True
                        reasons.append(f"obligation {oid} references absent knowledge gap {gap_id}")
                        continue
                    state = GapState(gap["payload"]["state"])
                    if state is GapState.RESOLVED:
                        resolution_refs = gap["payload"].get("resolution_evidence_refs", [])
                        if not resolution_refs:
                            unresolved.add(oid)
                            incomplete = True
                            reasons.append(f"resolved gap {gap_id} lacks resolution evidence")
                        for raw_ref in resolution_refs:
                            try:
                                resolution_ref = EvidenceRef(**raw_ref)
                            except Exception:
                                unresolved.add(oid)
                                incomplete = True
                                reasons.append(f"resolved gap {gap_id} contains an invalid resolution evidence reference")
                                continue
                            if claim is None or (
                                resolution_ref.source_snapshot_id != claim.source_snapshot_id
                                or not any(
                                    assertion.proposition_id == claim.proposition_id
                                    and assertion.scope_id == claim.scope_id
                                    for assertion, stored_ref in evidence_by_id.get(resolution_ref.evidence_id, [])
                                    if stored_ref == resolution_ref
                                )
                            ):
                                unresolved.add(oid)
                                incomplete = True
                                reasons.append(f"resolved gap {gap_id} resolution evidence is not bound to the claim")
                            check_persisted_ref(resolution_ref, oid)
                    else:
                        unresolved.add(oid)
                        if state is GapState.ACCEPTED_RESIDUAL:
                            unknown = True
                        else:
                            incomplete = True
                        reasons.append(f"knowledge gap {gap_id} remains {state.value}")

        epistemic_after = epistemic_store.snapshot_token()
        assurance_after = assurance_store.snapshot_token()
        ledger_consistent = assurance_before == assurance_after and epistemic_before == epistemic_after
        if not ledger_consistent:
            unknown = True
            reasons.append("one or both ledgers changed during coverage evaluation")
    except Exception as exc:
        return EpistemicCoverageResult(
            claim_id=claim_id,
            status=EpistemicCoverageStatus.UNKNOWN,
            manifest_sha256=manifest.manifest_sha256,
            expected_obligation_ids=manifest.expected_obligation_ids,
            missing_obligation_ids=missing,
            unresolved_obligation_ids=tuple(sorted(unresolved)),
            contested_obligation_ids=tuple(sorted(contested)),
            freshness_results=tuple(sorted(freshness.items())),
            reasons=(f"coverage evaluation could not be completed: {type(exc).__name__}",),
            ledger_consistent=False,
        )

    if invalidated:
        status = EpistemicCoverageStatus.INVALIDATED
    elif contested:
        status = EpistemicCoverageStatus.CONTESTED
    elif unknown:
        status = EpistemicCoverageStatus.UNKNOWN
    elif incomplete or unresolved:
        status = EpistemicCoverageStatus.INCOMPLETE
    else:
        status = EpistemicCoverageStatus.EVIDENCE_COMPLETE_WITHIN_DECLARED_MANIFEST
    if status is EpistemicCoverageStatus.EVIDENCE_COMPLETE_WITHIN_DECLARED_MANIFEST:
        reasons.append("all declared obligations are evidence-bound within this manifest; exhaustiveness and truth are not established")
    return EpistemicCoverageResult(
        claim_id=claim_id,
        status=status,
        manifest_sha256=manifest.manifest_sha256,
        expected_obligation_ids=manifest.expected_obligation_ids,
        missing_obligation_ids=missing,
        unresolved_obligation_ids=tuple(sorted(unresolved)),
        contested_obligation_ids=tuple(sorted(contested)),
        freshness_results=tuple(sorted(freshness.items())),
        reasons=tuple(reasons),
        ledger_consistent=ledger_consistent,
    )

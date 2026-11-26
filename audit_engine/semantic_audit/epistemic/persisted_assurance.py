"""Store-backed assurance evaluation across the independent epistemic ledgers.

This module fails closed when either ledger is invalid, evidence is missing,
evidence provenance is incomplete, or the two ledgers change during evaluation.
It does not infer proposition truth or make audit/authorization decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .assurance import (
    ArgumentAssessment,
    AssuranceClaim,
    AssuranceContractError,
    ArgumentLink,
    Defeater,
    DefeaterEvent,
    evaluate_assurance,
)
from .assurance_store import AssuranceStore, AssuranceStoreError
from .contracts import (
    EvidenceRef,
    FreshnessResult,
    FreshnessStatus,
)
from .store import EpistemicStore, StoreError


@dataclass(frozen=True)
class PersistedAssuranceResult:
    claim_id: str
    assessment: ArgumentAssessment
    claim: AssuranceClaim | None
    freshness_results: tuple[FreshnessResult, ...]
    missing_evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    ledger_consistent: bool


def _incomplete(
    claim_id: str,
    claim: AssuranceClaim | None,
    reasons: tuple[str, ...],
    *,
    freshness: tuple[FreshnessResult, ...] = (),
    missing: tuple[str, ...] = (),
    ledger_consistent: bool = False,
) -> PersistedAssuranceResult:
    return PersistedAssuranceResult(
        claim_id=claim_id,
        assessment=ArgumentAssessment.INCOMPLETE,
        claim=claim,
        freshness_results=freshness,
        missing_evidence_ids=missing,
        reasons=reasons,
        ledger_consistent=ledger_consistent,
    )


def evaluate_persisted_assurance(
    claim_id: str,
    assurance_store: AssuranceStore,
    epistemic_store: EpistemicStore,
) -> PersistedAssuranceResult:
    """Evaluate one persisted assurance claim using evidence and freshness stores.

    The two SQLite ledgers are not transactionally coupled. This function uses
    verified start/end hash-chain tokens in overlapping read intervals. If
    either ledger changes during the evaluation, the result is INCOMPLETE.
    """
    if not isinstance(claim_id, str) or not claim_id.strip():
        raise ValueError("claim_id must be a non-empty string")
    if not isinstance(assurance_store, AssuranceStore):
        raise TypeError("assurance_store must be an AssuranceStore")
    if not isinstance(epistemic_store, EpistemicStore):
        raise TypeError("epistemic_store must be an EpistemicStore")
    claim_id = claim_id.strip()

    try:
        assurance_before = assurance_store.snapshot_token()
        epistemic_before = epistemic_store.snapshot_token()
        assurance_records = assurance_store.records_snapshot()
        evidence_assertions = epistemic_store.assertion_records_snapshot()

        claims = [
            item for item in assurance_records
            if isinstance(item, AssuranceClaim) and item.claim_id == claim_id
        ]
        if len(claims) != 1:
            return _incomplete(
                claim_id, None,
                ("persisted assurance claim is absent or ambiguous",),
            )
        claim = claims[0]
        links = tuple(
            item for item in assurance_records
            if isinstance(item, ArgumentLink) and item.claim_id == claim_id
        )
        defeaters = tuple(
            item for item in assurance_records
            if isinstance(item, Defeater) and item.claim_id == claim_id
        )
        defeater_ids = {item.defeater_id for item in defeaters}
        events = tuple(
            item for item in assurance_records
            if isinstance(item, DefeaterEvent) and item.defeater_id in defeater_ids
        )

        evidence_by_id: dict[str, EvidenceRef] = {}
        conflicting_ids: set[str] = set()
        for assertion in evidence_assertions:
            for ref in assertion.evidence_refs:
                prior = evidence_by_id.get(ref.evidence_id)
                if prior is not None and prior != ref:
                    conflicting_ids.add(ref.evidence_id)
                else:
                    evidence_by_id[ref.evidence_id] = ref

        used_evidence_ids = set()
        for link in links:
            used_evidence_ids.update(link.evidence_ids)
        for defeater in defeaters:
            used_evidence_ids.update(defeater.evidence_ids)
        for event in events:
            used_evidence_ids.update(event.evidence_ids)

        missing = tuple(sorted(used_evidence_ids - set(evidence_by_id)))
        reasons: list[str] = []
        if missing:
            reasons.append("one or more assurance evidence IDs have no persisted EvidenceAssertion")
        if conflicting_ids & used_evidence_ids:
            reasons.append("one or more evidence IDs resolve to conflicting persisted EvidenceRef metadata")
        if any(
            evidence_by_id[item].source_snapshot_id != claim.source_snapshot_id
            for item in used_evidence_ids
            if item in evidence_by_id
        ):
            reasons.append("one or more evidence references belong to a different source snapshot")

        dependency_edges = epistemic_store.dependency_history()
        edges_by_dependent: dict[str, set[tuple[str, str, str]]] = {}
        for edge in dependency_edges:
            payload = edge["payload"]
            edges_by_dependent.setdefault(payload["dependent_id"], set()).add((
                payload["dependency_kind"],
                payload["dependency_id"],
                payload["expected_revision"],
            ))

        required_nodes = {
            node_id
            for link in links
            for node_id in link.provenance_node_ids
        }
        for evidence_id in used_evidence_ids & set(evidence_by_id):
            ref = evidence_by_id[evidence_id]
            node_id = f"evidence:{evidence_id}"
            expected = {
                ("source_snapshot", f"snapshot:{ref.source_snapshot_id}", ref.source_snapshot_id),
                ("evidence_producer", f"producer:{ref.producer_id}", ref.producer_id),
                ("evidence_method", f"method:{ref.method_id}", ref.method_id),
            }
            if ref.artifact_sha256:
                expected.add((
                    "artifact_digest",
                    f"artifact-sha256:{ref.artifact_sha256}",
                    ref.artifact_sha256,
                ))
            required_nodes.add(node_id)
            actual = edges_by_dependent.get(node_id, set())
            if actual != expected:
                reasons.append(
                    f"evidence provenance edges for {evidence_id} do not exactly match its persisted metadata"
                )

        freshness_results: list[FreshnessResult] = []
        freshness_by_node = {}
        for node_id in sorted(required_nodes):
            result = epistemic_store.freshness_closure(node_id)
            freshness_results.append(result)
            freshness_by_node[node_id] = result.status
            if result.status is not FreshnessStatus.FRESH:
                reasons.append(
                    f"provenance node {node_id} is {result.status.value}: {result.reason or 'no reason supplied'}"
                )

        # Reverse-order token reads make the two verified read intervals overlap.
        epistemic_after = epistemic_store.snapshot_token()
        assurance_after = assurance_store.snapshot_token()
        ledger_consistent = (
            assurance_before == assurance_after
            and epistemic_before == epistemic_after
        )
        if not ledger_consistent:
            reasons.append("one or both ledgers changed during the cross-ledger evaluation")
        if reasons:
            return _incomplete(
                claim_id,
                claim,
                tuple(dict.fromkeys(reasons)),
                freshness=tuple(freshness_results),
                missing=missing,
                ledger_consistent=ledger_consistent,
            )

        try:
            assessment = evaluate_assurance(
                claim,
                links,
                defeaters,
                events,
                available_evidence_ids=frozenset(evidence_by_id),
                freshness=freshness_by_node,
            )
        except AssuranceContractError as exc:
            return _incomplete(
                claim_id,
                claim,
                (f"persisted assurance records violate evaluation contracts: {exc}",),
                freshness=tuple(freshness_results),
                ledger_consistent=True,
            )

        return PersistedAssuranceResult(
            claim_id=claim_id,
            assessment=assessment,
            claim=claim,
            freshness_results=tuple(freshness_results),
            missing_evidence_ids=(),
            reasons=(),
            ledger_consistent=True,
        )
    except Exception as exc:
        return _incomplete(
            claim_id, None,
            (f"persisted ledger integrity or read failure: {exc}",),
        )

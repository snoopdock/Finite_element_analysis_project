"""Independent semantic verification and deterministic replay of M7.5.10 dossiers."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .assurance import AssuranceClaim
from .assurance_store import AssuranceStore
from .coverage import (
    CoverageObligation,
    EpistemicCoverageManifest,
    EpistemicCoverageStatus,
    ObligationDisposition,
    evaluate_epistemic_coverage,
)
from .coverage_dossier import (
    CoverageDossierError,
    CoverageDossierStore,
    _canonical,
    _manifest_payload,
    _result_payload,
)
from .rule_coverage import (
    RuleCoveragePlan,
    verify_rule_derived_manifest,
)
from .store import EpistemicStore


def _restore_plan(raw: dict[str, Any]) -> RuleCoveragePlan:
    if not isinstance(raw, dict):
        raise CoverageDossierError("persisted rule coverage plan is not an object")
    data = dict(raw)
    for name in ("rule_ids", "expected_obligation_ids", "closed_world_rule_ids"):
        data[name] = tuple(data[name])
    data["claim_polarities"] = tuple(tuple(item) for item in data["claim_polarities"])
    try:
        return RuleCoveragePlan(**data)
    except Exception as exc:
        raise CoverageDossierError("persisted rule coverage plan has an invalid shape") from exc


def _restore_manifest(raw: dict[str, Any]) -> EpistemicCoverageManifest:
    if not isinstance(raw, dict):
        raise CoverageDossierError("persisted coverage manifest is not an object")
    data = dict(raw)
    obligations = []
    try:
        for item in data["obligations"]:
            obligations.append(CoverageObligation(
                obligation_id=item["obligation_id"],
                disposition=ObligationDisposition(item["disposition"]),
                evidence_ids=tuple(item["evidence_ids"]),
                gap_ids=tuple(item["gap_ids"]),
                limitation=item.get("limitation"),
            ))
        data["obligations"] = tuple(obligations)
        data["expected_obligation_ids"] = tuple(data["expected_obligation_ids"])
        return EpistemicCoverageManifest(**data)
    except Exception as exc:
        raise CoverageDossierError("persisted coverage manifest has an invalid shape") from exc


def _validate_token(value: Any, field: str) -> tuple[int, str]:
    if (
        not isinstance(value, list) or len(value) != 2
        or isinstance(value[0], bool) or not isinstance(value[0], int) or value[0] < 0
        or not isinstance(value[1], str) or len(value[1]) != 64
        or any(char not in "0123456789abcdef" for char in value[1])
    ):
        raise CoverageDossierError(f"persisted {field} is not a valid ledger token")
    return value[0], value[1]


def verify_coverage_dossier_replay(
    dossier_id: str,
    *,
    assurance_store: AssuranceStore,
    epistemic_store: EpistemicStore,
    dossier_store: CoverageDossierStore,
) -> dict[str, Any]:
    """Validate dossier semantics and replay its evaluation when source snapshots match.

    Semantic validation is independent of the dossier ledger's hash-chain check.
    Replay is performed only when both current source-ledger tokens still equal
    the captured after-tokens. A later source mutation prevents replay but does
    not rewrite or erase the historical dossier.
    """
    if not isinstance(dossier_id, str) or not dossier_id.strip():
        raise ValueError("dossier_id must be a non-empty string")
    payload = dossier_store.get(dossier_id.strip())
    if payload is None:
        raise CoverageDossierError("coverage dossier does not exist")

    try:
        claim_id = payload["claim_id"]
        claims = [
            record for record in assurance_store.records_snapshot()
            if isinstance(record, AssuranceClaim) and record.claim_id == claim_id
        ]
        if len(claims) != 1:
            raise CoverageDossierError("persisted assurance claim is absent or ambiguous")
        claim = claims[0]

        plan = _restore_plan(payload["plan"])
        manifest = _restore_manifest(payload["manifest"])
        verify_rule_derived_manifest(claim, plan, manifest)

        result = payload["result"]
        if not isinstance(result, dict):
            raise CoverageDossierError("persisted evaluation result is not an object")
        if (
            result.get("claim_id") != claim.claim_id
            or result.get("manifest_sha256") != manifest.manifest_sha256
            or result.get("expected_obligation_ids") != list(plan.expected_obligation_ids)
        ):
            raise CoverageDossierError("persisted evaluation result is not bound to its plan and manifest")
        expected_missing = sorted(
            set(plan.expected_obligation_ids)
            - {item.obligation_id for item in manifest.obligations}
        )
        if result.get("missing_obligation_ids") != expected_missing:
            raise CoverageDossierError("persisted evaluation result has an inconsistent missing-obligation set")
        if result.get("status") not in {item.value for item in EpistemicCoverageStatus}:
            raise CoverageDossierError("persisted evaluation result has an unknown status")
        if not isinstance(result.get("ledger_consistent"), bool):
            raise CoverageDossierError("persisted evaluation result lacks a ledger-consistency flag")

        epistemic_before = _validate_token(payload["epistemic_token_before"], "epistemic_token_before")
        epistemic_after = _validate_token(payload["epistemic_token_after"], "epistemic_token_after")
        assurance_before = _validate_token(payload["assurance_token_before"], "assurance_token_before")
        assurance_after = _validate_token(payload["assurance_token_after"], "assurance_token_after")
        snapshot_consistent = payload["snapshot_consistent"]
        if not isinstance(snapshot_consistent, bool):
            raise CoverageDossierError("persisted snapshot_consistent flag is not Boolean")
        token_consistency = (
            epistemic_before == epistemic_after
            and assurance_before == assurance_after
        )
        if snapshot_consistent != token_consistency:
            raise CoverageDossierError("persisted snapshot-consistency flag disagrees with captured tokens")
        if snapshot_consistent and not result["ledger_consistent"]:
            raise CoverageDossierError("coverage result contradicts the stable capture interval")

        inventory = payload["gap_inventory"]
        if not isinstance(inventory, list):
            raise CoverageDossierError("persisted gap inventory is not a list")
        gap_by_id: dict[str, dict] = {}
        for item in inventory:
            if not isinstance(item, dict):
                raise CoverageDossierError("persisted gap inventory contains a malformed entry")
            gap_id = item.get("gap_id")
            revision = item.get("revision")
            gap_payload = item.get("payload")
            event_hash = item.get("event_hash")
            if (
                not isinstance(gap_id, str) or not gap_id
                or gap_id in gap_by_id
                or isinstance(revision, bool) or not isinstance(revision, int) or revision < 1
                or not isinstance(gap_payload, dict)
                or not isinstance(gap_payload.get("scope_id"), str)
                or not isinstance(event_hash, str) or len(event_hash) != 64
                or any(char not in "0123456789abcdef" for char in event_hash)
            ):
                raise CoverageDossierError("persisted gap inventory contains invalid identity or provenance fields")
            gap_by_id[gap_id] = item
        if list(gap_by_id) != sorted(gap_by_id):
            raise CoverageDossierError("persisted gap inventory is not in stable gap-ID order")

        mapping_raw = payload["gap_to_obligations"]
        if not isinstance(mapping_raw, list):
            raise CoverageDossierError("persisted gap mapping is not a list")
        mapping: dict[str, tuple[str, ...]] = {}
        assessed_pairs = {
            (obligation.obligation_id, gap_id)
            for obligation in manifest.obligations
            for gap_id in obligation.gap_ids
        }
        for pair in mapping_raw:
            if not isinstance(pair, list) or len(pair) != 2:
                raise CoverageDossierError("persisted gap mapping contains a malformed pair")
            gap_id, obligation_ids = pair
            if (
                not isinstance(gap_id, str) or gap_id in mapping
                or not isinstance(obligation_ids, list) or not obligation_ids
                or any(not isinstance(value, str) or not value for value in obligation_ids)
                or obligation_ids != sorted(set(obligation_ids))
            ):
                raise CoverageDossierError("persisted gap mapping contains duplicate or invalid identifiers")
            if gap_id not in gap_by_id:
                raise CoverageDossierError("persisted gap mapping references an absent inventory item")
            if gap_by_id[gap_id]["payload"]["scope_id"] != claim.scope_id:
                raise CoverageDossierError("persisted gap mapping crosses the assurance claim scope")
            for obligation_id in obligation_ids:
                if obligation_id not in plan.expected_obligation_ids:
                    raise CoverageDossierError("persisted gap mapping targets an obligation outside the derived plan")
                if (obligation_id, gap_id) not in assessed_pairs:
                    raise CoverageDossierError("persisted gap mapping is not represented in the assessed manifest")
            mapping[gap_id] = tuple(obligation_ids)
        if list(mapping) != sorted(mapping):
            raise CoverageDossierError("persisted gap mapping is not in stable gap-ID order")

        in_scope = {
            gap_id for gap_id, item in gap_by_id.items()
            if item["payload"]["scope_id"] == claim.scope_id
        }
        out_of_scope = tuple(sorted(set(gap_by_id) - in_scope))
        unreconciled = tuple(sorted(in_scope - set(mapping)))
        if payload["out_of_scope_gap_ids"] != list(out_of_scope):
            raise CoverageDossierError("persisted out-of-scope gap set is inconsistent with the inventory")
        if payload["unreconciled_gap_ids"] != list(unreconciled):
            raise CoverageDossierError("persisted unreconciled gap set is inconsistent with the inventory and mapping")

        status = EpistemicCoverageStatus(result["status"])
        if not snapshot_consistent:
            expected_overall = EpistemicCoverageStatus.UNKNOWN.value
        elif status in (
            EpistemicCoverageStatus.INVALIDATED,
            EpistemicCoverageStatus.CONTESTED,
            EpistemicCoverageStatus.UNKNOWN,
        ):
            expected_overall = status.value
        elif unreconciled:
            expected_overall = EpistemicCoverageStatus.INCOMPLETE.value
        else:
            expected_overall = status.value
        if payload["overall_status"] != expected_overall:
            raise CoverageDossierError("persisted overall status violates dossier precedence rules")

        current_epistemic = epistemic_store.snapshot_token()
        current_assurance = assurance_store.snapshot_token()
        source_matches = current_epistemic == epistemic_after and current_assurance == assurance_after
        replay_performed = False
        replay_matches = None
        inventory_matches = None
        if source_matches:
            current_inventory = epistemic_store.gap_records_snapshot()
            inventory_matches = _canonical(current_inventory) == _canonical(inventory)
            if not inventory_matches:
                raise CoverageDossierError("captured gap inventory does not match the unchanged epistemic ledger")
            replayed = evaluate_epistemic_coverage(
                claim.claim_id, manifest, assurance_store, epistemic_store
            )
            replay_performed = True
            replay_matches = _canonical(_result_payload(replayed)) == _canonical(result)
            if not replay_matches:
                raise CoverageDossierError("deterministic coverage replay differs from the persisted evaluation")

        return {
            "dossier_id": dossier_id,
            "dossier_ledger_integrity": True,
            "semantic_integrity": True,
            "source_snapshots_match": source_matches,
            "captured_gap_inventory_matches": inventory_matches,
            "replay_performed": replay_performed,
            "replay_matches": replay_matches,
            "snapshot_consistent_at_capture": snapshot_consistent,
            "overall_status_at_capture": expected_overall,
        }
    except CoverageDossierError:
        raise
    except Exception as exc:
        raise CoverageDossierError(
            f"coverage dossier semantic verification failed: {type(exc).__name__}: {exc}"
        ) from exc

"""M7.5.10 durable coverage dossiers and all-gap reconciliation.

The dossier ledger is independent from the epistemic and assurance ledgers.
Cross-ledger consistency is optimistic (before/after snapshot tokens), not atomic.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from .assurance import AssuranceClaim
from .assurance_store import AssuranceStore
from .coverage import (
    EpistemicCoverageManifest, EpistemicCoverageResult,
    EpistemicCoverageStatus, evaluate_epistemic_coverage,
)
from .rule_coverage import (
    RuleCoveragePlan, verify_rule_derived_manifest,
)
from .store import EpistemicStore


class CoverageDossierError(RuntimeError):
    """A durable coverage dossier cannot be established or verified."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _gap_inventory(store: EpistemicStore) -> tuple[dict, ...]:
    """Use the store's verified, transaction-scoped all-gap snapshot contract."""
    try:
        return store.gap_records_snapshot()
    except Exception as exc:
        raise CoverageDossierError("verified epistemic gap inventory is unavailable") from exc


@dataclass(frozen=True)
class CoverageDossier:
    dossier_id: str
    claim_id: str
    plan: dict
    manifest: dict
    gap_to_obligations: tuple[tuple[str, tuple[str, ...]], ...]
    gap_inventory: tuple[dict, ...]
    result: dict
    epistemic_token_before: tuple[int, str]
    epistemic_token_after: tuple[int, str]
    assurance_token_before: tuple[int, str]
    assurance_token_after: tuple[int, str]
    snapshot_consistent: bool
    unreconciled_gap_ids: tuple[str, ...]
    out_of_scope_gap_ids: tuple[str, ...]
    overall_status: str
    captured_at: str

    @property
    def dossier_sha256(self) -> str:
        return _digest(_canonical(asdict(self)))


class CoverageDossierStore:
    """Separate append-only, hash-chained store for coverage dossiers."""

    def __init__(self, database: str | Path, *, max_records: int = 10000):
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records < 1:
            raise ValueError("max_records must be a positive integer")
        self.max_records = max_records
        self._db = sqlite3.connect(str(database))
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS coverage_dossier_events (
                sequence INTEGER PRIMARY KEY,
                dossier_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TRIGGER IF NOT EXISTS coverage_dossier_no_update
            BEFORE UPDATE ON coverage_dossier_events
            BEGIN SELECT RAISE(ABORT, 'coverage dossier ledger is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS coverage_dossier_no_delete
            BEFORE DELETE ON coverage_dossier_events
            BEGIN SELECT RAISE(ABORT, 'coverage dossier ledger is append-only'); END;
        """)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "CoverageDossierStore":
        return self

    def __exit__(self, *_):
        self.close()

    def verify_integrity(self) -> bool:
        previous = "0" * 64
        rows = self._db.execute(
            "SELECT * FROM coverage_dossier_events ORDER BY sequence"
        ).fetchall()
        for expected, row in enumerate(rows, 1):
            payload_hash = _digest(row["payload"])
            material = f"{expected}\n{row['dossier_id']}\n{payload_hash}\n{previous}"
            calculated = _digest(material)
            if (
                row["sequence"] != expected
                or row["payload_sha256"] != payload_hash
                or row["previous_hash"] != previous
                or row["event_hash"] != calculated
            ):
                return False
            previous = calculated
        return True

    def record(self, dossier: CoverageDossier) -> bool:
        if not isinstance(dossier, CoverageDossier):
            raise TypeError("dossier must be a CoverageDossier")
        payload = _canonical(asdict(dossier))
        payload_hash = _digest(payload)
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            if not self.verify_integrity():
                raise CoverageDossierError("dossier ledger integrity failure; refusing write")
            old = self._db.execute(
                "SELECT payload_sha256 FROM coverage_dossier_events WHERE dossier_id = ?",
                (dossier.dossier_id,),
            ).fetchone()
            if old:
                if old["payload_sha256"] != payload_hash:
                    raise CoverageDossierError("dossier ID reused with different content")
                return False
            sequence = self._db.execute(
                "SELECT COUNT(*) AS n FROM coverage_dossier_events"
            ).fetchone()["n"] + 1
            if sequence > self.max_records:
                raise CoverageDossierError("dossier storage bound reached; no history was removed")
            previous_row = self._db.execute(
                "SELECT event_hash FROM coverage_dossier_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = previous_row["event_hash"] if previous_row else "0" * 64
            material = f"{sequence}\n{dossier.dossier_id}\n{payload_hash}\n{previous}"
            event_hash = _digest(material)
            self._db.execute(
                "INSERT INTO coverage_dossier_events VALUES (?, ?, ?, ?, ?, ?)",
                (sequence, dossier.dossier_id, payload, payload_hash, previous, event_hash),
            )
        return True

    def get(self, dossier_id: str) -> dict | None:
        if not self.verify_integrity():
            raise CoverageDossierError("dossier ledger integrity failure")
        row = self._db.execute(
            "SELECT payload FROM coverage_dossier_events WHERE dossier_id = ?",
            (dossier_id,),
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def history(self) -> tuple[dict, ...]:
        if not self.verify_integrity():
            raise CoverageDossierError("dossier ledger integrity failure")
        rows = self._db.execute(
            "SELECT sequence, dossier_id, payload, event_hash FROM coverage_dossier_events ORDER BY sequence"
        ).fetchall()
        return tuple({
            "sequence": row["sequence"], "dossier_id": row["dossier_id"],
            "payload": json.loads(row["payload"]), "event_hash": row["event_hash"],
        } for row in rows)


def _manifest_payload(manifest: EpistemicCoverageManifest) -> dict:
    data = asdict(manifest)
    data["obligations"] = [{
        "obligation_id": item.obligation_id,
        "disposition": item.disposition.value,
        "evidence_ids": list(item.evidence_ids),
        "gap_ids": list(item.gap_ids),
        "limitation": item.limitation,
    } for item in manifest.obligations]
    data["expected_obligation_ids"] = list(manifest.expected_obligation_ids)
    return data


def _result_payload(result: EpistemicCoverageResult) -> dict:
    data = asdict(result)
    data["status"] = result.status.value
    return data


def build_and_persist_coverage_dossier(
    *,
    dossier_id: str,
    claim: AssuranceClaim,
    plan: RuleCoveragePlan,
    manifest: EpistemicCoverageManifest,
    gap_to_obligations: Mapping[str, tuple[str, ...]],
    captured_at: str,
    assurance_store: AssuranceStore,
    epistemic_store: EpistemicStore,
    dossier_store: CoverageDossierStore,
) -> CoverageDossier:
    """Evaluate, reconcile every persisted gap, and append a recoverable dossier.

    Each in-scope persisted gap must be mapped to one or more derived
    obligations. Missing mappings are retained as explicit unreconciled gaps
    and contribute INCOMPLETE unless a stronger evaluator state (INVALIDATED,
    CONTESTED or UNKNOWN) applies. A mapping must also be reflected in the
    corresponding assessed CoverageObligation.gap_ids.
    """
    for name, value in (("dossier_id", dossier_id), ("captured_at", captured_at)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if not isinstance(gap_to_obligations, Mapping):
        raise TypeError("gap_to_obligations must be a mapping")
    verify_rule_derived_manifest(claim, plan, manifest)

    # Validate mapping shape first, but defer semantic checks until the
    # persisted inventory is available. This establishes deterministic error
    # precedence: existence -> claim scope -> derived-plan membership ->
    # assessed-manifest representation.
    mapping: dict[str, tuple[str, ...]] = {}
    for gap_id, obligation_ids in gap_to_obligations.items():
        if not isinstance(gap_id, str) or not gap_id.strip():
            raise CoverageDossierError("gap mapping contains an invalid gap ID")
        if not isinstance(obligation_ids, tuple) or not obligation_ids:
            raise CoverageDossierError(f"gap {gap_id} must map to a non-empty tuple of obligations")
        if any(not isinstance(item, str) or not item.strip() for item in obligation_ids):
            raise CoverageDossierError(f"gap {gap_id} contains an invalid obligation ID")
        normalized = tuple(sorted(set(obligation_ids)))
        if len(normalized) != len(obligation_ids):
            raise CoverageDossierError(f"gap {gap_id} contains duplicate obligation mappings")
        mapping[gap_id] = normalized

    epistemic_before = epistemic_store.snapshot_token()
    assurance_before = assurance_store.snapshot_token()
    gap_inventory = _gap_inventory(epistemic_store)
    gap_by_id = {item["gap_id"]: item for item in gap_inventory}

    absent_mapping_ids = set(mapping) - set(gap_by_id)
    if absent_mapping_ids:
        raise CoverageDossierError(
            "gap mapping references absent persisted gaps: " + ",".join(sorted(absent_mapping_ids))
        )

    out_of_scope_mapping_ids = {
        gap_id for gap_id in mapping
        if gap_by_id[gap_id]["payload"].get("scope_id") != claim.scope_id
    }
    if out_of_scope_mapping_ids:
        raise CoverageDossierError(
            "gap mapping references gaps outside the assurance claim scope: "
            + ",".join(sorted(out_of_scope_mapping_ids))
        )

    for gap_id, obligation_ids in mapping.items():
        outside_plan = set(obligation_ids) - set(plan.expected_obligation_ids)
        if outside_plan:
            raise CoverageDossierError(
                f"gap {gap_id} maps outside the derived obligation universe: "
                + ",".join(sorted(outside_plan))
            )

    assessed_gap_pairs = {
        (obligation.obligation_id, gap_id)
        for obligation in manifest.obligations
        for gap_id in obligation.gap_ids
    }
    for gap_id, obligation_ids in mapping.items():
        for obligation_id in obligation_ids:
            if (obligation_id, gap_id) not in assessed_gap_pairs:
                raise CoverageDossierError(
                    f"gap mapping {gap_id}->{obligation_id} is not represented in the manifest assessment"
                )

    in_scope_gap_ids = {
        gap_id for gap_id, item in gap_by_id.items()
        if item["payload"].get("scope_id") == claim.scope_id
    }
    out_of_scope_gap_ids = tuple(sorted(set(gap_by_id) - in_scope_gap_ids))
    unreconciled = tuple(sorted(in_scope_gap_ids - set(mapping)))

    result = evaluate_epistemic_coverage(
        claim.claim_id, manifest, assurance_store, epistemic_store
    )
    epistemic_after = epistemic_store.snapshot_token()
    assurance_after = assurance_store.snapshot_token()
    consistent = (
        epistemic_before == epistemic_after
        and assurance_before == assurance_after
    )

    if not consistent:
        overall = EpistemicCoverageStatus.UNKNOWN.value
    elif result.status is EpistemicCoverageStatus.INVALIDATED:
        overall = EpistemicCoverageStatus.INVALIDATED.value
    elif result.status is EpistemicCoverageStatus.CONTESTED:
        overall = EpistemicCoverageStatus.CONTESTED.value
    elif result.status is EpistemicCoverageStatus.UNKNOWN:
        overall = EpistemicCoverageStatus.UNKNOWN.value
    elif unreconciled:
        overall = EpistemicCoverageStatus.INCOMPLETE.value
    else:
        overall = result.status.value

    dossier = CoverageDossier(
        dossier_id=dossier_id,
        claim_id=claim.claim_id,
        plan=asdict(plan),
        manifest=_manifest_payload(manifest),
        gap_to_obligations=tuple(sorted(mapping.items())),
        gap_inventory=gap_inventory,
        result=_result_payload(result),
        epistemic_token_before=epistemic_before,
        epistemic_token_after=epistemic_after,
        assurance_token_before=assurance_before,
        assurance_token_after=assurance_after,
        snapshot_consistent=consistent,
        unreconciled_gap_ids=unreconciled,
        out_of_scope_gap_ids=out_of_scope_gap_ids,
        overall_status=overall,
        captured_at=captured_at,
    )
    dossier_store.record(dossier)
    return dossier


def verify_dossier_against_current_stores(
    dossier_id: str,
    *,
    assurance_store: AssuranceStore,
    epistemic_store: EpistemicStore,
    dossier_store: CoverageDossierStore,
) -> dict:
    """Verify dossier-ledger integrity and report whether source ledgers still match."""
    payload = dossier_store.get(dossier_id)
    if payload is None:
        raise CoverageDossierError("coverage dossier does not exist")
    current_epistemic = epistemic_store.snapshot_token()
    current_assurance = assurance_store.snapshot_token()
    return {
        "dossier_id": dossier_id,
        "dossier_ledger_integrity": dossier_store.verify_integrity(),
        "capture_was_consistent": payload["snapshot_consistent"],
        "current_epistemic_snapshot_matches": list(current_epistemic) == payload["epistemic_token_after"],
        "current_assurance_snapshot_matches": list(current_assurance) == payload["assurance_token_after"],
        "unreconciled_gap_ids": payload["unreconciled_gap_ids"],
        "out_of_scope_gap_ids": payload["out_of_scope_gap_ids"],
        "overall_status_at_capture": payload["overall_status"],
    }

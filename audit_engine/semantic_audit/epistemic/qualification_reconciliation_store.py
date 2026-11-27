"""M7.5.18 persistent qualification reconciliation and historical invalidation.

The ledger stores immutable reconciliation inputs and results. It records
invalidation events without rewriting historical records. Semantic replay
still requires the caller to supply the original verification context and
source snapshot; the ledger is not an external trust anchor.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from .assurance import AssuranceClaim
from .coverage import EpistemicCoverageManifest
from .qualification_reconciliation import (
    verify_qualification_obligation_reconciliation,
)
from .rule_coverage import RuleCoveragePlan

SCHEMA = "ae32c/persistent-qualification-reconciliation/v1"
EVENT_SCHEMA = "ae32c/qualification-reconciliation-ledger-event/v1"
_CONTEXT_KEYS = (
    "source_snapshot_id",
    "plan_sha256",
    "rule_registry_sha256",
    "coverage_manifest_sha256",
    "contract_registry_sha256",
    "aggregation_policy_registry_sha256",
    "qualification_sha256",
    "observation_bundle_sha256",
)


class QualificationReconciliationStoreError(RuntimeError):
    """Persistent qualification reconciliation cannot be safely stored."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False) + "\n"


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _context(reconciliation: Mapping[str, Any],
             qualification: Mapping[str, Any],
             bundle: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source_snapshot_id": reconciliation.get("source_snapshot_id"),
        "plan_sha256": reconciliation.get("plan_sha256"),
        "rule_registry_sha256": reconciliation.get("rule_registry_sha256"),
        "coverage_manifest_sha256": reconciliation.get("coverage_manifest_sha256"),
        "contract_registry_sha256": qualification.get("contract_registry_sha256"),
        "aggregation_policy_registry_sha256": reconciliation.get(
            "aggregation_policy_registry_sha256"),
        "qualification_sha256": qualification.get("qualification_sha256"),
        "observation_bundle_sha256": bundle.get("bundle_sha256"),
    }


def qualification_reconciliation_context(
    reconciliation: Mapping[str, Any],
    qualification: Mapping[str, Any],
    observation_bundle: Mapping[str, Any],
) -> dict[str, str]:
    """Build the exact eight-field currentness token used by invalidation."""
    context = _context(reconciliation, qualification, observation_bundle)
    if any(not isinstance(context.get(key), str) or not context[key].strip()
           for key in _CONTEXT_KEYS):
        raise ValueError("reconciliation_context_incomplete")
    return context


def _validate_envelope(envelope: Mapping[str, Any]) -> None:
    if envelope.get("schema") != SCHEMA:
        raise QualificationReconciliationStoreError("record_schema_invalid")
    reconciliation = envelope.get("reconciliation")
    qualification = envelope.get("qualification")
    bundle = envelope.get("observation_bundle")
    if not all(isinstance(x, Mapping) for x in (reconciliation, qualification, bundle)):
        raise QualificationReconciliationStoreError("record_payload_missing")
    reconciliation_payload = {
        key: value for key, value in reconciliation.items()
        if key != "reconciliation_sha256"
    }
    qualification_payload = {
        key: value for key, value in qualification.items()
        if key != "qualification_sha256"
    }
    bundle_payload = {
        key: value for key, value in bundle.items() if key != "bundle_sha256"
    }
    record_id = reconciliation.get("reconciliation_sha256")
    if record_id != _digest(reconciliation_payload):
        raise QualificationReconciliationStoreError("reconciliation_digest_mismatch")
    if qualification.get("qualification_sha256") != _digest(qualification_payload):
        raise QualificationReconciliationStoreError("qualification_digest_mismatch")
    if bundle.get("bundle_sha256") != _digest(bundle_payload):
        raise QualificationReconciliationStoreError("observation_bundle_digest_mismatch")
    if reconciliation.get("qualification_sha256") != qualification.get("qualification_sha256"):
        raise QualificationReconciliationStoreError("qualification_reference_mismatch")
    if reconciliation.get("observation_bundle_sha256") != bundle.get("bundle_sha256"):
        raise QualificationReconciliationStoreError("observation_bundle_reference_mismatch")
    if qualification.get("observation_bundle_sha256") != bundle.get("bundle_sha256"):
        raise QualificationReconciliationStoreError("qualification_bundle_binding_mismatch")
    if reconciliation.get("source_snapshot_id") != qualification.get("source_snapshot_id"):
        raise QualificationReconciliationStoreError("source_snapshot_binding_mismatch")
    if reconciliation.get("source_snapshot_id") != bundle.get("source_snapshot_id"):
        raise QualificationReconciliationStoreError("bundle_source_snapshot_binding_mismatch")
    context = _context(reconciliation, qualification, bundle)
    if envelope.get("context") != context:
        raise QualificationReconciliationStoreError("record_context_mismatch")
    if any(not isinstance(context.get(key), str) or not context[key].strip()
           for key in _CONTEXT_KEYS):
        raise QualificationReconciliationStoreError("record_context_incomplete")
    if envelope.get("record_id") != record_id:
        raise QualificationReconciliationStoreError("record_identity_mismatch")


def _invalidation_reasons(record_context: Mapping[str, str],
                          current_context: Mapping[str, str]) -> list[str]:
    labels = {
        "source_snapshot_id": "SOURCE_SNAPSHOT_CHANGED",
        "plan_sha256": "RULE_PLAN_CHANGED",
        "rule_registry_sha256": "RULE_CONTRACT_REGISTRY_CHANGED",
        "coverage_manifest_sha256": "COVERAGE_MANIFEST_CHANGED",
        "contract_registry_sha256": "SEMANTIC_CONTRACT_REGISTRY_CHANGED",
        "aggregation_policy_registry_sha256": "AGGREGATION_POLICY_CHANGED",
        "qualification_sha256": "QUALIFICATION_CHANGED",
        "observation_bundle_sha256": "OBSERVATION_BUNDLE_CHANGED",
    }
    return [labels[key] for key in _CONTEXT_KEYS
            if record_context.get(key) != current_context.get(key)]


class QualificationReconciliationStore:
    """Append-only SQLite event ledger for reconciliations and invalidations."""

    def __init__(self, database: str | Path, *, max_records: int = 10000):
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records < 1:
            raise ValueError("max_records_must_be_positive_integer")
        self.max_records = max_records
        self._db = sqlite3.connect(str(database))
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS qualification_reconciliation_events (
                sequence INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TRIGGER IF NOT EXISTS qualification_reconciliation_no_update
            BEFORE UPDATE ON qualification_reconciliation_events
            BEGIN SELECT RAISE(ABORT, 'qualification reconciliation ledger is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS qualification_reconciliation_no_delete
            BEFORE DELETE ON qualification_reconciliation_events
            BEGIN SELECT RAISE(ABORT, 'qualification reconciliation ledger is append-only'); END;
        """)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "QualificationReconciliationStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _append(self, event_id: str, event_type: str, payload: Mapping[str, Any]) -> bool:
        serialized = _canonical(dict(payload))
        payload_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            if not self.verify_integrity():
                raise QualificationReconciliationStoreError("ledger_integrity_failure")
            prior = self._db.execute(
                "SELECT payload_sha256,event_type FROM qualification_reconciliation_events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if prior:
                if prior["payload_sha256"] != payload_hash or prior["event_type"] != event_type:
                    raise QualificationReconciliationStoreError("event_identity_conflict")
                return False
            sequence = self._db.execute(
                "SELECT COUNT(*) FROM qualification_reconciliation_events"
            ).fetchone()[0] + 1
            if sequence > self.max_records:
                raise QualificationReconciliationStoreError("ledger_storage_limit_reached")
            last = self._db.execute(
                "SELECT event_hash FROM qualification_reconciliation_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = last["event_hash"] if last else "0" * 64
            event_hash = hashlib.sha256(
                f"{sequence}\n{event_id}\n{event_type}\n{payload_hash}\n{previous}".encode()
            ).hexdigest()
            self._db.execute(
                "INSERT INTO qualification_reconciliation_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sequence, event_id, event_type, serialized, payload_hash, previous, event_hash),
            )
        return True

    def verify_integrity(self) -> bool:
        previous = "0" * 64
        records: dict[str, Mapping[str, Any]] = {}
        rows = self._db.execute(
            "SELECT * FROM qualification_reconciliation_events ORDER BY sequence"
        ).fetchall()
        for expected, row in enumerate(rows, 1):
            payload_text = row["payload"]
            payload_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
            event_hash = hashlib.sha256(
                f"{expected}\n{row['event_id']}\n{row['event_type']}\n{payload_hash}\n{previous}".encode()
            ).hexdigest()
            try:
                payload = json.loads(payload_text)
                if _canonical(payload) != payload_text:
                    return False
                if row["event_type"] == "RECONCILIATION":
                    _validate_envelope(payload)
                    if row["event_id"] != payload["record_id"]:
                        return False
                    records[row["event_id"]] = payload
                elif row["event_type"] == "INVALIDATION":
                    if payload.get("schema") != EVENT_SCHEMA:
                        return False
                    record = records.get(payload.get("record_id"))
                    if record is None:
                        return False
                    current = payload.get("current_context")
                    if not isinstance(current, dict) or set(current) != set(_CONTEXT_KEYS):
                        return False
                    if any(not isinstance(current.get(key), str) or not current[key].strip()
                           for key in _CONTEXT_KEYS):
                        return False
                    reasons = _invalidation_reasons(record["context"], current)
                    body = {key: value for key, value in payload.items()
                            if key != "invalidation_id"}
                    if (not reasons or payload.get("reason_codes") != reasons
                            or payload.get("invalidation_id") != _digest(body)
                            or row["event_id"] != payload.get("invalidation_id")):
                        return False
                else:
                    return False
            except (TypeError, ValueError, KeyError, QualificationReconciliationStoreError):
                return False
            if (row["sequence"] != expected or row["payload_sha256"] != payload_hash
                    or row["previous_hash"] != previous or row["event_hash"] != event_hash):
                return False
            previous = event_hash
        return True

    def record(self, reconciliation: Mapping[str, Any],
               qualification: Mapping[str, Any],
               observation_bundle: Mapping[str, Any]) -> bool:
        """Append a content-bound record after the caller has independently replayed it.

        Use persist_verified_qualification_reconciliation for the replay-enforcing
        public path. This lower-level method checks identity and cross-artifact links.
        """
        if not all(isinstance(x, Mapping)
                   for x in (reconciliation, qualification, observation_bundle)):
            raise TypeError("reconciliation_qualification_and_bundle_must_be_mappings")
        record_id = reconciliation.get("reconciliation_sha256")
        envelope = {
            "schema": SCHEMA,
            "record_id": record_id,
            "reconciliation": dict(reconciliation),
            "qualification": dict(qualification),
            "observation_bundle": dict(observation_bundle),
            "context": _context(reconciliation, qualification, observation_bundle),
        }
        _validate_envelope(envelope)
        return self._append(str(record_id), "RECONCILIATION", envelope)

    def get(self, record_id: str) -> dict[str, Any] | None:
        if not self.verify_integrity():
            raise QualificationReconciliationStoreError("ledger_integrity_failure")
        row = self._db.execute(
            "SELECT payload FROM qualification_reconciliation_events "
            "WHERE event_id=? AND event_type='RECONCILIATION'", (record_id,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def invalidate(self, record_id: str,
                   current_context: Mapping[str, str]) -> dict[str, Any]:
        """Append an invalidation event; never mutate or delete the historical record."""
        envelope = self.get(record_id)
        if envelope is None:
            raise QualificationReconciliationStoreError("reconciliation_record_not_found")
        if not isinstance(current_context, Mapping) or set(current_context) != set(_CONTEXT_KEYS):
            raise ValueError("current_context_must_contain_exactly_the_declared_context_keys")
        current = dict(current_context)
        if any(not isinstance(current.get(key), str) or not current[key].strip()
               for key in _CONTEXT_KEYS):
            raise ValueError("current_context_values_must_be_non_empty_strings")
        reasons = _invalidation_reasons(envelope["context"], current)
        if not reasons:
            return {"invalidated": False, "reason_codes": [], "invalidation_id": None}
        body = {"schema": EVENT_SCHEMA, "record_id": record_id,
                "current_context": current, "reason_codes": reasons}
        invalidation_id = _digest(body)
        payload = {**body, "invalidation_id": invalidation_id}
        inserted = self._append(invalidation_id, "INVALIDATION", payload)
        return {"invalidated": True, "reason_codes": reasons,
                "invalidation_id": invalidation_id, "event_appended": inserted}

    def invalidation_history(self, record_id: str) -> tuple[dict[str, Any], ...]:
        if not self.verify_integrity():
            raise QualificationReconciliationStoreError("ledger_integrity_failure")
        rows = self._db.execute(
            "SELECT payload FROM qualification_reconciliation_events "
            "WHERE event_type='INVALIDATION' ORDER BY sequence"
        ).fetchall()
        return tuple(item for row in rows
                     if (item := json.loads(row["payload"])).get("record_id") == record_id)

    def history(self) -> tuple[dict[str, Any], ...]:
        if not self.verify_integrity():
            raise QualificationReconciliationStoreError("ledger_integrity_failure")
        rows = self._db.execute(
            "SELECT sequence,event_id,event_type,event_hash FROM qualification_reconciliation_events "
            "ORDER BY sequence"
        ).fetchall()
        return tuple(dict(row) for row in rows)


def persist_verified_qualification_reconciliation(
    store: QualificationReconciliationStore,
    reconciliation: Mapping[str, Any],
    qualification: Mapping[str, Any],
    observation_bundle: Mapping[str, Any],
    *,
    claim: AssuranceClaim,
    plan: RuleCoveragePlan,
    coverage_manifest: EpistemicCoverageManifest,
    source_manifest: Mapping[str, Any],
    repository_root: str | Path,
    defeaters: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Semantically replay, then append the immutable reconciliation envelope."""
    replay = verify_qualification_obligation_reconciliation(
        reconciliation, qualification, observation_bundle,
        claim=claim, plan=plan, coverage_manifest=coverage_manifest,
        source_manifest=source_manifest, repository_root=repository_root,
        defeaters=defeaters,
    )
    inserted = store.record(reconciliation, qualification, observation_bundle)
    return {**replay, "persisted": True, "inserted": inserted,
            "record_id": reconciliation["reconciliation_sha256"]}


def verify_persisted_qualification_reconciliation(
    record_id: str,
    *,
    store: QualificationReconciliationStore,
    claim: AssuranceClaim,
    plan: RuleCoveragePlan,
    coverage_manifest: EpistemicCoverageManifest,
    source_manifest: Mapping[str, Any],
    repository_root: str | Path,
    defeaters: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Replay a stored historical record against caller-supplied source context."""
    envelope = store.get(record_id)
    if envelope is None:
        raise QualificationReconciliationStoreError("reconciliation_record_not_found")
    replay = verify_qualification_obligation_reconciliation(
        envelope["reconciliation"], envelope["qualification"],
        envelope["observation_bundle"], claim=claim, plan=plan,
        coverage_manifest=coverage_manifest, source_manifest=source_manifest,
        repository_root=repository_root, defeaters=defeaters,
    )
    return {**replay, "record_id": record_id, "ledger_integrity": True,
            "historical_replay": True}

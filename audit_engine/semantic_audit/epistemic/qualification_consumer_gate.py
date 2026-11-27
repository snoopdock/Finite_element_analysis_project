"""M7.5.20 explicit downstream currentness preflight and usage ledger.

A consumer preflight records whether a persisted qualification reconciliation
passed the M7.5.19 currentness gate. It is not evidence acceptance, semantic
replay, assurance evaluation, or authorization.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from .qualification_reconciliation_store import (
    QualificationReconciliationStore,
    QualificationReconciliationStoreError,
    evaluate_persisted_qualification_reconciliation_currentness,
)

SCHEMA = "ae32c/qualification-reconciliation-consumer-check/v1"


class QualificationConsumerGateError(RuntimeError):
    """A downstream currentness preflight cannot be safely recorded."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False) + "\n"


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_must_be_a_non_empty_string")
    return value.strip()


class QualificationConsumerCheckStore:
    """Append-only, hash-chained ledger of downstream currentness preflights."""

    def __init__(self, database: str | Path, *, max_records: int = 10000):
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records < 1:
            raise ValueError("max_records_must_be_positive_integer")
        self.max_records = max_records
        self._db = sqlite3.connect(str(database))
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS qualification_consumer_checks (
                sequence INTEGER PRIMARY KEY,
                check_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TRIGGER IF NOT EXISTS qualification_consumer_checks_no_update
            BEFORE UPDATE ON qualification_consumer_checks
            BEGIN SELECT RAISE(ABORT, 'qualification consumer ledger is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS qualification_consumer_checks_no_delete
            BEFORE DELETE ON qualification_consumer_checks
            BEGIN SELECT RAISE(ABORT, 'qualification consumer ledger is append-only'); END;
        """)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "QualificationConsumerCheckStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def verify_integrity(self) -> bool:
        previous = "0" * 64
        rows = self._db.execute(
            "SELECT * FROM qualification_consumer_checks ORDER BY sequence"
        ).fetchall()
        for expected, row in enumerate(rows, 1):
            payload_text = row["payload"]
            payload_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
            event_hash = hashlib.sha256(
                f"{expected}\n{row['check_id']}\n{payload_hash}\n{previous}".encode()
            ).hexdigest()
            try:
                payload = json.loads(payload_text)
                if _canonical(payload) != payload_text:
                    return False
                body = {key: value for key, value in payload.items()
                        if key != "check_id"}
                if (
                    payload.get("schema") != SCHEMA
                    or payload.get("check_id") != _digest(body)
                    or row["check_id"] != payload.get("check_id")
                    or payload.get("currentness_status") not in {"CURRENT", "INVALIDATED"}
                    or payload.get("consumer_preflight_status") != (
                        "CURRENTNESS_CONFIRMED"
                        if payload.get("currentness_status") == "CURRENT"
                        else "BLOCKED_INVALIDATED"
                    )
                    or payload.get("downstream_authorization") != "NOT_EVALUATED"
                    or not all(isinstance(payload.get(key), str) and payload[key].strip()
                               for key in ("record_id", "consumer_id", "operation"))
                    or not isinstance(payload.get("invalidation_ids"), list)
                    or not isinstance(payload.get("reason_codes"), list)
                    or not isinstance(payload.get("current_context_sha256"), str)
                    or len(payload["current_context_sha256"]) != 64
                ):
                    return False
            except (TypeError, ValueError, KeyError):
                return False
            if (
                row["sequence"] != expected
                or row["payload_sha256"] != payload_hash
                or row["previous_hash"] != previous
                or row["event_hash"] != event_hash
            ):
                return False
            previous = event_hash
        return True

    def record(self, payload: Mapping[str, Any]) -> bool:
        if not isinstance(payload, Mapping):
            raise TypeError("consumer_check_payload_must_be_a_mapping")
        item = dict(payload)
        body = {key: value for key, value in item.items() if key != "check_id"}
        expected_id = _digest(body)
        if item.get("schema") != SCHEMA or item.get("check_id") != expected_id:
            raise QualificationConsumerGateError("consumer_check_identity_mismatch")
        serialized = _canonical(item)
        payload_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            if not self.verify_integrity():
                raise QualificationConsumerGateError("consumer_ledger_integrity_failure")
            prior = self._db.execute(
                "SELECT payload_sha256 FROM qualification_consumer_checks WHERE check_id=?",
                (expected_id,),
            ).fetchone()
            if prior:
                if prior["payload_sha256"] != payload_hash:
                    raise QualificationConsumerGateError("consumer_check_identity_conflict")
                return False
            sequence = self._db.execute(
                "SELECT COUNT(*) FROM qualification_consumer_checks"
            ).fetchone()[0] + 1
            if sequence > self.max_records:
                raise QualificationConsumerGateError("consumer_ledger_storage_limit_reached")
            last = self._db.execute(
                "SELECT event_hash FROM qualification_consumer_checks "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = last["event_hash"] if last else "0" * 64
            event_hash = hashlib.sha256(
                f"{sequence}\n{expected_id}\n{payload_hash}\n{previous}".encode()
            ).hexdigest()
            self._db.execute(
                "INSERT INTO qualification_consumer_checks VALUES (?, ?, ?, ?, ?, ?)",
                (sequence, expected_id, serialized, payload_hash, previous, event_hash),
            )
        return True

    def get(self, check_id: str) -> dict[str, Any] | None:
        if not self.verify_integrity():
            raise QualificationConsumerGateError("consumer_ledger_integrity_failure")
        row = self._db.execute(
            "SELECT payload FROM qualification_consumer_checks WHERE check_id=?",
            (check_id,),
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def history(self) -> tuple[dict[str, Any], ...]:
        if not self.verify_integrity():
            raise QualificationConsumerGateError("consumer_ledger_integrity_failure")
        rows = self._db.execute(
            "SELECT sequence,check_id,event_hash FROM qualification_consumer_checks "
            "ORDER BY sequence"
        ).fetchall()
        return tuple(dict(row) for row in rows)


def evaluate_qualification_reconciliation_for_consumer(
    record_id: str,
    *,
    consumer_id: str,
    operation: str,
    reconciliation_store: QualificationReconciliationStore,
    check_store: QualificationConsumerCheckStore,
    current_context: Mapping[str, str],
) -> dict[str, Any]:
    """Record a consumer preflight after the M7.5.19 gate has evaluated currentness.

    CURRENTNESS_CONFIRMED is only a currentness precondition. The caller must
    still perform semantic replay, evidence/assurance checks, and any separately
    governed authorization. Invoke immediately before use and bind the consumer
    operation to the same artifacts represented by current_context.
    """
    record_id = _required_text(record_id, "record_id")
    consumer_id = _required_text(consumer_id, "consumer_id")
    operation = _required_text(operation, "operation")
    if not isinstance(reconciliation_store, QualificationReconciliationStore):
        raise TypeError("reconciliation_store_must_be_a_QualificationReconciliationStore")
    if not isinstance(check_store, QualificationConsumerCheckStore):
        raise TypeError("check_store_must_be_a_QualificationConsumerCheckStore")
    if not isinstance(current_context, Mapping):
        raise TypeError("current_context_must_be_a_mapping")

    currentness = evaluate_persisted_qualification_reconciliation_currentness(
        record_id, store=reconciliation_store, current_context=current_context
    )
    body = {
        "schema": SCHEMA,
        "record_id": record_id,
        "consumer_id": consumer_id,
        "operation": operation,
        "current_context_sha256": _digest(dict(current_context)),
        "currentness_status": currentness["currentness_status"],
        "consumer_preflight_status": (
            "CURRENTNESS_CONFIRMED"
            if currentness["currentness_status"] == "CURRENT"
            else "BLOCKED_INVALIDATED"
        ),
        "invalidation_ids": list(currentness["historical_invalidation_ids"]),
        "reason_codes": list(currentness["historical_reason_codes"]),
        "downstream_authorization": "NOT_EVALUATED",
    }
    check_id = _digest(body)
    payload = {**body, "check_id": check_id}
    inserted = check_store.record(payload)
    return {
        **payload,
        "check_event_appended": inserted,
        "reconciliation_ledger_integrity": currentness["ledger_integrity"],
        "semantic_replay_performed": False,
        "current_context_matches_record": currentness["current_context_matches_record"],
    }

"""Append-only SQLite event store for epistemic assertions and knowledge gaps.

The store is intentionally independent of legacy knowledge_graph.epistemic_states.
It persists descriptive records only and never makes audit or authorization decisions.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any

from .contracts import EvidenceAssertion, KnowledgeGap, GapState


class StoreError(RuntimeError):
    """Base class for epistemic store failures."""


class DuplicateRecordError(StoreError):
    """A stable record ID was reused for different content."""


class RevisionConflictError(StoreError):
    """The caller's expected gap revision is not the current revision."""


class InvalidTransitionError(StoreError):
    """A knowledge-gap lifecycle transition is not permitted."""


class StorageLimitError(StoreError):
    """The configured event bound was reached; no records were discarded."""


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return _json_value(asdict(value))
    return value


def _canonical_payload(record: Any) -> str:
    return json.dumps(_json_value(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


_ALLOWED_GAP_TRANSITIONS = {
    GapState.OPEN: {GapState.INVESTIGATING, GapState.BLOCKED, GapState.RESOLVED, GapState.ACCEPTED_RESIDUAL},
    GapState.INVESTIGATING: {GapState.BLOCKED, GapState.RESOLVED, GapState.ACCEPTED_RESIDUAL},
    GapState.BLOCKED: {GapState.INVESTIGATING, GapState.RESOLVED, GapState.ACCEPTED_RESIDUAL},
    GapState.RESOLVED: set(),
    GapState.ACCEPTED_RESIDUAL: set(),
}


class EpistemicStore:
    """SQLite event ledger with immutable rows and a verifiable hash chain.

    max_events is a hard admission bound, not a retention policy. Reaching it raises
    StorageLimitError. The store never truncates, overwrites, or silently deletes data.
    """

    def __init__(self, database: str | Path, *, max_events: int = 100_000) -> None:
        if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1:
            raise ValueError("max_events must be a positive integer")
        self.database = str(database)
        self.max_events = max_events
        self._connection = sqlite3.connect(self.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "EpistemicStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def _initialize(self) -> None:
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS epistemic_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                record_type TEXT NOT NULL CHECK(record_type IN ('assertion', 'gap')),
                record_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 1),
                payload TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE,
                UNIQUE(record_type, record_id, revision)
            );
            CREATE TRIGGER IF NOT EXISTS epistemic_events_no_update
            BEFORE UPDATE ON epistemic_events BEGIN
                SELECT RAISE(ABORT, 'epistemic event ledger is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS epistemic_events_no_delete
            BEFORE DELETE ON epistemic_events BEGIN
                SELECT RAISE(ABORT, 'epistemic event ledger is append-only');
            END;
        """)
        self._connection.commit()

    def _append(self, record_type: str, record_id: str, revision: int, payload: str) -> bool:
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        event_id = f"{record_type}:{record_id}:{revision}"
        with self._connection:
            existing = self._connection.execute(
                "SELECT payload_sha256 FROM epistemic_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if existing:
                if existing["payload_sha256"] != payload_hash:
                    raise DuplicateRecordError(f"{event_id} already exists with different content")
                return False

            count = self._connection.execute("SELECT COUNT(*) AS n FROM epistemic_events").fetchone()["n"]
            if count >= self.max_events:
                raise StorageLimitError(
                    f"event limit {self.max_events} reached; existing history was retained"
                )
            previous = self._connection.execute(
                "SELECT event_hash FROM epistemic_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous_hash = previous["event_hash"] if previous else "0" * 64
            sequence = count + 1
            event_material = f"{sequence}\n{event_id}\n{payload_hash}\n{previous_hash}"
            event_hash = hashlib.sha256(event_material.encode("utf-8")).hexdigest()
            self._connection.execute(
                """INSERT INTO epistemic_events
                   (event_id, record_type, record_id, revision, payload,
                    payload_sha256, previous_hash, event_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, record_type, record_id, revision, payload,
                 payload_hash, previous_hash, event_hash),
            )
            return True

    def record_assertion(self, assertion: EvidenceAssertion) -> bool:
        if not isinstance(assertion, EvidenceAssertion):
            raise TypeError("assertion must be an EvidenceAssertion")
        return self._append("assertion", assertion.assertion_id, 1, _canonical_payload(assertion))

    def record_gap(self, gap: KnowledgeGap) -> bool:
        if not isinstance(gap, KnowledgeGap):
            raise TypeError("gap must be a KnowledgeGap")
        return self._append("gap", gap.gap_id, 1, _canonical_payload(gap))

    def transition_gap(self, gap: KnowledgeGap, *, expected_revision: int) -> int:
        """Append a new gap revision; the prior revision remains immutable."""
        if not isinstance(gap, KnowledgeGap):
            raise TypeError("gap must be a KnowledgeGap")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        current = self.latest_gap(gap.gap_id)
        if current is None:
            raise RevisionConflictError(f"gap {gap.gap_id} has no initial record")
        if current["revision"] != expected_revision:
            raise RevisionConflictError(
                f"expected revision {expected_revision}, current revision is {current['revision']}"
            )
        old_state = GapState(current["payload"]["state"])
        if gap.state not in _ALLOWED_GAP_TRANSITIONS[old_state]:
            raise InvalidTransitionError(f"transition {old_state.value} -> {gap.state.value} is not permitted")
        self._append("gap", gap.gap_id, expected_revision + 1, _canonical_payload(gap))
        return expected_revision + 1

    def latest_gap(self, gap_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            """SELECT revision, payload FROM epistemic_events
               WHERE record_type = 'gap' AND record_id = ?
               ORDER BY revision DESC LIMIT 1""", (gap_id,)
        ).fetchone()
        if row is None:
            return None
        return {"revision": row["revision"], "payload": json.loads(row["payload"])}

    def gap_history(self, gap_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """SELECT sequence, revision, payload, event_hash FROM epistemic_events
               WHERE record_type = 'gap' AND record_id = ? ORDER BY revision""", (gap_id,)
        ).fetchall()
        return [
            {"sequence": row["sequence"], "revision": row["revision"],
             "payload": json.loads(row["payload"]), "event_hash": row["event_hash"]}
            for row in rows
        ]

    def assertion_history(self, assertion_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """SELECT sequence, payload, event_hash FROM epistemic_events
               WHERE record_type = 'assertion' AND record_id = ? ORDER BY sequence""",
            (assertion_id,),
        ).fetchall()
        return [
            {"sequence": row["sequence"], "payload": json.loads(row["payload"]),
             "event_hash": row["event_hash"]}
            for row in rows
        ]

    def event_count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) AS n FROM epistemic_events"
        ).fetchone()["n"]

    def verify_integrity(self) -> bool:
        """Verify sequence continuity, payload digests, and the full event hash chain."""
        rows = self._connection.execute(
            "SELECT * FROM epistemic_events ORDER BY sequence"
        ).fetchall()
        previous_hash = "0" * 64
        for expected_sequence, row in enumerate(rows, start=1):
            if row["sequence"] != expected_sequence or row["previous_hash"] != previous_hash:
                return False
            payload_hash = hashlib.sha256(row["payload"].encode("utf-8")).hexdigest()
            if payload_hash != row["payload_sha256"]:
                return False
            material = f"{expected_sequence}\n{row['event_id']}\n{payload_hash}\n{previous_hash}"
            calculated = hashlib.sha256(material.encode("utf-8")).hexdigest()
            if calculated != row["event_hash"]:
                return False
            previous_hash = calculated
        return True

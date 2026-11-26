"""Bounded append-only hash-chained persistence for assurance argument records."""
from __future__ import annotations
import hashlib, json, sqlite3
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from .assurance import AssuranceClaim, ArgumentLink, Defeater, DefeaterEvent

class AssuranceStoreError(RuntimeError): pass
class AssuranceDuplicateError(AssuranceStoreError): pass
class AssuranceStorageLimitError(AssuranceStoreError): pass

_RECORDS = {"claim": AssuranceClaim, "link": ArgumentLink, "defeater": Defeater, "defeater_event": DefeaterEvent}

def _value(v: Any):
    if isinstance(v, Enum): return v.value
    if isinstance(v, tuple): return [_value(x) for x in v]
    if is_dataclass(v): return _value(asdict(v))
    return v

def _payload(v: Any) -> str:
    return json.dumps(_value(v), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

class AssuranceStore:
    """Independent append-only assurance ledger; it never updates or deletes rows."""
    def __init__(self, database: str | Path, *, max_events: int = 10000):
        if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1:
            raise ValueError("max_events must be a positive integer")
        self.max_events = max_events
        self._db = sqlite3.connect(str(database))
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
          CREATE TABLE IF NOT EXISTS assurance_events (
            sequence INTEGER PRIMARY KEY, event_type TEXT NOT NULL, record_id TEXT NOT NULL,
            payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL, previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL UNIQUE, UNIQUE(event_type, record_id));
          CREATE TRIGGER IF NOT EXISTS assurance_no_update BEFORE UPDATE ON assurance_events
            BEGIN SELECT RAISE(ABORT, 'assurance ledger is append-only'); END;
          CREATE TRIGGER IF NOT EXISTS assurance_no_delete BEFORE DELETE ON assurance_events
            BEGIN SELECT RAISE(ABORT, 'assurance ledger is append-only'); END;
        """)
        self._db.commit()
    def close(self): self._db.close()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()
    def verify_integrity(self) -> bool:
        previous = "0" * 64
        rows = self._db.execute("SELECT * FROM assurance_events ORDER BY sequence").fetchall()
        for sequence, row in enumerate(rows, 1):
            digest = hashlib.sha256(row["payload"].encode()).hexdigest()
            material = f"{sequence}\n{row['event_type']}\n{row['record_id']}\n{digest}\n{previous}"
            calculated = hashlib.sha256(material.encode()).hexdigest()
            if row["sequence"] != sequence or row["payload_sha256"] != digest or row["previous_hash"] != previous or row["event_hash"] != calculated:
                return False
            previous = calculated
        return True
    def record(self, record: Any) -> bool:
        kind = next((name for name, cls in _RECORDS.items() if isinstance(record, cls)), None)
        if kind is None: raise TypeError("unsupported assurance record type")
        identity = {"claim":"claim_id", "link":"link_id", "defeater":"defeater_id", "defeater_event":"event_id"}[kind]
        record_id = getattr(record, identity)
        payload = _payload(record)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            if not self.verify_integrity(): raise AssuranceStoreError("assurance ledger integrity failure")
            old = self._db.execute("SELECT payload_sha256 FROM assurance_events WHERE event_type=? AND record_id=?", (kind, record_id)).fetchone()
            if old:
                if old["payload_sha256"] != digest: raise AssuranceDuplicateError("stable record ID reused with different content")
                return False
            sequence = self._db.execute("SELECT COUNT(*) AS n FROM assurance_events").fetchone()["n"] + 1
            if sequence > self.max_events: raise AssuranceStorageLimitError("assurance event bound reached; no records removed")
            row = self._db.execute("SELECT event_hash FROM assurance_events ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = row["event_hash"] if row else "0" * 64
            material = f"{sequence}\n{kind}\n{record_id}\n{digest}\n{previous}"
            event_hash = hashlib.sha256(material.encode()).hexdigest()
            self._db.execute("INSERT INTO assurance_events VALUES (?, ?, ?, ?, ?, ?, ?)", (sequence, kind, record_id, payload, digest, previous, event_hash))
        return True
    def history(self, event_type: str | None = None) -> list[dict[str, Any]]:
        if event_type is not None and event_type not in _RECORDS: raise ValueError("unknown event type")
        rows = (self._db.execute("SELECT * FROM assurance_events ORDER BY sequence").fetchall()
                if event_type is None else self._db.execute("SELECT * FROM assurance_events WHERE event_type=? ORDER BY sequence", (event_type,)).fetchall())
        return [dict(row) for row in rows]

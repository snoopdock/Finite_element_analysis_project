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

from .contracts import (
    CompletenessClaim, EvidenceAssertion, KnowledgeGap, GapState,
    ProvenanceDependency, ProvenanceInvalidation, ProvenanceManifest,
    FreshnessResult, FreshnessStatus,
)


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
        existing = self._connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'epistemic_events'"
        ).fetchone()
        schema_sql = existing["sql"] or "" if existing else ""
        if existing and any(f"'{kind}'" not in schema_sql for kind in ("completeness", "dependency", "invalidation", "dependency_manifest")):
            # Migrate earlier append-only schemas without discarding or rehashing history.
            with self._connection:
                self._connection.execute("BEGIN IMMEDIATE")
                self._connection.execute("DROP TRIGGER IF EXISTS epistemic_events_no_update")
                self._connection.execute("DROP TRIGGER IF EXISTS epistemic_events_no_delete")
                self._connection.execute(
                    "ALTER TABLE epistemic_events RENAME TO epistemic_events_legacy"
                )
                self._connection.execute("""
                    CREATE TABLE epistemic_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        record_type TEXT NOT NULL CHECK(record_type IN ('assertion', 'gap', 'completeness', 'dependency', 'invalidation', 'dependency_manifest')),
                        record_id TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK(revision >= 1),
                        payload TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        previous_hash TEXT NOT NULL,
                        event_hash TEXT NOT NULL UNIQUE,
                        UNIQUE(record_type, record_id, revision)
                    )
                """)
                self._connection.execute("""
                    INSERT INTO epistemic_events
                    (sequence, event_id, record_type, record_id, revision, payload,
                     payload_sha256, previous_hash, event_hash)
                    SELECT sequence, event_id, record_type, record_id, revision, payload,
                           payload_sha256, previous_hash, event_hash
                    FROM epistemic_events_legacy ORDER BY sequence
                """)
                self._connection.execute("DROP TABLE epistemic_events_legacy")

        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS epistemic_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                record_type TEXT NOT NULL CHECK(record_type IN ('assertion', 'gap', 'completeness', 'dependency', 'invalidation', 'dependency_manifest')),
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

    def _append(
        self, record_type: str, record_id: str, revision: int, payload: str,
        *, transaction_open: bool = False,
    ) -> bool:
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        event_id = f"{record_type}:{record_id}:{revision}"

        def append_locked() -> bool:
            if not self.verify_integrity():
                raise StoreError("event ledger integrity check failed; refusing further writes")
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

        if transaction_open:
            return append_locked()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            return append_locked()

    def record_assertion(self, assertion: EvidenceAssertion) -> bool:
        if not isinstance(assertion, EvidenceAssertion):
            raise TypeError("assertion must be an EvidenceAssertion")
        return self._append("assertion", assertion.assertion_id, 1, _canonical_payload(assertion))

    def record_gap(self, gap: KnowledgeGap) -> bool:
        if not isinstance(gap, KnowledgeGap):
            raise TypeError("gap must be a KnowledgeGap")
        return self._append("gap", gap.gap_id, 1, _canonical_payload(gap))

    def record_completeness_claim(self, claim: CompletenessClaim) -> bool:
        if not isinstance(claim, CompletenessClaim):
            raise TypeError("claim must be a CompletenessClaim")
        return self._append("completeness", claim.claim_id, 1, _canonical_payload(claim))

    def completeness_history(self, claim_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """SELECT sequence, payload, event_hash FROM epistemic_events
               WHERE record_type = 'completeness' AND record_id = ? ORDER BY sequence""",
            (claim_id,),
        ).fetchall()
        return [
            {"sequence": row["sequence"], "payload": json.loads(row["payload"]),
             "event_hash": row["event_hash"]}
            for row in rows
        ]

    def record_completeness_dependencies(self, claim: CompletenessClaim) -> tuple[str, ...]:
        """Declare the claim's snapshot, method and evidence provenance dependencies."""
        if not isinstance(claim, CompletenessClaim):
            raise TypeError("claim must be a CompletenessClaim")
        claim_node = f"claim:{claim.claim_id}"
        edges: list[ProvenanceDependency] = []

        def add(dependent: str, dependency: str, kind: str, revision: str) -> None:
            edge_id = f"dep:{dependent}<-{dependency}:{kind}"
            edges.append(ProvenanceDependency(
                edge_id=edge_id, dependent_id=dependent, dependency_id=dependency,
                dependency_kind=kind, expected_revision=revision,
            ))

        snapshot_node = f"snapshot:{claim.source_snapshot_id}"
        add(claim_node, snapshot_node, "source_snapshot", claim.source_snapshot_id)
        add(claim_node, f"enumerator:{claim.enumeration_method}", "enumeration_method", claim.method_version)
        if claim.verification_method_id:
            add(claim_node, f"verification:{claim.verification_method_id}",
                "verification_method", claim.verification_method_id)
        for ref in claim.evidence_refs:
            evidence_node = f"evidence:{ref.evidence_id}"
            add(claim_node, evidence_node, "evidence_reference", ref.evidence_id)
            add(evidence_node, f"snapshot:{ref.source_snapshot_id}",
                "evidence_snapshot", ref.source_snapshot_id)
            add(evidence_node, f"producer:{ref.producer_id}", "evidence_producer", ref.producer_id)
            add(evidence_node, f"method:{ref.method_id}", "evidence_method", ref.method_id)
            if ref.artifact_sha256:
                add(evidence_node, f"artifact-sha256:{ref.artifact_sha256}",
                    "artifact_digest", ref.artifact_sha256)

        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if self.invalidation_history(claim_node):
                raise StoreError("cannot add provenance dependencies to an invalidated claim; issue a new claim ID")
            adjacency = self._dependency_adjacency()
            recorded: list[str] = []
            for edge in edges:
                if self.invalidation_history(edge.dependency_id):
                    raise StoreError(f"dependency {edge.dependency_id} is already invalidated")
                if self._reachable(adjacency, edge.dependency_id, edge.dependent_id):
                    raise StoreError(f"dependency edge {edge.edge_id} would introduce a cycle")
                self._append(
                    "dependency", edge.edge_id, 1, _canonical_payload(edge),
                    transaction_open=True,
                )
                adjacency.setdefault(edge.dependent_id, set()).add(edge.dependency_id)
                recorded.append(edge.edge_id)
            manifest = ProvenanceManifest(
                manifest_id=f"manifest:{claim_node}:v1",
                node_id=claim_node,
                edge_ids=tuple(recorded),
                manifest_version="m7.5.4/v1",
            )
            self.record_dependency_manifest(manifest, transaction_open=True)
        return tuple(recorded)

    def record_dependency_manifest(
        self, manifest: ProvenanceManifest, *, transaction_open: bool = False,
    ) -> bool:
        if not isinstance(manifest, ProvenanceManifest):
            raise TypeError("manifest must be a ProvenanceManifest")
        if not transaction_open:
            with self._connection:
                self._connection.execute("BEGIN IMMEDIATE")
                return self.record_dependency_manifest(manifest, transaction_open=True)
        rows = self._connection.execute(
            """SELECT record_id FROM epistemic_events
               WHERE record_type = 'dependency'
               AND json_extract(payload, '$.dependent_id') = ?""",
            (manifest.node_id,),
        ).fetchall()
        declared = {row["record_id"] for row in rows}
        if declared != set(manifest.edge_ids):
            raise StoreError("dependency manifest must exactly enumerate all recorded outgoing edges")
        return self._append(
            "dependency_manifest", manifest.manifest_id, 1,
            _canonical_payload(manifest), transaction_open=True,
        )

    def dependency_history(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """SELECT sequence, record_id, payload, event_hash FROM epistemic_events
               WHERE record_type = 'dependency' ORDER BY sequence"""
        ).fetchall()
        return [
            {"sequence": row["sequence"], "edge_id": row["record_id"],
             "payload": json.loads(row["payload"]), "event_hash": row["event_hash"]}
            for row in rows
        ]

    def _dependency_adjacency(self) -> dict[str, set[str]]:
        adjacency: dict[str, set[str]] = {}
        for item in self.dependency_history():
            payload = item["payload"]
            adjacency.setdefault(payload["dependent_id"], set()).add(payload["dependency_id"])
        return adjacency

    @staticmethod
    def _reachable(adjacency: dict[str, set[str]], start: str, target: str) -> bool:
        pending = [start]
        visited: set[str] = set()
        while pending:
            node = pending.pop()
            if node == target:
                return True
            if node in visited:
                continue
            visited.add(node)
            pending.extend(sorted(adjacency.get(node, ()), reverse=True))
        return False

    def record_dependency(self, dependency: ProvenanceDependency) -> bool:
        """Append an edge; reject any edge that would make the dependency graph cyclic."""
        if not isinstance(dependency, ProvenanceDependency):
            raise TypeError("dependency must be a ProvenanceDependency")
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if self.invalidation_history(dependency.dependency_id):
                raise StoreError("cannot attach a dependency to an invalidated node; use a new versioned node")
            if self.invalidation_history(dependency.dependent_id):
                raise StoreError("cannot extend an invalidated dependent node; use a new versioned node")
            adjacency = self._dependency_adjacency()
            if self._reachable(adjacency, dependency.dependency_id, dependency.dependent_id):
                raise StoreError(
                    f"dependency edge {dependency.edge_id} would introduce a cycle"
                )
            return self._append(
                "dependency", dependency.edge_id, 1, _canonical_payload(dependency),
                transaction_open=True,
            )

    def invalidate_dependency(
        self, changed_node_id: str, *, root_change_id: str,
        reason: str, observed_at: str,
    ) -> tuple[str, ...]:
        """Invalidate every transitive dependent of a changed provenance node.

        The root node is not itself marked stale; only records that depend on it
        are invalidated. Repeating the same root_change_id is idempotent.
        """
        for name, value in (("changed_node_id", changed_node_id),
                            ("root_change_id", root_change_id),
                            ("reason", reason), ("observed_at", observed_at)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        changed_node_id = changed_node_id.strip()
        root_change_id = root_change_id.strip()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            reverse: dict[str, set[str]] = {}
            for dependent, dependencies in self._dependency_adjacency().items():
                for dependency in dependencies:
                    reverse.setdefault(dependency, set()).add(dependent)

            ordered: list[tuple[str, str]] = []
            queue = [changed_node_id]
            visited = {changed_node_id}
            while queue:
                node = queue.pop(0)
                for dependent in sorted(reverse.get(node, ())):
                    if dependent in visited:
                        continue
                    visited.add(dependent)
                    ordered.append((dependent, changed_node_id))
                    queue.append(dependent)

            for node_id, root_id in ordered:
                invalidation = ProvenanceInvalidation(
                    invalidation_id=f"{root_change_id}:{node_id}",
                    node_id=node_id,
                    root_change_id=root_change_id,
                    changed_dependency_id=root_id,
                    reason=reason,
                    observed_at=observed_at,
                )
                self._append(
                    "invalidation", invalidation.invalidation_id, 1,
                    _canonical_payload(invalidation), transaction_open=True,
                )
        return tuple(node_id for node_id, _ in ordered)

    def invalidation_history(self, node_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """SELECT sequence, record_id, payload, event_hash FROM epistemic_events
               WHERE record_type = 'invalidation' AND json_extract(payload, '$.node_id') = ?
               ORDER BY sequence""", (node_id,)
        ).fetchall()
        return [
            {"sequence": row["sequence"], "invalidation_id": row["record_id"],
             "payload": json.loads(row["payload"]), "event_hash": row["event_hash"]}
            for row in rows
        ]

    def freshness_status(self, node_id: str) -> FreshnessResult:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        node_id = node_id.strip()
        # Read all three facts from one SQLite snapshot so a concurrent invalidation
        # cannot be missed between the invalidation and manifest checks.
        with self._connection:
            self._connection.execute("BEGIN")
            history = self.invalidation_history(node_id)
            if history:
                return FreshnessResult(
                    node_id=node_id, status=FreshnessStatus.INVALIDATED,
                    invalidation_ids=tuple(item["invalidation_id"] for item in history),
                    reason="one or more dependency changes invalidated this node",
                )
            manifest_row = self._connection.execute(
                """SELECT payload FROM epistemic_events
                   WHERE record_type = 'dependency_manifest'
                   AND json_extract(payload, '$.node_id') = ?
                   ORDER BY sequence DESC LIMIT 1""",
                (node_id,),
            ).fetchone()
            if manifest_row:
                manifest = json.loads(manifest_row["payload"])
                rows = self._connection.execute(
                    """SELECT record_id FROM epistemic_events
                       WHERE record_type = 'dependency'
                       AND json_extract(payload, '$.dependent_id') = ?""",
                    (node_id,),
                ).fetchall()
                actual = {row["record_id"] for row in rows}
                declared = set(manifest["edge_ids"])
                if actual == declared and declared:
                    return FreshnessResult(
                        node_id=node_id, status=FreshnessStatus.FRESH,
                        reason="a closed dependency manifest exactly matches the recorded dependency edges",
                    )
                return FreshnessResult(
                    node_id=node_id, status=FreshnessStatus.UNKNOWN,
                    reason="dependency manifest is missing edges or does not match the current dependency set",
                )
            return FreshnessResult(
                node_id=node_id, status=FreshnessStatus.UNKNOWN,
                reason="no dependency declaration establishes freshness",
            )

    def transition_gap(self, gap: KnowledgeGap, *, expected_revision: int) -> int:
        """Append a new gap revision; the prior revision remains immutable."""
        if not isinstance(gap, KnowledgeGap):
            raise TypeError("gap must be a KnowledgeGap")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self.latest_gap(gap.gap_id)
            if current is None:
                raise RevisionConflictError(f"gap {gap.gap_id} has no initial record")
            if current["revision"] != expected_revision:
                raise RevisionConflictError(
                    f"expected revision {expected_revision}, current revision is {current['revision']}"
                )
            prior = current["payload"]
            stable_fields = ("subject_id", "kind", "scope_id", "discovery_method")
            for field in stable_fields:
                prior_value = prior[field]
                next_value = gap.kind.value if field == "kind" else getattr(gap, field)
                if prior_value != next_value:
                    raise StoreError(f"gap identity field {field} cannot change across revisions")
            old_state = GapState(prior["state"])
            if gap.state not in _ALLOWED_GAP_TRANSITIONS[old_state]:
                raise InvalidTransitionError(f"transition {old_state.value} -> {gap.state.value} is not permitted")
            self._append(
                "gap", gap.gap_id, expected_revision + 1, _canonical_payload(gap),
                transaction_open=True,
            )
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

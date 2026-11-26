"""M7.5.4 provenance dependency, freshness and invalidation tests."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    CompletenessClaim, CompletenessStatus, DuplicateRecordError, EpistemicStore, EvidenceRef,
    FreshnessStatus, NegativeClaimRequest, ProvenanceDependency,
    ProvenanceManifest, StorageLimitError, StoreError, evaluate_negative_claim_with_freshness,
)


def evidence():
    return EvidenceRef(
        evidence_id="evidence-1", source_snapshot_id="snapshot-1",
        producer_id="enumerator", method_id="tree-walk",
        observed_at="2026-11-27T00:00:00Z",
    )


def claim():
    return CompletenessClaim(
        claim_id="claim-1", subject_id="repository:source",
        scope_id="scope:src", source_snapshot_id="snapshot-1",
        enumeration_method="git-tree-walk", method_version="v2",
        covered_units=1, expected_units=1,
        status=CompletenessStatus.SUPPORTED_WITHIN_SCOPE,
        evidence_refs=(evidence(),), verification_method_id="manifest-check",
        predicate_id="contains:source-unit",
        covered_unit_ids=("src/a.py",), expected_unit_ids=("src/a.py",),
    )


def request():
    return NegativeClaimRequest(
        subject_id="repository:source", predicate_id="contains:source-unit",
        scope_id="scope:src", source_snapshot_id="snapshot-1",
        closed_world_rule_id="rule:closed-world:v1", rule_allows_closed_world=True,
    )


class ProvenanceGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = EpistemicStore(Path(self.temp.name) / "epistemic.sqlite")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def edge(self, edge_id, dependent, dependency):
        return ProvenanceDependency(
            edge_id=edge_id, dependent_id=dependent, dependency_id=dependency,
            dependency_kind="test", expected_revision="v1",
        )

    def test_cycles_are_rejected_before_append(self):
        self.store.record_dependency(self.edge("ab", "A", "B"))
        self.store.record_dependency(self.edge("bc", "B", "C"))
        before = self.store.event_count()
        with self.assertRaises(StoreError):
            self.store.record_dependency(self.edge("ca", "C", "A"))
        self.assertEqual(self.store.event_count(), before)
        self.assertTrue(self.store.verify_integrity())

    def test_dependency_edge_is_idempotent_but_conflicting_reuse_rejected(self):
        item = self.edge("edge-1", "claim:X", "snapshot:X")
        self.assertTrue(self.store.record_dependency(item))
        self.assertFalse(self.store.record_dependency(item))
        with self.assertRaises(DuplicateRecordError):
            self.store.record_dependency(self.edge("edge-1", "claim:X", "snapshot:Y"))
        self.assertEqual(len(self.store.dependency_history()), 1)

    def test_completeness_claim_gets_closed_dependency_manifest(self):
        item = claim()
        edges = self.store.record_completeness_dependencies(item)
        self.assertGreaterEqual(len(edges), 7)
        status = self.store.freshness_status("claim:claim-1")
        self.assertEqual(status.status, FreshnessStatus.FRESH)
        self.assertEqual(self.store.freshness_status("evidence:evidence-1").status, FreshnessStatus.FRESH)
        self.assertEqual(self.store.record_completeness_dependencies(item), edges)
        self.assertTrue(self.store.verify_integrity())

    def test_missing_or_incomplete_manifest_never_reports_fresh(self):
        self.store.record_dependency(self.edge("edge-1", "claim:X", "snapshot:X"))
        self.assertEqual(self.store.freshness_status("claim:X").status, FreshnessStatus.UNKNOWN)
        incomplete = ProvenanceManifest(
            manifest_id="manifest-X", node_id="claim:X",
            edge_ids=("edge-missing",), manifest_version="v1",
        )
        with self.assertRaises(StoreError):
            self.store.record_dependency_manifest(incomplete)
        self.assertEqual(self.store.freshness_status("claim:X").status, FreshnessStatus.UNKNOWN)

    def test_new_edge_after_manifest_invalidates_manifest_completeness(self):
        self.store.record_dependency(self.edge("edge-1", "claim:X", "snapshot:X"))
        self.store.record_dependency_manifest(ProvenanceManifest(
            manifest_id="manifest-X", node_id="claim:X",
            edge_ids=("edge-1",), manifest_version="v1",
        ))
        self.assertEqual(self.store.freshness_status("claim:X").status, FreshnessStatus.FRESH)
        self.store.record_dependency(self.edge("edge-2", "claim:X", "method:X"))
        self.assertEqual(self.store.freshness_status("claim:X").status, FreshnessStatus.UNKNOWN)

    def test_transitive_invalidation_is_deterministic_and_preserves_history(self):
        self.store.record_dependency(self.edge("claim-snapshot", "claim:A", "snapshot:A"))
        self.store.record_dependency(self.edge("report-claim", "report:A", "claim:A"))
        self.store.record_dependency(self.edge("dashboard-report", "dashboard:A", "report:A"))
        self.store.record_dependency(self.edge("sibling-snapshot", "claim:B", "snapshot:B"))
        self.store.record_dependency_manifest(ProvenanceManifest(
            manifest_id="manifest-claim-A", node_id="claim:A",
            edge_ids=("claim-snapshot",), manifest_version="v1",
        ))
        self.store.record_dependency_manifest(ProvenanceManifest(
            manifest_id="manifest-report-A", node_id="report:A",
            edge_ids=("report-claim",), manifest_version="v1",
        ))
        self.store.record_dependency_manifest(ProvenanceManifest(
            manifest_id="manifest-dashboard-A", node_id="dashboard:A",
            edge_ids=("dashboard-report",), manifest_version="v1",
        ))
        self.store.record_dependency_manifest(ProvenanceManifest(
            manifest_id="manifest-claim-B", node_id="claim:B",
            edge_ids=("sibling-snapshot",), manifest_version="v1",
        ))
        affected = self.store.invalidate_dependency(
            "snapshot:A", root_change_id="change-17",
            reason="source snapshot replaced", observed_at="2026-11-27T12:00:00Z",
        )
        self.assertEqual(affected, ("claim:A", "report:A", "dashboard:A"))
        self.assertEqual(self.store.freshness_status("claim:A").status, FreshnessStatus.INVALIDATED)
        self.assertEqual(self.store.freshness_status("report:A").status, FreshnessStatus.INVALIDATED)
        self.assertEqual(self.store.freshness_status("dashboard:A").status, FreshnessStatus.INVALIDATED)
        self.assertEqual(self.store.freshness_status("claim:B").status, FreshnessStatus.FRESH)
        count = self.store.event_count()
        repeated = self.store.invalidate_dependency(
            "snapshot:A", root_change_id="change-17",
            reason="source snapshot replaced", observed_at="2026-11-27T12:00:00Z",
        )
        self.assertEqual(repeated, affected)
        self.assertEqual(self.store.event_count(), count)
        self.assertEqual(len(self.store.invalidation_history("claim:A")), 1)
        self.assertTrue(self.store.verify_integrity())

    def test_stale_nodes_cannot_be_reintroduced_as_fresh_dependencies(self):
        self.store.record_dependency(self.edge("claim-snapshot", "claim:A", "snapshot:A"))
        self.store.record_dependency_manifest(ProvenanceManifest(
            manifest_id="manifest-A", node_id="claim:A",
            edge_ids=("claim-snapshot",), manifest_version="v1",
        ))
        self.store.invalidate_dependency(
            "snapshot:A", root_change_id="change-A",
            reason="snapshot changed", observed_at="now",
        )
        with self.assertRaises(StoreError):
            self.store.record_dependency(self.edge("report-claim", "report:A", "claim:A"))

    def test_freshness_is_mandatory_for_negative_claim_reuse(self):
        item = claim()
        unknown = self.store.freshness_status("claim:claim-1")
        result = evaluate_negative_claim_with_freshness(item, request(), unknown)
        self.assertFalse(result.admissible)
        self.assertIn("completeness claim freshness is unknown because dependencies are not declared", result.reasons)

        self.store.record_completeness_dependencies(item)
        fresh = self.store.freshness_status("claim:claim-1")
        self.assertTrue(evaluate_negative_claim_with_freshness(item, request(), fresh).admissible)

        self.store.invalidate_dependency(
            "snapshot:snapshot-1", root_change_id="snapshot-change-1",
            reason="source changed", observed_at="now",
        )
        stale = self.store.freshness_status("claim:claim-1")
        result = evaluate_negative_claim_with_freshness(item, request(), stale)
        self.assertFalse(result.admissible)
        self.assertIn("completeness claim has been invalidated by a dependency change", result.reasons)

    def test_claim_dependency_registration_rolls_back_all_edges_on_storage_limit(self):
        self.store.max_events = 2
        with self.assertRaises(StorageLimitError):
            self.store.record_completeness_dependencies(claim())
        self.assertEqual(self.store.event_count(), 0)
        self.assertTrue(self.store.verify_integrity())
        self.assertEqual(self.store.freshness_status("claim:claim-1").status, FreshnessStatus.UNKNOWN)

    def test_transitive_invalidation_rolls_back_all_nodes_on_storage_limit(self):
        self.store.record_dependency(self.edge("claim-snapshot", "claim:A", "snapshot:A"))
        self.store.record_dependency(self.edge("report-claim", "report:A", "claim:A"))
        self.store.record_dependency_manifest(ProvenanceManifest(
            manifest_id="manifest-claim-A", node_id="claim:A",
            edge_ids=("claim-snapshot",), manifest_version="v1",
        ))
        self.store.record_dependency_manifest(ProvenanceManifest(
            manifest_id="manifest-report-A", node_id="report:A",
            edge_ids=("report-claim",), manifest_version="v1",
        ))
        before = self.store.event_count()
        self.store.max_events = before + 1
        with self.assertRaises(StorageLimitError):
            self.store.invalidate_dependency(
                "snapshot:A", root_change_id="limited-change",
                reason="source changed", observed_at="now",
            )
        self.assertEqual(self.store.event_count(), before)
        self.assertEqual(self.store.freshness_status("claim:A").status, FreshnessStatus.FRESH)
        self.assertEqual(self.store.freshness_status("report:A").status, FreshnessStatus.FRESH)
        self.assertTrue(self.store.verify_integrity())

    def test_m753_database_migrates_to_provenance_schema_without_rehashing_history(self):
        database = Path(self.temp.name) / "m753.sqlite"
        payload = json.dumps({"legacy": "m753"}, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()
        event_id = "completeness:legacy-claim:1"
        previous_hash = "0" * 64
        event_hash = hashlib.sha256(
            f"1\n{event_id}\n{payload_hash}\n{previous_hash}".encode()
        ).hexdigest()
        raw = sqlite3.connect(database)
        raw.execute("""
            CREATE TABLE epistemic_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                record_type TEXT NOT NULL CHECK(record_type IN ('assertion', 'gap', 'completeness')),
                record_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 1),
                payload TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE,
                UNIQUE(record_type, record_id, revision)
            )
        """)
        raw.execute("""
            INSERT INTO epistemic_events VALUES
            (1, ?, 'completeness', 'legacy-claim', 1, ?, ?, ?, ?)
        """, (event_id, payload, payload_hash, previous_hash, event_hash))
        raw.commit()
        raw.close()
        with EpistemicStore(database) as migrated:
            self.assertEqual(migrated.event_count(), 1)
            self.assertTrue(migrated.verify_integrity())
            self.assertTrue(migrated.record_dependency(self.edge("new-edge", "claim:new", "snapshot:new")))
            self.assertEqual(migrated.event_count(), 2)
            self.assertTrue(migrated.verify_integrity())


if __name__ == "__main__":
    unittest.main()

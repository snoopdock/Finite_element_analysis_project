import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic.contracts import (
    FreshnessStatus,
    ProvenanceDependency,
    ProvenanceManifest,
)
from audit_engine.semantic_audit.epistemic.store import EpistemicStore, StoreError


class FreshnessClosureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = EpistemicStore(Path(self.temp.name) / "epistemic.sqlite")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def declare_node(self, node_id, dependencies=()):
        edge_ids = []
        for index, dependency_id in enumerate(dependencies):
            edge_id = f"edge:{node_id}:{index}:{dependency_id}"
            edge = ProvenanceDependency(
                edge_id=edge_id,
                dependent_id=node_id,
                dependency_id=dependency_id,
                dependency_kind="test_dependency",
                expected_revision="rev-1",
            )
            self.store.record_dependency(edge)
            edge_ids.append(edge_id)
        manifest = ProvenanceManifest(
            manifest_id=f"manifest:{node_id}:v1",
            node_id=node_id,
            edge_ids=tuple(edge_ids),
            manifest_version="m7.5.6/v1",
        )
        self.store.record_dependency_manifest(manifest)

    def test_missing_terminal_manifest_is_unknown(self):
        result = self.store.freshness_closure("source:unregistered")
        self.assertIs(result.status, FreshnessStatus.UNKNOWN)
        self.assertIn("no manifest", result.reason)

    def test_explicit_empty_manifest_declares_fresh_terminal(self):
        self.declare_node("source:terminal")
        local = self.store.freshness_status("source:terminal")
        closure = self.store.freshness_closure("source:terminal")
        self.assertIs(local.status, FreshnessStatus.FRESH)
        self.assertIs(closure.status, FreshnessStatus.FRESH)
        self.assertEqual(closure.reason, "explicit terminal manifest is exact")

    def test_composite_closure_is_fresh_when_all_dependencies_are_terminal(self):
        self.declare_node("source:a")
        self.declare_node("source:b")
        self.declare_node("claim:root", ("source:a", "source:b"))
        result = self.store.freshness_closure("claim:root")
        self.assertIs(result.status, FreshnessStatus.FRESH)
        self.assertIn("all nodes", result.reason)

    def test_local_fresh_does_not_hide_unknown_transitive_dependency(self):
        self.declare_node("claim:root", ("source:missing-manifest",))
        local = self.store.freshness_status("claim:root")
        closure = self.store.freshness_closure("claim:root")
        self.assertIs(local.status, FreshnessStatus.FRESH)
        self.assertIs(closure.status, FreshnessStatus.UNKNOWN)
        self.assertIn("transitive dependencies", closure.reason)

    def test_transitive_invalidation_invalidates_root_closure(self):
        self.declare_node("source:leaf")
        self.declare_node("claim:middle", ("source:leaf",))
        self.declare_node("claim:root", ("claim:middle",))
        affected = self.store.invalidate_dependency(
            "source:leaf",
            root_change_id="source-change-1",
            reason="source revision changed",
            observed_at="2026-11-27T10:00:00Z",
        )
        self.assertEqual(set(affected), {"claim:middle", "claim:root"})
        result = self.store.freshness_closure("claim:root")
        self.assertIs(result.status, FreshnessStatus.INVALIDATED)
        self.assertEqual(
            set(result.invalidation_ids),
            {"source-change-1:claim:middle", "source-change-1:claim:root"},
        )

    def test_new_edge_after_manifest_makes_closure_unknown(self):
        self.declare_node("source:a")
        self.declare_node("claim:root", ("source:a",))
        self.store.record_dependency(ProvenanceDependency(
            edge_id="edge:late",
            dependent_id="claim:root",
            dependency_id="source:b",
            dependency_kind="late_dependency",
            expected_revision="rev-1",
        ))
        result = self.store.freshness_closure("claim:root")
        self.assertIs(result.status, FreshnessStatus.UNKNOWN)
        self.assertIn("manifest", result.reason)

    def test_cycle_forming_edge_is_rejected(self):
        self.declare_node("node:a", ("node:b",))
        with self.assertRaises(StoreError):
            self.store.record_dependency(ProvenanceDependency(
                edge_id="edge:b-to-a",
                dependent_id="node:b",
                dependency_id="node:a",
                dependency_kind="cycle_test",
                expected_revision="rev-1",
            ))
        self.assertTrue(self.store.verify_integrity())

    def test_multiple_branches_have_deterministic_closure(self):
        self.declare_node("source:z")
        self.declare_node("source:a")
        self.declare_node("branch:z", ("source:z",))
        self.declare_node("branch:a", ("source:a",))
        self.declare_node("claim:root", ("branch:z", "branch:a"))
        first = self.store.freshness_closure("claim:root")
        second = self.store.freshness_closure("claim:root")
        self.assertEqual(first, second)
        self.assertIs(first.status, FreshnessStatus.FRESH)

    def test_unknown_dependency_takes_precedence_over_local_fresh(self):
        self.declare_node("source:known")
        self.declare_node("claim:root", ("source:known", "source:unknown"))
        self.assertIs(self.store.freshness_status("claim:root").status, FreshnessStatus.FRESH)
        self.assertIs(self.store.freshness_closure("claim:root").status, FreshnessStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from tools.ae32c_graph_snapshot import (
    GraphSnapshotError,
    build_graph_snapshot,
    canonical_bytes,
    digest,
    verify_graph_manifest,
)


def source_manifest():
    payload = {
        "manifest_schema": "ae32c/source-snapshot-manifest/v1",
        "status": "VERIFIED",
        "source_snapshot_id": "a" * 64,
        "source": {
            "repository": "example/repo",
            "commit_oid": "1" * 40,
            "root_tree_oid": "2" * 40,
        },
        "source_inventory": {"entries": [
            {"path": "src/a.py", "mode": "100644", "git_object_oid": "3" * 40,
             "content_sha256": "4" * 64},
            {"path": "README.md", "mode": "100644", "git_object_oid": "5" * 40,
             "content_sha256": "6" * 64},
        ]},
        "verification": {"status": "VERIFIED"},
    }
    payload["manifest_sha256"] = digest(payload)
    return payload


def report():
    return {
        "audit": {"status": "complete", "scope_policy": {"extensions": [".py"]}},
        "source_manifest": [{"path": "src/a.py", "status": "included",
                             "sha256": "4" * 64, "size": 10}],
        "python_parse_issues": [],
        "scope_issues": [],
        "python_source_root_issues": [],
        "workflow_issues": [],
    }


class GraphSnapshotTests(unittest.TestCase):
    def _build(self, graph=None, evidence=None, represented=None, hashes=None):
        return build_graph_snapshot(
            source_manifest=source_manifest(),
            graph=graph or {"nodes": [{"id": "file:src/a.py", "type": "PythonSourceFile",
                                       "attributes": {"sha256": "4" * 64}, "metadata": {}}],
                            "edges": []},
            evidence_report=evidence or report(),
            represented_paths=represented if represented is not None else {"src/a.py"},
            file_hashes=hashes if hashes is not None else {"src/a.py": "4" * 64},
            python_runtime="3.test",
        )

    def test_identity_is_deterministic_and_order_independent(self):
        first = self._build()
        second = self._build(graph={"edges": [], "nodes": list(reversed([
            {"id": "file:src/a.py", "type": "PythonSourceFile",
             "attributes": {"sha256": "4" * 64}, "metadata": {}},
        ]))})
        self.assertEqual(first["graph_snapshot_id"], second["graph_snapshot_id"])
        self.assertEqual(first["graph"]["content_sha256"], second["graph"]["content_sha256"])

    def test_source_snapshot_identity_is_bound_into_graph_identity(self):
        first = self._build()
        changed = source_manifest()
        changed["source_snapshot_id"] = "b" * 64
        changed["manifest_sha256"] = digest({k: v for k, v in changed.items() if k != "manifest_sha256"})
        second = build_graph_snapshot(
            source_manifest=changed,
            graph={"nodes": [{"id": "file:src/a.py", "type": "PythonSourceFile",
                              "attributes": {"sha256": "4" * 64}, "metadata": {}}], "edges": []},
            evidence_report=report(), represented_paths={"src/a.py"},
            file_hashes={"src/a.py": "4" * 64}, python_runtime="3.test",
        )
        self.assertNotEqual(first["graph_snapshot_id"], second["graph_snapshot_id"])

    def test_unaccounted_source_unit_makes_coverage_incomplete(self):
        result = self._build(represented=set(), hashes={})
        self.assertEqual(result["coverage"]["status"], "INCOMPLETE")
        self.assertEqual(result["coverage"]["unaccounted_count"], 1)
        self.assertFalse(result["authority"]["graph_completeness_established"])

    def test_negative_findings_are_denied_even_when_coverage_is_complete(self):
        result = self._build()
        self.assertEqual(result["coverage"]["status"], "COMPLETE_WITH_DECLARED_EXCLUSIONS")
        self.assertFalse(result["coverage"]["limitations"]["negative_findings_permitted_by_default"])
        self.assertFalse(result["authority"]["negative_findings_permitted_by_default"])

    def test_extra_uncommitted_graph_path_is_rejected(self):
        with self.assertRaisesRegex(GraphSnapshotError, "graph_contains_uncommitted_source_path"):
            self._build(represented={"src/a.py", "scratch.py"},
                        hashes={"src/a.py": "4" * 64, "scratch.py": "5" * 64})

    def test_source_to_graph_digest_mismatch_fails_closed(self):
        with self.assertRaisesRegex(GraphSnapshotError, "source_to_graph_digest_mismatch"):
            self._build(hashes={"src/a.py": "f" * 64})

    def test_dangling_graph_edge_fails_closed(self):
        with self.assertRaisesRegex(GraphSnapshotError, "graph_dangling_edge"):
            self._build(graph={"nodes": [], "edges": [
                {"source": "missing", "target": "also-missing", "relation": "CALLS"}
            ]})

    def test_tampered_source_manifest_is_rejected(self):
        manifest = source_manifest()
        manifest["source"]["commit_oid"] = "f" * 40
        with self.assertRaisesRegex(GraphSnapshotError, "source_manifest_digest_mismatch"):
            build_graph_snapshot(
                source_manifest=manifest,
                graph={"nodes": [], "edges": []}, evidence_report=report(),
                represented_paths=set(), file_hashes={},
            )

    def test_graph_manifest_tampering_is_rejected(self):
        result = self._build()
        result["coverage"]["represented_count"] = 999
        with self.assertRaisesRegex(GraphSnapshotError, "graph_manifest_digest_mismatch"):
            verify_graph_manifest(result)

    def test_graph_manifest_internal_identity_is_verified(self):
        result = self._build()
        verify_graph_manifest(result)
        self.assertEqual(result["manifest_sha256"], digest({
            key: value for key, value in result.items() if key != "manifest_sha256"
        }))

    def test_extractor_issue_makes_coverage_incomplete(self):
        evidence = report()
        evidence["python_parse_issues"] = [{"path": "src/a.py", "kind": "python_syntax_error"}]
        result = self._build(evidence=evidence)
        self.assertEqual(result["coverage"]["status"], "INCOMPLETE")
        self.assertEqual(result["coverage"]["extractor_coverage"]["python_ast"]["failed_count"], 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from audit_engine.semantic_audit.ae32c.trusted_artifact import (
    TrustedArtifactError, _verify_coverage_cross_binding, digest, parse_manifest, validate_publication_artifact,
)
from tools.ae32c_graph_snapshot import build_graph_snapshot


REPOSITORY = "snoopdock/Finite_element_analysis_project"
COMMIT = "1" * 40
TREE = "2" * 40


def fixtures(*, represented=True):
    entries = [
        {"path": "README.md", "mode": "100644", "object_type": "blob",
         "git_object_oid": "3" * 40, "content_sha256": "4" * 64,
         "materialization_kind": "regular_file"},
        {"path": "src/a.py", "mode": "100644", "object_type": "blob",
         "git_object_oid": "5" * 40, "content_sha256": "6" * 64,
         "materialization_kind": "regular_file"},
    ]
    inventory_sha = digest(entries)
    source = {
        "repository": REPOSITORY, "source_mode": "push", "commit_oid": COMMIT,
        "commit_oid_algorithm": "sha1", "root_tree_oid": TREE,
        "base_commit_oid": None, "head_commit_oid": None,
        "source_inventory_sha256": inventory_sha,
    }
    source_id = digest(source)
    event = {
        "event_name": "push", "repository": REPOSITORY, "ref": "refs/heads/main",
        "source_mode": "push", "base_commit_oid": None, "head_commit_oid": None,
        "event_merge_commit_oid": None,
    }
    source_manifest = {
        "manifest_schema": "ae32c/source-snapshot-manifest/v1",
        "status": "VERIFIED", "source_snapshot_id": source_id,
        "source": source, "event": event,
        "source_inventory": {"schema": "ae32c/source-inventory/v1",
                             "entry_count": len(entries), "entries": entries,
                             "sha256": inventory_sha},
        "materialization": {"status": "CLEAN"},
        "verification": {
            "status": "VERIFIED", "source_snapshot_id_at_verification": source_id,
            "source_inventory_sha256_at_verification": inventory_sha,
            "worktree_clean_at_verification": True,
        },
        "run": {"run_id": "100", "run_attempt": "1", "workflow": "AE-32C"},
        "authority": {"production_approval": False},
    }
    source_manifest["manifest_sha256"] = digest(source_manifest)
    report = {
        "audit": {"status": "complete", "scope_policy": {"extensions": [".py"]}},
        "source_manifest": [{"path": "src/a.py", "status": "included",
                             "sha256": "6" * 64, "size": 10}],
        "python_parse_issues": [], "scope_issues": [],
        "python_source_root_issues": [], "workflow_issues": [],
    }
    graph_manifest = build_graph_snapshot(
        source_manifest=source_manifest,
        graph={"nodes": [{"id": "file:src/a.py", "type": "PythonSourceFile",
                          "attributes": {"sha256": "6" * 64}, "metadata": {}}],
               "edges": []},
        evidence_report=report,
        represented_paths={"src/a.py"} if represented else set(),
        file_hashes={"src/a.py": "6" * 64} if represented else {},
        python_runtime="3.test",
    )
    expected = {
        "repository": REPOSITORY, "default_branch": "main", "head_branch": "main",
        "head_repository": REPOSITORY, "ref": "refs/heads/main", "event": "push",
        "head_sha": COMMIT, "run_id": 100, "run_attempt": 1, "run_number": 51,
        "workflow_id": 430355742,
        "workflow_path": ".github/workflows/ae32c_source_snapshot_manifest.yml",
        "conclusion": "success",
    }
    return source_manifest, graph_manifest, expected


class TrustedArtifactTests(unittest.TestCase):
    def test_complete_artifact_produces_current_eligible_record(self):
        source, graph, expected = fixtures()
        result = validate_publication_artifact(source, graph, expected=expected)
        self.assertTrue(result["current_eligible"])
        self.assertEqual(result["record"]["outcome"], "SUCCEEDED")
        self.assertEqual(result["record"]["source_revision"], COMMIT)

    def test_incomplete_graph_is_history_only(self):
        source, graph, expected = fixtures(represented=False)
        result = validate_publication_artifact(source, graph, expected=expected)
        self.assertFalse(result["current_eligible"])
        self.assertEqual(result["record"]["outcome"], "INCOMPLETE")

    def test_wrong_upstream_run_is_rejected(self):
        source, graph, expected = fixtures()
        expected["run_id"] = 101
        with self.assertRaisesRegex(TrustedArtifactError, "workflow_run_id_mismatch"):
            validate_publication_artifact(source, graph, expected=expected)

    def test_wrong_event_is_rejected(self):
        source, graph, expected = fixtures()
        source["event"]["event_name"] = "pull_request"
        source["manifest_sha256"] = digest({
            key: value for key, value in source.items() if key != "manifest_sha256"
        })
        with self.assertRaisesRegex(TrustedArtifactError, "event_not_authorized"):
            validate_publication_artifact(source, graph, expected=expected)

    def test_graph_source_commit_mismatch_is_rejected(self):
        source, graph, expected = fixtures()
        graph["source"]["commit_oid"] = "f" * 40
        graph["manifest_sha256"] = digest({
            key: value for key, value in graph.items() if key != "manifest_sha256"
        })
        with self.assertRaisesRegex(TrustedArtifactError, "graph_source_identity_mismatch"):
            validate_publication_artifact(source, graph, expected=expected)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(TrustedArtifactError, "duplicate_json_key"):
            parse_manifest(b'{"a":1,"a":2}', label="source")

    def test_non_finite_json_numbers_are_rejected(self):
        with self.assertRaisesRegex(TrustedArtifactError, "non_finite_json_number"):
            parse_manifest(b'{"a":NaN}', label="source")

    def test_source_manifest_tampering_is_rejected(self):
        source, graph, expected = fixtures()
        source["source"]["commit_oid"] = "f" * 40
        with self.assertRaisesRegex(TrustedArtifactError, "source_manifest_digest_invalid"):
            validate_publication_artifact(source, graph, expected=expected)

    def test_coverage_unit_must_bind_exact_source_inventory_entry(self):
        source, graph, expected = fixtures()
        graph["coverage"]["source_units"][0]["git_object_oid"] = "f" * 40
        with self.assertRaisesRegex(TrustedArtifactError, "graph_coverage_source_entry_mismatch"):
            _verify_coverage_cross_binding(
                graph["coverage"], source["source_inventory"]["entries"]
            )

    def test_coverage_aggregate_counts_must_match_status_rows(self):
        source, graph, expected = fixtures()
        graph["coverage"]["represented_count"] += 1
        with self.assertRaisesRegex(TrustedArtifactError, "graph_coverage_aggregate_counts_mismatch"):
            _verify_coverage_cross_binding(
                graph["coverage"], source["source_inventory"]["entries"]
            )

    def test_non_default_branch_is_rejected(self):
        source, graph, expected = fixtures()
        expected["head_branch"] = "feature/test"
        expected["ref"] = "refs/heads/feature/test"
        source["event"]["ref"] = expected["ref"]
        source["manifest_sha256"] = digest({
            key: value for key, value in source.items() if key != "manifest_sha256"
        })
        with self.assertRaisesRegex(TrustedArtifactError, "event_ref_not_default_branch"):
            validate_publication_artifact(source, graph, expected=expected)


if __name__ == "__main__":
    unittest.main()

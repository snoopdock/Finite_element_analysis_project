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
            {"path": "README.md", "mode": "100644", "object_type": "blob",
             "git_object_oid": "5" * 40, "content_sha256": "6" * 64},
            {"path": "src/a.py", "mode": "100644", "object_type": "blob",
             "git_object_oid": "3" * 40, "content_sha256": "4" * 64},
        ]},
        "verification": {"status": "VERIFIED"},
    }
    payload["source_inventory"]["entry_count"] = len(payload["source_inventory"]["entries"])
    payload["source_inventory"]["sha256"] = digest(payload["source_inventory"]["entries"])
    payload["manifest_sha256"] = digest(payload)
    return payload


def lfs_attestation(manifest=None, pointer_paths=()):
    manifest = manifest or source_manifest()
    entries = [
        {"path": item["path"], "git_object_oid": item["git_object_oid"],
         "content_sha256": item["content_sha256"], "is_lfs_pointer": item["path"] in pointer_paths}
        for item in manifest["source_inventory"]["entries"]
        if item["object_type"] == "blob" and item["mode"] in {"100644", "100755"}
    ]
    pointers = []
    for item in entries:
        if item["is_lfs_pointer"]:
            pointers.append({
                "path": item["path"], "git_object_oid": item["git_object_oid"],
                "pointer_sha256": item["content_sha256"], "status": "UNVERIFIED",
                "reason": "lfs_object_store_not_supplied",
            })
    result = {
        "schema": "ae32c/lfs-payload-verification/v2",
        "source_snapshot_id": manifest["source_snapshot_id"],
        "commit_oid": manifest["source"]["commit_oid"],
        "source_inventory_sha256": manifest["source_inventory"]["sha256"],
        "object_store_mode": "NOT_SUPPLIED_NO_NETWORK",
        "status": "NOT_SUPPLIED", "scan_complete": True,
        "scanned_regular_blob_count": len(entries), "regular_blob_inventory": entries,
        "pointer_count": len(pointers), "verified_payload_count": 0,
        "unverified_payload_count": len(pointers), "lfs_payload_verified": False,
        "records": pointers, "remote_payload_provenance_verified": False,
        "atomic_snapshot_established": False, "production_approval": False,
    }
    result["attestation_sha256"] = digest(result)
    return result


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
    def _build(self, graph=None, evidence=None, represented=None, hashes=None, lfs=None):
        return build_graph_snapshot(
            source_manifest=source_manifest(),
            graph=graph or {"nodes": [{"id": "file:src/a.py", "type": "PythonSourceFile",
                                       "attributes": {"sha256": "4" * 64}, "metadata": {}}],
                            "edges": []},
            evidence_report=evidence or report(),
            represented_paths=represented if represented is not None else {"src/a.py"},
            file_hashes=hashes if hashes is not None else {"src/a.py": "4" * 64},
            python_runtime="3.test",
            lfs_attestation=lfs if lfs is not None else lfs_attestation(),
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
            lfs_attestation=lfs_attestation(changed),
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


    def test_lfs_attestation_is_bound_to_source_and_inventory(self):
        attestation = lfs_attestation()
        attestation["source_inventory_sha256"] = "f" * 64
        attestation["attestation_sha256"] = digest({
            key: value for key, value in attestation.items() if key != "attestation_sha256"
        })
        with self.assertRaisesRegex(GraphSnapshotError, "lfs_attestation_source_binding_mismatch"):
            self._build(lfs=attestation)

    def test_lfs_attestation_commit_mismatch_is_rejected(self):
        attestation = lfs_attestation()
        attestation["commit_oid"] = "f" * 40
        attestation["attestation_sha256"] = digest({
            key: value for key, value in attestation.items() if key != "attestation_sha256"
        })
        with self.assertRaisesRegex(GraphSnapshotError, "lfs_attestation_source_binding_mismatch"):
            self._build(lfs=attestation)

    def test_lfs_attestation_rejects_duplicate_regular_blob_inventory(self):
        attestation = lfs_attestation()
        attestation["regular_blob_inventory"].append(dict(attestation["regular_blob_inventory"][0]))
        attestation["scanned_regular_blob_count"] += 1
        attestation["attestation_sha256"] = digest({
            key: value for key, value in attestation.items() if key != "attestation_sha256"
        })
        with self.assertRaisesRegex(GraphSnapshotError, "lfs_regular_blob_inventory_count_mismatch|lfs_regular_blob_inventory_duplicate"):
            self._build(lfs=attestation)

    def test_lfs_pointer_record_omission_is_rejected(self):
        attestation = lfs_attestation(pointer_paths={"README.md"})
        attestation["records"] = []
        attestation["pointer_count"] = 0
        attestation["unverified_payload_count"] = 0
        attestation["attestation_sha256"] = digest({
            key: value for key, value in attestation.items() if key != "attestation_sha256"
        })
        with self.assertRaisesRegex(GraphSnapshotError, "lfs_pointer_records_incomplete_or_extra"):
            self._build(lfs=attestation)

    def test_graph_manifest_rejects_lfs_attestation_tampering_and_omission(self):
        result = self._build()
        changed = dict(result)
        changed["lfs_attestation"] = dict(result["lfs_attestation"])
        changed["lfs_attestation"]["status"] = "VERIFIED_LOCAL_PAYLOADS"
        changed["manifest_sha256"] = digest({
            key: value for key, value in changed.items() if key != "manifest_sha256"
        })
        with self.assertRaisesRegex(GraphSnapshotError, "lfs_attestation_digest_mismatch"):
            verify_graph_manifest(changed)
        missing = dict(result)
        missing.pop("lfs_attestation")
        missing["manifest_sha256"] = digest({
            key: value for key, value in missing.items() if key != "manifest_sha256"
        })
        with self.assertRaisesRegex(GraphSnapshotError, "graph_lfs_attestation_reference_mismatch"):
            verify_graph_manifest(missing)

    def test_lfs_attestation_is_in_graph_identity_and_coverage(self):
        result = self._build()
        self.assertEqual(result["identity"]["lfs_attestation_sha256"],
                         result["lfs_attestation"]["attestation_sha256"])
        self.assertEqual(result["coverage"]["lfs_payloads"]["status"], "NOT_SUPPLIED")
        self.assertEqual(result["coverage"]["lfs_payloads"]["scanned_regular_blob_count"], 2)
        self.assertFalse(result["lfs_attestation"]["production_approval"])

    def test_extractor_issue_makes_coverage_incomplete(self):
        evidence = report()
        evidence["python_parse_issues"] = [{"path": "src/a.py", "kind": "python_syntax_error"}]
        result = self._build(evidence=evidence)
        self.assertEqual(result["coverage"]["status"], "INCOMPLETE")
        self.assertEqual(result["coverage"]["extractor_coverage"]["python_ast"]["failed_count"], 1)


if __name__ == "__main__":
    unittest.main()

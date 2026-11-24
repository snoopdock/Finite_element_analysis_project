"""Focused detached evidence verifier tests; standard-library only."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools import gb08_m74_native_conformance_dossier as dossier


def _report_e85(backend: str) -> dict:
    cases = []
    for name in dossier.CASES:
        truncated = name in {"visited_node_bound", "step_bound"}
        stop_reason = {"visited_node_bound": "max_visited_nodes", "step_bound": "max_traversal_steps"}.get(name)
        cases.append({
            "name": name, "status": "passed", "reference_parity": True,
            "repeat_deterministic": True, "truncated": truncated,
            "stop_reason": stop_reason,
            "graph_fingerprint": "graph:c6146d2473910927d9c7f113d92a4400",
        })
    worker = None
    if backend == "snap":
        worker = {
            "container_image_id": dossier.SNAP_IMAGE,
            "snap_version": "6.0.0", "python_version": "3.9.25",
            "request_timeout_enforced": True, "request_timeout_seconds": 120.0,
        }
    return {
        "backend": backend,
        "backend_execution": {
            "queries_attempted": 14, "queries_succeeded": 14, "queries_failed": 0,
            "parity_verified_queries": 14, "parity_failures": 0,
            "native_adjacency_lookups": 34, "native_edge_occurrences_read": 96,
        },
        "backend_native_query_mode": dossier.MODES[backend],
        "backend_loss_assessment": (
            {"lossless": False, "details": {
                "lossless": False,
                "scope": "hybrid_csr_plus_exact_semantic_side_channels",
                "lost": ["native_per_edge_relation_and_metadata_columns_inside_csr_matrix"],
                "preserved": ["directed_connectivity", "parallel_edge_multiplicity",
                              "semantic_node_identity_mapping", "exact_edge_occurrences_in_side_channel",
                              "relation_labels_in_side_channel", "node_and_edge_attributes_in_side_channel",
                              "node_and_edge_metadata_in_side_channel"],
            }} if backend == "scipy" else
            ({"lossless": True, "details": {"lossless": True, "lost": []}}
             if backend != "networkx" else None)
        ),
        "canonical_graph_fingerprint": "graph:c6146d2473910927d9c7f113d92a4400",
        "case_count": 7, "conformance_cases": cases,
        "filesystem_mutations": 0, "network_calls": 0, "provider_calls": 0,
        "native_library_version": dossier.VERSIONS[backend],
        "native_worker": worker,
        "projection_round_trip": {
            "status": "passed", "exact": True, "node_count": 5,
            "edge_occurrence_count": 8, "parallel_edge_occurrences": 3,
            "self_loop_occurrences": 1,
            "round_trip_sha256": "a2c0d12aed407f322c425c5c557ef58d7e52b2814b9e2e83ef01ff859ca77ab3",
        },
        "repository_code_executed": False, "repeated_query_count": 14,
        "schema_version": "ae32c/e85-native-backend-conformance/v1",
        "source_revision": dossier.SOURCE, "status": "passed",
        "workflow_name": dossier.WORKFLOW,
        "workflow_run_attempt": "1", "workflow_run_id": str(dossier.RUN),
    }


def _report_e88(backend: str) -> dict:
    worker = None
    if backend == "snap":
        worker = {
            "container_image_id": dossier.SNAP_IMAGE,
            "snap_version": "6.0.0", "python_version": "3.9.25",
            "request_timeout_enforced": True, "request_timeout_seconds": 30.0,
            "container_policy": copy.deepcopy(dossier.SNAP_POLICY),
            "graph_fingerprint": dossier.REPO["graph_fingerprint"],
            "node_count": 26, "edge_occurrence_count": 41,
        }
    telemetry = {
        "find_workflow_context": 16,
        "trace_execution_context": 7,
        "trace_execution_context.workflow_context": 16,
    }
    return {
        "backend": backend,
        "backend_execution": {
            "queries_attempted": 43, "queries_succeeded": 43, "queries_failed": 0,
            "parity_verified_queries": 43, "parity_failures": 0,
            "native_adjacency_lookups": 45, "native_edge_occurrences_read": 86,
        },
        "backend_library": backend,
        "backend_library_version": dossier.VERSIONS[backend],
        "backend_native_query_mode": dossier.MODES[backend],
        "backend_queries": {
            "find_related_tests": "selected_backend_and_reference_parity_verified",
            "graph_neighbors": "selected_backend_and_reference_parity_verified",
            "graph_path": "selected_backend_and_reference_parity_verified",
            "find_workflow_context": {"status": "complete_for_query"},
            "trace_execution_context": {"status": "complete_for_query"},
            "trace_nested_find_workflow_context": {"status": "complete_for_query"},
        },
        "context_operation_telemetry": {
            name: {
                "adjacency_queries_attempted": count,
                "adjacency_queries_succeeded": count,
                "adjacency_queries_failed": 0,
                "parity_verified": count, "parity_failures": 0,
            } for name, count in telemetry.items()
        },
        "graph_to_repository_follow_through": {
            "status": "passed", "verified_read_count": 2,
            "reads": [
                {"path": name, "line_count": lines, "source_sha256": sha,
                 "source_range_complete": True}
                for name, (lines, sha) in dossier.READS.items()
            ],
        },
        "graph_path": {"path_found": True},
        "related_tests": {"candidate_count": 1, "returned_count": 1},
        "repository_snapshot": copy.deepcopy(dossier.REPO),
        "required_graph_query": {"coverage_status": "complete_for_query", "direction": "incoming",
                                 "target": "symbol:pipeline.extractor::extract",
                                 "source_paths": ["main.py", "pipeline/extractor.py", "tests/checks.py"]},
        "native_worker": worker,
        "side_effects": {
            "network_calls_performed": False, "provider_calls_made": False,
            "repository_code_executed": False, "source_files_modified": False,
            "tests_executed_by_backend": False,
        },
        "schema_version": "ae32c/repository-backend-conformance/v1",
        "source_revision": dossier.SOURCE, "status": "passed",
        "workflow_name": dossier.WORKFLOW,
        "workflow_run_attempt": "1", "workflow_run_id": str(dossier.RUN),
    }


class DossierVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.artifact_dir = self.root / "artifacts"
        self.artifact_dir.mkdir()
        self.manifest = {
            "run_id": dossier.RUN, "run_attempt": dossier.ATTEMPT,
            "workflow_name": dossier.WORKFLOW,
            "head_branch": "stage1/section-uuids",
            "source_revision": dossier.SOURCE,
            "artifacts": [],
        }
        for index, backend in enumerate(dossier.BACKENDS, start=1):
            path = self.artifact_dir / (backend.replace("-", "_") + ".zip")
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(f"e85-{backend}.json", json.dumps(_report_e85(backend)))
                archive.writestr(f"e88-{backend}-repository.json", json.dumps(_report_e88(backend)))
            self.manifest["artifacts"].append({
                "id": 900000 + index,
                "name": dossier.ARTIFACTS[backend],
                "expired": False,
                "size_in_bytes": path.stat().st_size,
                "digest": "sha256:" + dossier.file_sha(path),
                "workflow_run": {
                    "id": dossier.RUN, "head_branch": "stage1/section-uuids",
                    "head_sha": dossier.SOURCE,
                    "repository_id": 1346375418, "head_repository_id": 1346375418,
                },
            })

    def tearDown(self):
        self.temp.cleanup()

    def _refresh_metadata(self, backend):
        artifact = next(item for item in self.manifest["artifacts"]
                        if item["name"] == dossier.ARTIFACTS[backend])
        path = self.artifact_dir / (backend.replace("-", "_") + ".zip")
        artifact["size_in_bytes"] = path.stat().st_size
        artifact["size_in_bytes"] = path.stat().st_size
        artifact["digest"] = "sha256:" + dossier.file_sha(path)

    def test_complete_five_backend_set_verifies(self):
        result = dossier.verify(self.artifact_dir, self.manifest)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["campaign"]["backends"], list(dossier.BACKENDS))
        self.assertEqual(len(result["artifacts"]), 5)
        self.assertTrue(result["interpretation"]["computational_options_not_competitors"])
        self.assertFalse(result["interpretation"]["performance_winner_established"])
        self.assertFalse(result["interpretation"]["production_approval"])

    def test_missing_backend_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["artifacts"].pop()
        with self.assertRaisesRegex(dossier.DossierError, "manifest_requires_five_artifacts"):
            dossier.verify(self.artifact_dir, manifest)

    def test_expired_artifact_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["artifacts"][0]["expired"] = True
        with self.assertRaisesRegex(dossier.DossierError, "artifact_expired_or_digest_invalid"):
            dossier.verify(self.artifact_dir, manifest)

    def test_mixed_source_revision_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["artifacts"][0]["workflow_run"]["head_sha"] = "0" * 40
        with self.assertRaisesRegex(dossier.DossierError, "artifact_source_binding"):
            dossier.verify(self.artifact_dir, manifest)

    def test_wrong_archive_digest_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["artifacts"][0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(dossier.DossierError, "artifact_archive_digest_or_size"):
            dossier.verify(self.artifact_dir, manifest)

    def test_duplicate_artifact_id_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["artifacts"][1]["id"] = manifest["artifacts"][0]["id"]
        with self.assertRaisesRegex(dossier.DossierError, "artifact_id_invalid"):
            dossier.verify(self.artifact_dir, manifest)

    def test_wrong_report_source_revision_is_rejected(self):
        path = self.artifact_dir / "networkx.zip"
        with zipfile.ZipFile(path) as source:
            members = {name: source.read(name) for name in source.namelist()}
        report = json.loads(members["e85-networkx.json"])
        report["source_revision"] = "0" * 40
        members["e85-networkx.json"] = json.dumps(report).encode()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, content in members.items(): target.writestr(name, content)
        self._refresh_metadata("networkx")
        with self.assertRaisesRegex(dossier.DossierError, "source_sha_mismatch:networkx:e85"):
            dossier.verify(self.artifact_dir, self.manifest)

    def test_e85_reference_parity_failure_is_rejected(self):
        path = self.artifact_dir / "networkx.zip"
        with zipfile.ZipFile(path) as source:
            members = {name: source.read(name) for name in source.namelist()}
        report = json.loads(members["e85-networkx.json"])
        report["backend_execution"]["parity_failures"] = 1
        members["e85-networkx.json"] = json.dumps(report).encode()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, content in members.items(): target.writestr(name, content)
        self._refresh_metadata("networkx")
        with self.assertRaisesRegex(dossier.DossierError, "e85_telemetry:networkx:parity_failures"):
            dossier.verify(self.artifact_dir, self.manifest)

    def test_incomplete_context_telemetry_is_rejected(self):
        path = self.artifact_dir / "snap.zip"
        with zipfile.ZipFile(path) as source:
            members = {name: source.read(name) for name in source.namelist()}
        report = json.loads(members["e88-snap-repository.json"])
        del report["context_operation_telemetry"]["trace_execution_context"]
        members["e88-snap-repository.json"] = json.dumps(report).encode()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, content in members.items(): target.writestr(name, content)
        self._refresh_metadata("snap")
        with self.assertRaisesRegex(dossier.DossierError, "e88_context_telemetry_keys:snap"):
            dossier.verify(self.artifact_dir, self.manifest)

    def test_zip_extra_member_is_rejected(self):
        path = self.artifact_dir / "igraph.zip"
        with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("unexpected.txt", "untrusted extra")
        self._refresh_metadata("igraph")
        with self.assertRaisesRegex(dossier.DossierError, "zip_member_set:igraph"):
            dossier.verify(self.artifact_dir, self.manifest)

    def test_snap_container_policy_is_verified(self):
        path = self.artifact_dir / "snap.zip"
        with zipfile.ZipFile(path) as source:
            members = {name: source.read(name) for name in source.namelist()}
        report = json.loads(members["e88-snap-repository.json"])
        report["native_worker"]["container_policy"]["network"] = "bridge"
        members["e88-snap-repository.json"] = json.dumps(report).encode()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, content in members.items(): target.writestr(name, content)
        self._refresh_metadata("snap")
        with self.assertRaisesRegex(dossier.DossierError, "snap_e88_isolation:"):
            dossier.verify(self.artifact_dir, self.manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)

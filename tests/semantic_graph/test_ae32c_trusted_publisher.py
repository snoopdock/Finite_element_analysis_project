from __future__ import annotations

import unittest

from tools.ae32c_trusted_publisher import (
    PublisherError,
    build_expected_metadata,
    select_expected_artifact,
)


class TrustedPublisherMetadataTests(unittest.TestCase):
    def setUp(self):
        self.run = {
            "id": 12345,
            "run_attempt": 2,
            "run_number": 88,
            "workflow_id": 430355742,
            "path": ".github/workflows/ae32c_source_snapshot_manifest.yml",
            "head_sha": "a" * 40,
            "head_branch": "main",
            "head_repository": {"full_name": "snoopdock/Finite_element_analysis_project"},
            "event": "push",
            "conclusion": "success",
        }
        self.repository = {
            "full_name": "snoopdock/Finite_element_analysis_project",
            "default_branch": "main",
        }

    def test_expected_metadata_is_built_from_api_values(self):
        value = build_expected_metadata(
            self.run, self.repository, "snoopdock/Finite_element_analysis_project"
        )
        self.assertEqual(value["workflow_id"], 430355742)
        self.assertEqual(value["workflow_path"], ".github/workflows/ae32c_source_snapshot_manifest.yml")
        self.assertEqual(value["ref"], "refs/heads/main")
        self.assertEqual(value["run_attempt"], 2)

    def test_missing_head_repository_is_rejected(self):
        run = dict(self.run)
        run["head_repository"] = None
        with self.assertRaisesRegex(PublisherError, "upstream_run_metadata_incomplete"):
            build_expected_metadata(
                run, self.repository, "snoopdock/Finite_element_analysis_project"
            )

    def test_exact_artifact_name_and_digest_are_required(self):
        artifact = {
            "id": 999,
            "name": "ae32c-source-graph-snapshot-12345-2",
            "expired": False,
            "digest": "sha256:" + "b" * 64,
        }
        selected = select_expected_artifact([artifact], run_id=12345, run_attempt=2)
        self.assertEqual(selected["id"], 999)

    def test_duplicate_artifact_name_is_rejected(self):
        artifact = {
            "id": 999,
            "name": "ae32c-source-graph-snapshot-12345-2",
            "expired": False,
            "digest": "sha256:" + "b" * 64,
        }
        with self.assertRaisesRegex(PublisherError, "missing_or_duplicated"):
            select_expected_artifact([artifact, dict(artifact, id=1000)], run_id=12345, run_attempt=2)

    def test_expired_artifact_is_rejected(self):
        artifact = {
            "id": 999,
            "name": "ae32c-source-graph-snapshot-12345-2",
            "expired": True,
            "digest": "sha256:" + "b" * 64,
        }
        with self.assertRaisesRegex(PublisherError, "artifact_expired"):
            select_expected_artifact([artifact], run_id=12345, run_attempt=2)

    def test_missing_artifact_digest_is_rejected(self):
        artifact = {
            "id": 999,
            "name": "ae32c-source-graph-snapshot-12345-2",
            "expired": False,
        }
        with self.assertRaisesRegex(PublisherError, "digest_missing"):
            select_expected_artifact([artifact], run_id=12345, run_attempt=2)


if __name__ == "__main__":
    unittest.main()

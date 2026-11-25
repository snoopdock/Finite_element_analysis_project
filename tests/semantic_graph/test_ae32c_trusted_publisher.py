from __future__ import annotations

import io
import unittest
from email.message import Message
from unittest.mock import patch

from tools.ae32c_trusted_publisher import (
    PublisherError,
    build_expected_metadata,
    select_expected_artifact,
    _download_artifact,
)


class TrustedPublisherMetadataTests(unittest.TestCase):
    def setUp(self):
        self.run = {
            "id": 12345,
            "repository": {"full_name": "snoopdock/Finite_element_analysis_project"},
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

    def test_wrong_run_repository_is_rejected(self):
        run = dict(self.run)
        run["repository"] = {"full_name": "attacker/other"}
        with self.assertRaisesRegex(PublisherError, "upstream_run_repository_mismatch"):
            build_expected_metadata(run, self.repository, "snoopdock/Finite_element_analysis_project")

    def test_artifact_head_sha_must_match_run(self):
        artifact = {
            "id": 999, "name": "ae32c-source-graph-snapshot-12345-2",
            "expired": False, "digest": "sha256:" + "b" * 64,
            "workflow_run": {"id": 12345, "head_sha": "c" * 40},
        }
        with self.assertRaisesRegex(PublisherError, "artifact_workflow_head_sha_mismatch"):
            select_expected_artifact([artifact], run_id=12345, run_attempt=2, head_sha="a" * 40)

    def test_artifact_redirect_does_not_forward_api_token_to_other_origin(self):
        headers = Message()
        headers["Location"] = "https://objects.example.invalid/artifact.zip"
        class FakeOpener:
            def __init__(self):
                self.calls = []
            def open(self, request, timeout):
                self.calls.append(request)
                if len(self.calls) == 1:
                    from urllib.error import HTTPError
                    raise HTTPError(request.full_url, 302, "Found", headers, io.BytesIO())
                return io.BytesIO(b"zip-bytes")
        fake = FakeOpener()
        with patch("urllib.request.build_opener", return_value=fake):
            payload = _download_artifact("https://api.github.com", "secret-token",
                "snoopdock/Finite_element_analysis_project", 999)
        self.assertEqual(payload, b"zip-bytes")
        self.assertEqual(fake.calls[0].get_header("Authorization"), "Bearer secret-token")
        self.assertIsNone(fake.calls[1].get_header("Authorization"))
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
            "workflow_run": {"id": 12345, "head_sha": "a" * 40},
        }
        selected = select_expected_artifact(
            [artifact], run_id=12345, run_attempt=2, head_sha="a" * 40
        )
        self.assertEqual(selected["id"], 999)

    def test_duplicate_artifact_name_is_rejected(self):
        artifact = {
            "id": 999,
            "name": "ae32c-source-graph-snapshot-12345-2",
            "expired": False,
            "digest": "sha256:" + "b" * 64,
            "workflow_run": {"id": 12345, "head_sha": "a" * 40},
        }
        with self.assertRaisesRegex(PublisherError, "missing_or_duplicated"):
            select_expected_artifact([artifact, dict(artifact, id=1000)], run_id=12345, run_attempt=2)

    def test_expired_artifact_is_rejected(self):
        artifact = {
            "id": 999,
            "name": "ae32c-source-graph-snapshot-12345-2",
            "expired": True,
            "digest": "sha256:" + "b" * 64,
            "workflow_run": {"id": 12345, "head_sha": "a" * 40},
        }
        with self.assertRaisesRegex(PublisherError, "artifact_expired"):
            select_expected_artifact([artifact], run_id=12345, run_attempt=2)

    def test_missing_artifact_digest_is_rejected(self):
        artifact = {
            "id": 999,
            "name": "ae32c-source-graph-snapshot-12345-2",
            "expired": False,
            "workflow_run": {"id": 12345, "head_sha": "a" * 40},
        }
        with self.assertRaisesRegex(PublisherError, "digest_missing"):
            select_expected_artifact([artifact], run_id=12345, run_attempt=2)


if __name__ == "__main__":
    unittest.main()

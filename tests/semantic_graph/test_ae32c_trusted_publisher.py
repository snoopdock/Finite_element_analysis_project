from __future__ import annotations

import io
import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from email.message import Message
from unittest.mock import patch

from test_ae32c_trusted_artifact import fixtures as artifact_fixtures, REPOSITORY, COMMIT

from tools.ae32c_trusted_publisher import (
    PublisherError,
    build_expected_metadata,
    select_expected_artifact,
    _download_artifact,
    prepare,
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




class TrustedPublisherPrepareIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.source, self.graph, self.expected = artifact_fixtures()
        self.run = {
            "id": 100,
            "repository": {"full_name": REPOSITORY},
            "run_attempt": 1,
            "run_number": 51,
            "workflow_id": 430355742,
            "path": ".github/workflows/ae32c_source_snapshot_manifest.yml",
            "head_sha": COMMIT,
            "head_branch": "main",
            "head_repository": {"full_name": REPOSITORY},
            "event": "push",
            "conclusion": "success",
        }
        self.repo_meta = {"full_name": REPOSITORY, "default_branch": "main"}
        self.archive = self._archive_bytes()
        self.artifact = {
            "id": 7654,
            "name": "ae32c-source-graph-snapshot-100-1",
            "expired": False,
            "digest": "sha256:" + hashlib.sha256(self.archive).hexdigest(),
            "workflow_run": {"id": 100, "head_sha": COMMIT},
        }

    def _archive_bytes(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("source-snapshot-manifest.json", json.dumps(self.source))
            archive.writestr("graph-snapshot-manifest.json", json.dumps(self.graph))
        return buffer.getvalue()

    def _api_responses(self, run=None, artifacts=None):
        return [
            run or self.run,
            self.repo_meta,
            {"artifacts": [self.artifact] if artifacts is None else artifacts},
        ]

    def test_prepare_validates_exact_api_run_artifact_and_writes_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            output_path = Path(tmp) / "prepared.json"
            # Only the upstream run ID is read from the event payload. Authority
            # fields are independently retrieved from the GitHub API.
            event_path.write_text(json.dumps({
                "workflow_run": {"id": 100, "head_branch": "attacker-controlled"}
            }), encoding="utf-8")
            with patch("tools.ae32c_trusted_publisher._api_json",
                       side_effect=self._api_responses()) as api_call, \
                 patch("tools.ae32c_trusted_publisher._download_artifact",
                       return_value=self.archive) as download:
                result = prepare(
                    api_url="https://api.github.com", read_token="read-only-token",
                    repository=REPOSITORY, event_path=str(event_path),
                    output_path=str(output_path), trusted_root=str(Path.cwd()),
                )
            self.assertTrue(result["current_eligible"])
            self.assertEqual(result["artifact_id"], 7654)
            self.assertEqual(result["artifact_sha256"], hashlib.sha256(self.archive).hexdigest())
            self.assertEqual(result["record"]["source_revision"], COMMIT)
            self.assertEqual(json.loads(output_path.read_text())["record"], result["record"])
            self.assertEqual(api_call.call_count, 3)
            download.assert_called_once_with("https://api.github.com", "read-only-token", REPOSITORY, 7654)

    def test_prepare_rejects_artifact_byte_digest_mismatch(self):
        bad_artifact = dict(self.artifact, digest="sha256:" + "0" * 64)
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text(json.dumps({"workflow_run": {"id": 100}}), encoding="utf-8")
            with patch("tools.ae32c_trusted_publisher._api_json",
                       side_effect=self._api_responses(artifacts=[bad_artifact])), \
                 patch("tools.ae32c_trusted_publisher._download_artifact",
                       return_value=self.archive):
                with self.assertRaisesRegex(PublisherError, "upstream_artifact_digest_mismatch"):
                    prepare(
                        api_url="https://api.github.com", read_token="read-only-token",
                        repository=REPOSITORY, event_path=str(event_path),
                        output_path=str(Path(tmp) / "prepared.json"),
                        trusted_root=str(Path.cwd()),
                    )

    def test_prepare_rejects_event_run_id_disagreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text(json.dumps({"workflow_run": {"id": 101}}), encoding="utf-8")
            with patch("tools.ae32c_trusted_publisher._api_json",
                       side_effect=self._api_responses()):
                with self.assertRaisesRegex(PublisherError, "workflow_run_id_disagrees_with_event"):
                    prepare(
                        api_url="https://api.github.com", read_token="read-only-token",
                        repository=REPOSITORY, event_path=str(event_path),
                        output_path=str(Path(tmp) / "prepared.json"),
                        trusted_root=str(Path.cwd()),
                    )

    def test_prepare_rejects_non_allowlisted_workflow_before_artifact_download(self):
        bad_run = dict(self.run, workflow_id=999)
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text(json.dumps({"workflow_run": {"id": 100}}), encoding="utf-8")
            with patch("tools.ae32c_trusted_publisher._api_json",
                       side_effect=self._api_responses(run=bad_run)), \
                 patch("tools.ae32c_trusted_publisher._download_artifact",
                       return_value=self.archive) as download:
                with self.assertRaisesRegex(PublisherError, "producer_workflow_not_allowlisted"):
                    prepare(
                        api_url="https://api.github.com", read_token="read-only-token",
                        repository=REPOSITORY, event_path=str(event_path),
                        output_path=str(Path(tmp) / "prepared.json"),
                        trusted_root=str(Path.cwd()),
                    )
            download.assert_not_called()

    def test_prepare_rejects_incomplete_coverage_as_current_but_retains_record(self):
        source, graph, expected = artifact_fixtures(represented=False)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("source-snapshot-manifest.json", json.dumps(source))
            archive.writestr("graph-snapshot-manifest.json", json.dumps(graph))
        raw = buffer.getvalue()
        artifact = dict(self.artifact, digest="sha256:" + hashlib.sha256(raw).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            output_path = Path(tmp) / "prepared.json"
            event_path.write_text(json.dumps({"workflow_run": {"id": 100}}), encoding="utf-8")
            with patch("tools.ae32c_trusted_publisher._api_json",
                       side_effect=self._api_responses(artifacts=[artifact])), \
                 patch("tools.ae32c_trusted_publisher._download_artifact",
                       return_value=raw):
                result = prepare(
                    api_url="https://api.github.com", read_token="read-only-token",
                    repository=REPOSITORY, event_path=str(event_path),
                    output_path=str(output_path), trusted_root=str(Path.cwd()),
                )
            self.assertFalse(result["current_eligible"])
            self.assertEqual(result["record"]["outcome"], "INCOMPLETE")
            self.assertTrue(output_path.is_file())

if __name__ == "__main__":
    unittest.main()

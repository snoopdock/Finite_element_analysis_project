"""M7.5.26 cross-layer snapshot identity and provenance tests."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.ae32c_source_snapshot_manifest import capture_manifest, verify_manifest
from audit_engine.semantic_audit.epistemic.cross_layer_snapshot_provenance import (
    CrossLayerSnapshotProvenanceError, verify_cross_layer_snapshot_provenance,
    verify_cross_layer_snapshot_provenance_envelope,
)


def seal(value, key):
    import hashlib
    payload = {name: item for name, item in value.items() if name != key}
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False) + "\n").encode()
    return {**payload, key: hashlib.sha256(raw).hexdigest()}


class M7526SnapshotProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "m7526@example.invalid")
        self._git("config", "user.name", "M7526")
        (self.root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-qm", "snapshot")
        self.commit = self._git("rev-parse", "HEAD")
        captured = capture_manifest(self.root, expected_source_revision=self.commit,
            event_name="push", repository_name="example/repository", ref="refs/heads/test")
        self.manifest_path = self.root.parent / "source-manifest.json"
        self.manifest_path.write_text(json.dumps(captured), encoding="utf-8")
        self.manifest = verify_manifest(self.root, self.manifest_path,
                                         expected_source_revision=self.commit)
        self._build_artifacts()

    def tearDown(self):
        self.temp.cleanup()

    def _git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return result.stdout.decode().strip()

    def _build_artifacts(self):
        source_id = self.manifest["source_snapshot_id"]
        self.claim_id, self.plan_id, self.coverage_id = "claim:m7526", "a" * 64, "b" * 64
        self.bundle = seal({"schema": "ae32c/typed-evidence-observation-bundle/v1",
            "source_snapshot_id": source_id, "plan_sha256": self.plan_id, "observations": []},
            "bundle_sha256")
        self.qualification = seal({"schema": "ae32c/semantic-evidence-qualification/v1",
            "source_snapshot_id": source_id,
            "observation_bundle_sha256": self.bundle["bundle_sha256"],
            "contract_registry_sha256": "c" * 64, "qualifications": []}, "qualification_sha256")
        self.execution = seal({"schema": "ae32c/execution-obligation-reconciliation/v1",
            "claim_id": self.claim_id, "source_snapshot_id": source_id,
            "source_manifest_sha256": self.manifest["manifest_sha256"],
            "plan_sha256": self.plan_id, "coverage_manifest_sha256": self.coverage_id},
            "reconciliation_sha256")
        self.qualification_reconciliation = seal({
            "schema": "ae32c/qualification-obligation-reconciliation/v1",
            "claim_id": self.claim_id, "source_snapshot_id": source_id,
            "plan_sha256": self.plan_id, "coverage_manifest_sha256": self.coverage_id,
            "qualification_sha256": self.qualification["qualification_sha256"],
            "observation_bundle_sha256": self.bundle["bundle_sha256"]},
            "reconciliation_sha256")
        self.composition = seal({
            "schema": "ae32c/execution-semantic-obligation-composition/v1",
            "claim_id": self.claim_id, "source_snapshot_id": source_id,
            "plan_sha256": self.plan_id, "coverage_manifest_sha256": self.coverage_id,
            "execution_reconciliation_sha256": self.execution["reconciliation_sha256"],
            "qualification_reconciliation_sha256": self.qualification_reconciliation["reconciliation_sha256"],
            "qualification_currentness": {"state": "CURRENT_REPLAY_VERIFIED"}},
            "composition_sha256")
        consumer = {"record_id": self.qualification_reconciliation["reconciliation_sha256"],
            "consumer_id": "test-consumer", "operation": "verify",
            "downstream_authorization": "NOT_EVALUATED"}
        self.orchestration = seal({
            "schema": "ae32c/orchestrated-persisted-obligation-composition/v1",
            "execution_reconciliation_sha256": self.execution["reconciliation_sha256"],
            "qualification_reconciliation_sha256": self.qualification_reconciliation["reconciliation_sha256"],
            "execution_replay": {"reconciliation_sha256": self.execution["reconciliation_sha256"],
                "ledger_integrity": True, "semantic_replay": True},
            "execution_replay_bracket": {"reconciliation_sha256": self.execution["reconciliation_sha256"],
                "pre_qualification_replay_verified": True, "post_qualification_replay_verified": True,
                "results_identical": True, "atomic_cross_store_snapshot": False},
            "qualification_consumer_result": consumer, "composition": self.composition},
            "orchestration_sha256")

    def _verify(self, **kwargs):
        return verify_cross_layer_snapshot_provenance(
            self.manifest, self.execution, self.qualification_reconciliation,
            self.qualification, self.bundle, self.orchestration, **kwargs)

    def test_declared_identity_is_not_misreported_as_source_state_replay(self):
        result = self._verify()
        self.assertEqual(result["provenance_status"], "COMPLETE")
        self.assertEqual(result["snapshot_identity_assurance"], "DECLARED_ONLY")
        self.assertFalse(result["source_state_verification"]["source_state_replay_verified"])
        self.assertFalse(result["atomic_cross_store_snapshot"])
        self.assertEqual(result["trust_anchor"], "NONE")

    def test_repository_replay_verifies_commit_tree_inventory_and_cleanliness(self):
        result = self._verify(repository_root=self.root, expected_source_revision=self.commit)
        self.assertEqual(result["snapshot_identity_assurance"], "SOURCE_STATE_REPLAY_VERIFIED")
        self.assertTrue(result["source_state_verification"]["source_state_replay_verified"])
        self.assertEqual(result["source_state_verification"]["commit_oid"], self.commit)

    def test_stale_repository_state_is_rejected(self):
        (self.root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-qm", "mutate source after capture")
        with self.assertRaisesRegex(CrossLayerSnapshotProvenanceError, "source_state_replay_failed"):
            self._verify(repository_root=self.root)

    def test_cross_artifact_snapshot_mismatch_is_rejected(self):
        changed = dict(self.qualification_reconciliation, source_snapshot_id="d" * 64)
        self.qualification_reconciliation = seal(changed, "reconciliation_sha256")
        with self.assertRaisesRegex(CrossLayerSnapshotProvenanceError, "snapshot_binding_mismatch"):
            self._verify()

    def test_execution_manifest_digest_mismatch_is_rejected(self):
        changed = dict(self.execution, source_manifest_sha256="e" * 64)
        self.execution = seal(changed, "reconciliation_sha256")
        with self.assertRaisesRegex(CrossLayerSnapshotProvenanceError, "execution_source_manifest_binding_mismatch"):
            self._verify()

    def test_missing_observation_bundle_fails_closed(self):
        with self.assertRaises(TypeError):
            verify_cross_layer_snapshot_provenance(self.manifest, self.execution,
                self.qualification_reconciliation, self.qualification, None, self.orchestration)

    def test_manifest_tampering_is_rejected(self):
        changed = dict(self.manifest)
        changed["source"] = dict(changed["source"], commit_oid="f" * len(self.commit))
        with self.assertRaisesRegex(CrossLayerSnapshotProvenanceError, "source_manifest_digest_mismatch"):
            verify_cross_layer_snapshot_provenance(changed, self.execution,
                self.qualification_reconciliation, self.qualification, self.bundle, self.orchestration)

    def test_orchestration_reference_tampering_is_rejected(self):
        changed = dict(self.orchestration, qualification_reconciliation_sha256="f" * 64)
        with self.assertRaisesRegex(CrossLayerSnapshotProvenanceError, "orchestration_digest_mismatch"):
            verify_cross_layer_snapshot_provenance(self.manifest, self.execution,
                self.qualification_reconciliation, self.qualification, self.bundle, changed)

    def test_envelope_checker_does_not_claim_repository_replay(self):
        result = self._verify()
        checked = verify_cross_layer_snapshot_provenance_envelope(result)
        self.assertTrue(checked["content_binding_verified"])
        self.assertFalse(checked["source_state_replay_performed"])
        changed = dict(result, production_approval=True)
        with self.assertRaisesRegex(CrossLayerSnapshotProvenanceError, "provenance_envelope_digest_mismatch"):
            verify_cross_layer_snapshot_provenance_envelope(changed)


if __name__ == "__main__":
    unittest.main()

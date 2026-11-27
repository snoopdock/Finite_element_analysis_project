"""M7.5.21 tests for currentness-gated persisted qualification replay."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit_engine.semantic_audit.epistemic.qualification_reconciliation_store import (
    QualificationReconciliationStore,
    evaluate_persisted_qualification_reconciliation_currentness,
)
from audit_engine.semantic_audit.epistemic.qualification_reconciliation import (
    QualificationReconciliationError,
)
from audit_engine.semantic_audit.epistemic.qualification_consumer_gate import (
    QualificationConsumerCheckStore,
)
from audit_engine.semantic_audit.epistemic.qualification_reconciliation_consumer import (
    QualificationConsumerReplayError,
    qualification_consumer_current_context,
    verify_persisted_qualification_reconciliation_for_consumer,
)
import test_m7517_qualification_reconciliation as m7517


class QualificationReconciliationConsumerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = m7517.QualificationReconciliationTests()
        self.fixture.setUp()
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.reconciliation_store = QualificationReconciliationStore(
            root / "reconciliation.sqlite")
        self.check_store = QualificationConsumerCheckStore(root / "consumer.sqlite")
        observation = self.fixture.syntax_observation("src/broken_a.py")
        self.bundle, self.qualification = self.fixture.qualification([observation])
        self.reconciliation = self.fixture.reconcile(self.bundle, self.qualification)
        self.record_id = self.reconciliation["reconciliation_sha256"]
        self.reconciliation_store.record(
            self.reconciliation, self.qualification, self.bundle)
        self.context = qualification_consumer_current_context(
            claim=self.fixture.claim,
            plan=self.fixture.plan,
            coverage_manifest=self.fixture.coverage_manifest,
            current_qualification=self.qualification,
            current_observation_bundle=self.bundle,
            source_manifest=self.fixture.source_manifest,
        )

    def tearDown(self):
        self.reconciliation_store.close()
        self.check_store.close()
        self.tmp.cleanup()
        self.fixture.tearDown()

    def consume(self, **overrides):
        args = {
            "record_id": self.record_id,
            "consumer_id": "qualification-replay-verifier",
            "operation": "verify-persisted-qualification-reconciliation",
            "reconciliation_store": self.reconciliation_store,
            "check_store": self.check_store,
            "current_context": self.context,
            "claim": self.fixture.claim,
            "plan": self.fixture.plan,
            "coverage_manifest": self.fixture.coverage_manifest,
            "current_qualification": self.qualification,
            "current_observation_bundle": self.bundle,
            "source_manifest": self.fixture.source_manifest,
            "repository_root": self.fixture.root,
        }
        args.update(overrides)
        return verify_persisted_qualification_reconciliation_for_consumer(**args)

    def test_current_consumer_preflight_is_followed_by_semantic_replay(self):
        result = self.consume()
        self.assertEqual(result["consumer_operation_status"], "REPLAY_VERIFIED")
        self.assertTrue(result["semantic_replay_performed"])
        self.assertTrue(result["replay_result"]["semantic_replay"])
        self.assertEqual(result["downstream_authorization"], "NOT_EVALUATED")
        self.assertEqual(result["preflight"]["consumer_preflight_status"],
                         "CURRENTNESS_CONFIRMED")
        self.assertEqual(len(self.check_store.history()), 1)

    def test_historically_invalidated_record_is_blocked_without_replay(self):
        changed = dict(self.context, plan_sha256="f" * 64)
        evaluate_persisted_qualification_reconciliation_currentness(
            self.record_id, store=self.reconciliation_store,
            current_context=changed)
        with patch(
            "audit_engine.semantic_audit.epistemic.qualification_reconciliation_consumer."
            "verify_persisted_qualification_reconciliation"
        ) as replay:
            result = self.consume()
        replay.assert_not_called()
        self.assertEqual(result["consumer_operation_status"], "BLOCKED_INVALIDATED")
        self.assertFalse(result["semantic_replay_performed"])
        self.assertIsNone(result["replay_result"])
        self.assertEqual(result["preflight"]["consumer_preflight_status"],
                         "BLOCKED_INVALIDATED")
        self.assertEqual(len(self.check_store.history()), 1)

    def test_caller_cannot_supply_context_that_disagrees_with_live_artifacts(self):
        altered = dict(self.context, plan_sha256="0" * 64)
        with self.assertRaisesRegex(
                QualificationConsumerReplayError,
                "caller_current_context_does_not_match_live_artifacts"):
            self.consume(current_context=altered)
        self.assertEqual(len(self.check_store.history()), 0)

    def test_live_artifact_context_is_derived_from_all_eight_dimensions(self):
        self.assertEqual(set(self.context), {
            "source_snapshot_id", "plan_sha256", "rule_registry_sha256",
            "coverage_manifest_sha256", "contract_registry_sha256",
            "aggregation_policy_registry_sha256", "qualification_sha256",
            "observation_bundle_sha256",
        })
        self.assertEqual(self.context["plan_sha256"], self.fixture.plan.plan_sha256)
        self.assertEqual(self.context["coverage_manifest_sha256"],
                         self.fixture.coverage_manifest.manifest_sha256)

    def test_source_bytes_drift_after_currentness_preflight_fails_semantic_replay(self):
        (self.fixture.root / "src/broken_a.py").write_text("import os\n")
        with self.assertRaises(QualificationReconciliationError):
            self.consume()
        # The preflight is only a currentness assertion over supplied context;
        # semantic replay remains independently necessary and rejects source drift.
        self.assertEqual(len(self.check_store.history()), 1)
        event = self.check_store.get(self.check_store.history()[0]["check_id"])
        self.assertEqual(event["consumer_preflight_status"], "CURRENTNESS_CONFIRMED")


if __name__ == "__main__":
    unittest.main()

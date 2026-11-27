"""M7.5.20 downstream qualification-currentness consumer gate tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic.qualification_reconciliation_store import (
    QualificationReconciliationStore, QualificationReconciliationStoreError,
)
from audit_engine.semantic_audit.epistemic.qualification_consumer_gate import (
    QualificationConsumerCheckStore,
    QualificationConsumerGateError,
    evaluate_qualification_reconciliation_for_consumer,
)
from test_m7518_qualification_reconciliation_store import artifacts


class QualificationConsumerGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.reconciliation_store = QualificationReconciliationStore(
            root / "reconciliation.sqlite")
        self.check_store = QualificationConsumerCheckStore(root / "consumer.sqlite")
        self.reconciliation, self.qualification, self.bundle = artifacts()
        self.reconciliation_store.record(
            self.reconciliation, self.qualification, self.bundle)
        self.record_id = self.reconciliation["reconciliation_sha256"]
        self.context = self.reconciliation_store.get(self.record_id)["context"]

    def tearDown(self):
        self.reconciliation_store.close()
        self.check_store.close()
        self.tmp.cleanup()

    def evaluate(self, **overrides):
        args = {
            "record_id": self.record_id,
            "consumer_id": "coverage-dossier-builder",
            "operation": "consume-qualification-reconciliation",
            "reconciliation_store": self.reconciliation_store,
            "check_store": self.check_store,
            "current_context": self.context,
        }
        args.update(overrides)
        return evaluate_qualification_reconciliation_for_consumer(**args)

    def test_currentness_preflight_is_recorded_without_authorizing_use(self):
        result = self.evaluate()
        self.assertEqual(result["consumer_preflight_status"], "CURRENTNESS_CONFIRMED")
        self.assertEqual(result["currentness_status"], "CURRENT")
        self.assertEqual(result["downstream_authorization"], "NOT_EVALUATED")
        self.assertFalse(result["semantic_replay_performed"])
        self.assertTrue(result["check_event_appended"])
        self.assertTrue(self.check_store.verify_integrity())
        self.assertEqual(len(self.check_store.history()), 1)

    def test_drift_is_invalidated_before_consumer_preflight_is_recorded(self):
        changed = dict(self.context, source_snapshot_id="snapshot:consumer-drift")
        result = self.evaluate(current_context=changed)
        self.assertEqual(result["currentness_status"], "INVALIDATED")
        self.assertEqual(result["consumer_preflight_status"], "BLOCKED_INVALIDATED")
        self.assertEqual(result["reason_codes"], ["SOURCE_SNAPSHOT_CHANGED"])
        self.assertEqual(len(self.reconciliation_store.invalidation_history(self.record_id)), 1)
        self.assertTrue(result["check_event_appended"])
        self.assertTrue(self.check_store.verify_integrity())

    def test_reverted_context_does_not_restore_consumer_preflight(self):
        self.evaluate(current_context=dict(self.context, plan_sha256="f" * 64))
        result = self.evaluate()
        self.assertEqual(result["currentness_status"], "INVALIDATED")
        self.assertEqual(result["consumer_preflight_status"], "BLOCKED_INVALIDATED")
        self.assertEqual(result["current_context_matches_record"], True)

    def test_identical_consumer_check_is_idempotent(self):
        first = self.evaluate()
        second = self.evaluate()
        self.assertTrue(first["check_event_appended"])
        self.assertFalse(second["check_event_appended"])
        self.assertEqual(first["check_id"], second["check_id"])
        self.assertEqual(len(self.check_store.history()), 1)

    def test_distinct_consumer_or_operation_has_distinct_check_identity(self):
        first = self.evaluate()
        second = self.evaluate(consumer_id="assurance-evaluator")
        third = self.evaluate(operation="render-coverage-report")
        self.assertNotEqual(first["check_id"], second["check_id"])
        self.assertNotEqual(first["check_id"], third["check_id"])
        self.assertEqual(len(self.check_store.history()), 3)

    def test_consumer_ledger_capacity_failure_fails_closed(self):
        self.check_store.close()
        self.check_store = QualificationConsumerCheckStore(
            Path(self.tmp.name) / "bounded.sqlite", max_records=1)
        self.evaluate()
        with self.assertRaisesRegex(QualificationConsumerGateError,
                                    "consumer_ledger_storage_limit_reached"):
            self.evaluate(operation="second-operation")

    def test_tampered_consumer_ledger_is_rejected(self):
        self.evaluate()
        self.check_store._db.execute(
            "DROP TRIGGER qualification_consumer_checks_no_update")
        self.check_store._db.execute(
            "UPDATE qualification_consumer_checks SET payload='{}' WHERE sequence=1")
        with self.assertRaisesRegex(QualificationConsumerGateError,
                                    "consumer_ledger_integrity_failure"):
            self.evaluate(operation="another-operation")

    def test_invalid_consumer_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "consumer_id_must_be_a_non_empty_string"):
            self.evaluate(consumer_id=" ")

    def test_missing_reconciliation_fails_before_any_consumer_event(self):
        with self.assertRaisesRegex(QualificationReconciliationStoreError,
                                    "reconciliation_record_not_found"):
            self.evaluate(record_id="missing-record")
        self.assertEqual(len(self.check_store.history()), 0)


if __name__ == "__main__":
    unittest.main()

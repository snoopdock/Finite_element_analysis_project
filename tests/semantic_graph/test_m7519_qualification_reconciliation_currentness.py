"""M7.5.19 qualification-reconciliation currentness gate tests."""
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic.qualification_reconciliation_store import (
    QualificationReconciliationStore,
    QualificationReconciliationStoreError,
    evaluate_persisted_qualification_reconciliation_currentness,
)
from test_m7518_qualification_reconciliation_store import artifacts


class QualificationReconciliationCurrentnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "qualification.sqlite"
        self.store = QualificationReconciliationStore(self.db)
        self.reconciliation, self.qualification, self.bundle = artifacts()
        self.store.record(self.reconciliation, self.qualification, self.bundle)
        self.record_id = self.reconciliation["reconciliation_sha256"]
        self.context = self.store.get(self.record_id)["context"]

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def evaluate(self, context):
        return evaluate_persisted_qualification_reconciliation_currentness(
            self.record_id, store=self.store, current_context=context)

    def test_matching_context_is_current_without_appending_event(self):
        result = self.evaluate(self.context)
        self.assertEqual(result["currentness_status"], "CURRENT")
        self.assertTrue(result["current_context_matches_record"])
        self.assertEqual(result["historical_invalidation_count"], 0)
        self.assertFalse(result["semantic_replay_performed"])
        self.assertEqual(result["downstream_authorization"], "NOT_EVALUATED")
        self.assertEqual(len(self.store.history()), 1)

    def test_context_drift_appends_invalidation_before_returning(self):
        changed = dict(self.context, source_snapshot_id="snapshot:next")
        result = self.evaluate(changed)
        self.assertEqual(result["currentness_status"], "INVALIDATED")
        self.assertFalse(result["current_context_matches_record"])
        self.assertEqual(result["current_reason_codes"], ["SOURCE_SNAPSHOT_CHANGED"])
        self.assertEqual(result["historical_invalidation_count"], 1)
        self.assertTrue(result["invalidation_event_appended"])
        self.assertEqual(len(self.store.history()), 2)
        self.assertTrue(self.store.verify_integrity())

    def test_invalidation_is_monotonic_even_if_context_reverts(self):
        changed = dict(self.context, plan_sha256="f" * 64)
        first = self.evaluate(changed)
        self.assertEqual(first["currentness_status"], "INVALIDATED")
        reverted = self.evaluate(self.context)
        self.assertEqual(reverted["currentness_status"], "INVALIDATED")
        self.assertTrue(reverted["current_context_matches_record"])
        self.assertEqual(reverted["current_reason_codes"], [])
        self.assertEqual(reverted["historical_invalidation_count"], 1)
        self.assertFalse(reverted["invalidation_event_appended"])

    def test_repeated_same_drift_is_idempotent(self):
        changed = dict(self.context,
                       aggregation_policy_registry_sha256="9" * 64)
        first = self.evaluate(changed)
        second = self.evaluate(changed)
        self.assertTrue(first["invalidation_event_appended"])
        self.assertFalse(second["invalidation_event_appended"])
        self.assertEqual(second["historical_invalidation_count"], 1)
        self.assertEqual(len(self.store.history()), 2)

    def test_distinct_drift_contexts_are_retained(self):
        first_context = dict(self.context, source_snapshot_id="snapshot:two")
        second_context = dict(self.context, plan_sha256="f" * 64)
        self.evaluate(first_context)
        result = self.evaluate(second_context)
        self.assertEqual(result["currentness_status"], "INVALIDATED")
        self.assertEqual(result["historical_invalidation_count"], 2)
        self.assertEqual(result["historical_reason_codes"], [
            "SOURCE_SNAPSHOT_CHANGED", "RULE_PLAN_CHANGED"])

    def test_unknown_record_is_rejected(self):
        with self.assertRaisesRegex(QualificationReconciliationStoreError,
                                    "reconciliation_record_not_found"):
            evaluate_persisted_qualification_reconciliation_currentness(
                "missing", store=self.store, current_context=self.context)

    def test_context_with_missing_or_extra_keys_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly_the_declared_context_keys"):
            self.evaluate({"source_snapshot_id": "snapshot:next"})
        extra = dict(self.context, unbound_dimension="x")
        with self.assertRaisesRegex(ValueError, "exactly_the_declared_context_keys"):
            self.evaluate(extra)

    def test_empty_context_value_is_rejected(self):
        invalid = dict(self.context, source_snapshot_id=" ")
        with self.assertRaisesRegex(ValueError, "non_empty_strings"):
            self.evaluate(invalid)

    def test_ledger_capacity_failure_never_returns_current(self):
        self.store.close()
        self.store = QualificationReconciliationStore(self.db, max_records=1)
        changed = dict(self.context, source_snapshot_id="snapshot:blocked")
        with self.assertRaisesRegex(QualificationReconciliationStoreError,
                                    "ledger_storage_limit_reached"):
            self.evaluate(changed)
        self.assertEqual(len(self.store.history()), 1)

    def test_gate_refuses_a_tampered_ledger(self):
        self.store._db.execute(
            "DROP TRIGGER qualification_reconciliation_no_update")
        self.store._db.execute(
            "UPDATE qualification_reconciliation_events SET payload='{}' "
            "WHERE sequence=1")
        with self.assertRaisesRegex(QualificationReconciliationStoreError,
                                    "ledger_integrity_failure"):
            self.evaluate(self.context)


if __name__ == "__main__":
    unittest.main()

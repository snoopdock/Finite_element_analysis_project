"""M7.5.18 persistent qualification reconciliation ledger tests."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic.qualification_reconciliation_store import (
    QualificationReconciliationStore,
    QualificationReconciliationStoreError,
    persist_verified_qualification_reconciliation,
    verify_persisted_qualification_reconciliation,
    qualification_reconciliation_context,
)
from test_m7517_qualification_reconciliation import QualificationReconciliationTests


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n"


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def artifacts():
    bundle_payload = {
        "schema": "ae32c/typed-evidence-observation-bundle/v1",
        "source_snapshot_id": "snapshot:ledger",
        "observations": [],
    }
    bundle = {**bundle_payload, "bundle_sha256": digest(bundle_payload)}
    qualification_payload = {
        "schema": "ae32c/semantic-evidence-qualification/v1",
        "source_snapshot_id": "snapshot:ledger",
        "observation_bundle_sha256": bundle["bundle_sha256"],
        "contract_registry_sha256": "a" * 64,
        "qualifications": [],
    }
    qualification = {
        **qualification_payload,
        "qualification_sha256": digest(qualification_payload),
    }
    reconciliation_payload = {
        "schema": "ae32c/qualification-obligation-reconciliation/v1",
        "claim_id": "claim:ledger",
        "source_snapshot_id": "snapshot:ledger",
        "plan_sha256": "b" * 64,
        "rule_registry_sha256": "c" * 64,
        "coverage_manifest_sha256": "d" * 64,
        "qualification_sha256": qualification["qualification_sha256"],
        "observation_bundle_sha256": bundle["bundle_sha256"],
        "aggregation_policy_registry_sha256": "e" * 64,
        "obligation_reconciliations": [],
        "summary": {},
    }
    reconciliation = {
        **reconciliation_payload,
        "reconciliation_sha256": digest(reconciliation_payload),
    }
    return reconciliation, qualification, bundle


class QualificationReconciliationLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "qualification.sqlite"
        self.store = QualificationReconciliationStore(self.db)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_context_helper_exposes_all_invalidation_dimensions(self):
        reconciliation, qualification, bundle = artifacts()
        context = qualification_reconciliation_context(
            reconciliation, qualification, bundle)
        self.assertEqual(set(context), {
            "source_snapshot_id", "plan_sha256", "rule_registry_sha256",
            "coverage_manifest_sha256", "contract_registry_sha256",
            "aggregation_policy_registry_sha256", "qualification_sha256",
            "observation_bundle_sha256",
        })

    def test_record_is_content_addressed_idempotent_and_restartable(self):
        reconciliation, qualification, bundle = artifacts()
        self.assertTrue(self.store.record(reconciliation, qualification, bundle))
        self.assertFalse(self.store.record(reconciliation, qualification, bundle))
        record_id = reconciliation["reconciliation_sha256"]
        self.assertEqual(self.store.get(record_id)["reconciliation"], reconciliation)
        self.assertTrue(self.store.verify_integrity())
        self.store.close()
        self.store = QualificationReconciliationStore(self.db)
        self.assertTrue(self.store.verify_integrity())
        self.assertEqual(self.store.get(record_id)["qualification"], qualification)

    def test_cross_artifact_binding_is_checked_before_append(self):
        reconciliation, qualification, bundle = artifacts()
        altered = dict(bundle)
        altered["source_snapshot_id"] = "snapshot:other"
        payload = {key: value for key, value in altered.items() if key != "bundle_sha256"}
        altered["bundle_sha256"] = digest(payload)
        with self.assertRaisesRegex(QualificationReconciliationStoreError,
                                    "observation_bundle_reference_mismatch|bundle_source_snapshot_binding_mismatch"):
            self.store.record(reconciliation, qualification, altered)
        self.assertEqual(self.store.history(), ())

    def test_invalidation_is_append_only_and_preserves_historical_record(self):
        reconciliation, qualification, bundle = artifacts()
        self.store.record(reconciliation, qualification, bundle)
        record_id = reconciliation["reconciliation_sha256"]
        context = self.store.get(record_id)["context"]
        unchanged = self.store.invalidate(record_id, context)
        self.assertFalse(unchanged["invalidated"])
        current = dict(context)
        current["source_snapshot_id"] = "snapshot:new"
        current["plan_sha256"] = "f" * 64
        first = self.store.invalidate(record_id, current)
        second = self.store.invalidate(record_id, current)
        self.assertTrue(first["invalidated"])
        self.assertTrue(first["event_appended"])
        self.assertFalse(second["event_appended"])
        self.assertEqual(first["reason_codes"], [
            "SOURCE_SNAPSHOT_CHANGED", "RULE_PLAN_CHANGED"])
        self.assertEqual(len(self.store.invalidation_history(record_id)), 1)
        self.assertEqual(self.store.get(record_id)["reconciliation"], reconciliation)
        self.assertTrue(self.store.verify_integrity())

    def test_distinct_invalidation_contexts_are_retained_not_overwritten(self):
        reconciliation, qualification, bundle = artifacts()
        self.store.record(reconciliation, qualification, bundle)
        record_id = reconciliation["reconciliation_sha256"]
        context = self.store.get(record_id)["context"]
        changed_source = dict(context, source_snapshot_id="snapshot:two")
        changed_policy = dict(context, aggregation_policy_registry_sha256="9" * 64)
        self.store.invalidate(record_id, changed_source)
        self.store.invalidate(record_id, changed_policy)
        history = self.store.invalidation_history(record_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["reason_codes"], ["SOURCE_SNAPSHOT_CHANGED"])
        self.assertEqual(history[1]["reason_codes"], ["AGGREGATION_POLICY_CHANGED"])

    def test_sqlite_triggers_reject_update_and_delete(self):
        reconciliation, qualification, bundle = artifacts()
        self.store.record(reconciliation, qualification, bundle)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._db.execute(
                "UPDATE qualification_reconciliation_events SET payload='{}'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._db.execute("DELETE FROM qualification_reconciliation_events")

    def test_recomputed_database_tampering_is_detected_by_chain_verifier(self):
        reconciliation, qualification, bundle = artifacts()
        self.store.record(reconciliation, qualification, bundle)
        self.store._db.execute("DROP TRIGGER qualification_reconciliation_no_update")
        self.store._db.execute(
            "UPDATE qualification_reconciliation_events SET payload='{}' WHERE sequence=1")
        self.assertFalse(self.store.verify_integrity())

    def test_storage_bound_refuses_new_events_without_evicting_history(self):
        self.store.close()
        self.store = QualificationReconciliationStore(self.db, max_records=1)
        reconciliation, qualification, bundle = artifacts()
        self.store.record(reconciliation, qualification, bundle)
        context = self.store.get(reconciliation["reconciliation_sha256"])["context"]
        with self.assertRaisesRegex(QualificationReconciliationStoreError,
                                    "ledger_storage_limit_reached"):
            self.store.invalidate(
                reconciliation["reconciliation_sha256"],
                dict(context, source_snapshot_id="snapshot:changed"))
        self.assertEqual(len(self.store.history()), 1)

    def test_verified_persistence_and_historical_replay_use_m7517_verifier(self):
        fixture = QualificationReconciliationTests()
        fixture.setUp()
        try:
            bundle, qualification = fixture.qualification(
                [fixture.syntax_observation("src/broken_a.py")])
            reconciliation = fixture.reconcile(bundle, qualification)
            result = persist_verified_qualification_reconciliation(
                self.store, reconciliation, qualification, bundle,
                claim=fixture.claim, plan=fixture.plan,
                coverage_manifest=fixture.coverage_manifest,
                source_manifest=fixture.source_manifest,
                repository_root=fixture.root)
            self.assertTrue(result["semantic_replay"])
            self.assertTrue(result["persisted"])
            replay = verify_persisted_qualification_reconciliation(
                result["record_id"], store=self.store, claim=fixture.claim,
                plan=fixture.plan, coverage_manifest=fixture.coverage_manifest,
                source_manifest=fixture.source_manifest,
                repository_root=fixture.root)
            self.assertTrue(replay["historical_replay"])
            self.assertTrue(replay["semantic_replay"])
            self.assertFalse(self.store.record(reconciliation, qualification, bundle))
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()

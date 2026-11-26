"""Structural, lifecycle, durability and failure tests for M7.5.2."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    AssertionPolarity, EvidenceAssertion, EvidenceRef, GapKind, GapState, KnowledgeGap,
)
from audit_engine.semantic_audit.epistemic.store import (
    DuplicateRecordError, EpistemicStore, InvalidTransitionError,
    RevisionConflictError, StorageLimitError,
)


def evidence(identifier):
    return EvidenceRef(
        evidence_id=identifier, source_snapshot_id="git:snapshot-1",
        producer_id="test-producer", method_id="test-method",
        observed_at="2026-11-27T00:00:00Z",
    )


def assertion(identifier, polarity):
    return EvidenceAssertion(
        assertion_id=identifier, proposition_id="prop-1", polarity=polarity,
        evidence_refs=(evidence("ev-" + identifier),), scope_id="scope-1",
        method_id="test-method", observed_at="2026-11-27T00:00:00Z",
    )


def gap(state=GapState.OPEN, *, resolution=()):
    return KnowledgeGap(
        gap_id="gap-1", subject_id="source:vendor-x", kind=GapKind.SOURCE_UNAVAILABLE,
        state=state, scope_id="scope-1", discovery_method="inventory:v1",
        impact="source content not available", resolution_evidence_refs=resolution,
        disposition=("accepted by reviewer" if state is GapState.ACCEPTED_RESIDUAL else None),
        authorized_by=("reviewer:1" if state is GapState.ACCEPTED_RESIDUAL else None),
    )


class EpistemicStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "epistemic.sqlite"
        self.store = EpistemicStore(self.db)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_opposing_assertions_are_both_persisted(self):
        self.assertTrue(self.store.record_assertion(assertion("a-support", AssertionPolarity.SUPPORTS)))
        self.assertTrue(self.store.record_assertion(assertion("a-challenge", AssertionPolarity.CHALLENGES)))
        self.assertEqual(self.store.event_count(), 2)
        self.assertEqual(len(self.store.assertion_history("a-support")), 1)
        self.assertEqual(len(self.store.assertion_history("a-challenge")), 1)

    def test_identical_duplicate_is_idempotent_but_conflicting_duplicate_rejected(self):
        item = assertion("a-1", AssertionPolarity.SUPPORTS)
        self.assertTrue(self.store.record_assertion(item))
        self.assertFalse(self.store.record_assertion(item))
        conflicting = assertion("a-1", AssertionPolarity.CHALLENGES)
        with self.assertRaises(DuplicateRecordError):
            self.store.record_assertion(conflicting)
        self.assertEqual(self.store.event_count(), 1)

    def test_gap_lifecycle_appends_revisions_without_replacing_history(self):
        self.store.record_gap(gap())
        revision = self.store.transition_gap(
            gap(GapState.INVESTIGATING), expected_revision=1
        )
        self.assertEqual(revision, 2)
        revision = self.store.transition_gap(
            gap(GapState.RESOLVED, resolution=(evidence("resolution-1"),)),
            expected_revision=2,
        )
        self.assertEqual(revision, 3)
        history = self.store.gap_history("gap-1")
        self.assertEqual([item["revision"] for item in history], [1, 2, 3])
        self.assertEqual(history[0]["payload"]["state"], "open")
        self.assertEqual(history[-1]["payload"]["state"], "resolved")

    def test_stale_revision_and_terminal_reopening_are_rejected(self):
        self.store.record_gap(gap())
        self.store.transition_gap(gap(GapState.INVESTIGATING), expected_revision=1)
        with self.assertRaises(RevisionConflictError):
            self.store.transition_gap(gap(GapState.BLOCKED), expected_revision=1)
        self.store.transition_gap(
            gap(GapState.RESOLVED, resolution=(evidence("resolution-1"),)),
            expected_revision=2,
        )
        with self.assertRaises(InvalidTransitionError):
            self.store.transition_gap(gap(GapState.OPEN), expected_revision=3)

    def test_database_triggers_prevent_update_and_delete(self):
        self.store.record_assertion(assertion("a-1", AssertionPolarity.SUPPORTS))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._connection.execute(
                "UPDATE epistemic_events SET payload = '{}' WHERE event_id = 'assertion:a-1:1'"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._connection.execute(
                "DELETE FROM epistemic_events WHERE event_id = 'assertion:a-1:1'"
            )
        self.assertEqual(self.store.event_count(), 1)

    def test_hard_storage_limit_never_evicts_existing_events(self):
        self.store.close()
        self.store = EpistemicStore(self.db, max_events=1)
        self.store.record_assertion(assertion("a-1", AssertionPolarity.SUPPORTS))
        with self.assertRaises(StorageLimitError):
            self.store.record_assertion(assertion("a-2", AssertionPolarity.CHALLENGES))
        self.assertEqual(self.store.event_count(), 1)
        self.assertEqual(len(self.store.assertion_history("a-1")), 1)

    def test_reopen_preserves_history_and_hash_chain(self):
        self.store.record_assertion(assertion("a-1", AssertionPolarity.SUPPORTS))
        self.store.record_gap(gap())
        self.store.close()
        self.store = EpistemicStore(self.db)
        self.assertEqual(self.store.event_count(), 2)
        self.assertTrue(self.store.verify_integrity())

    def test_event_chain_detects_out_of_band_tampering(self):
        self.store.record_assertion(assertion("a-1", AssertionPolarity.SUPPORTS))
        self.store.close()
        raw = sqlite3.connect(self.db)
        raw.execute("DROP TRIGGER epistemic_events_no_update")
        raw.execute("UPDATE epistemic_events SET payload = '{}' WHERE event_id = 'assertion:a-1:1'")
        raw.commit()
        raw.close()
        self.store = EpistemicStore(self.db)
        self.assertFalse(self.store.verify_integrity())


if __name__ == "__main__":
    unittest.main()

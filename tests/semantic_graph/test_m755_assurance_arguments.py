import tempfile
import unittest
from pathlib import Path
from audit_engine.semantic_audit.epistemic.assurance import (
    AssuranceClaim, ArgumentLink, ArgumentRelation, Defeater, DefeaterKind,
    DefeaterAction, DefeaterEvent, ArgumentAssessment, evaluate_assurance,
    AssuranceContractError,
)
from audit_engine.semantic_audit.epistemic.assurance_store import (
    AssuranceStore, AssuranceDuplicateError, AssuranceStorageLimitError,
)
from audit_engine.semantic_audit.epistemic.contracts import FreshnessStatus

class AssuranceTests(unittest.TestCase):
    def setUp(self):
        self.claim = AssuranceClaim("c1", "p1", "repo", "scope", "snap", "The declared proposition")
        self.link = ArgumentLink("l1", "c1", ArgumentRelation.SUPPORTS, ("premise:1",), "warrant:1", ("e1",), ("snapshot:s1",))
        self.defeater = Defeater("d1", "c1", DefeaterKind.UNDERCUTTING, "l1", "enumerator may omit generated files", ("e2",))
        self.kw = dict(available_evidence_ids=frozenset({"e1", "e2", "e3"}), freshness={"snapshot:s1": FreshnessStatus.FRESH})
    def assess(self, defeaters=(), events=(), links=None, **kw):
        return evaluate_assurance(self.claim, (self.link,) if links is None else links, defeaters, events, **(kw or self.kw))
    def test_support_is_not_truth_and_open_undercutter_blocks_clean_assessment(self):
        self.assertEqual(self.assess(), ArgumentAssessment.SUPPORTS_WITHOUT_OPEN_DEFEATERS)
        self.assertEqual(self.assess((self.defeater,)), ArgumentAssessment.SUPPORTS_WITH_OPEN_DEFEATERS)
    def test_resolve_requires_evidence_and_recorded_resolution_closes_defeater(self):
        with self.assertRaises(AssuranceContractError):
            DefeaterEvent("ev0", "d1", DefeaterAction.RESOLVE, "answered")
        event = DefeaterEvent("ev1", "d1", DefeaterAction.RESOLVE, "independent inventory verified", ("e3",))
        self.assertEqual(self.assess((self.defeater,), (event,)), ArgumentAssessment.SUPPORTS_WITHOUT_OPEN_DEFEATERS)
    def test_accepted_residual_is_not_resolution(self):
        event = DefeaterEvent("ev1", "d1", DefeaterAction.ACCEPT_RESIDUAL, "risk accepted", (), "reviewer:1")
        self.assertEqual(self.assess((self.defeater,), (event,)), ArgumentAssessment.SUPPORTS_WITH_OPEN_DEFEATERS)
    def test_stale_or_missing_evidence_makes_assessment_incomplete(self):
        self.assertEqual(self.assess(links=(self.link,), available_evidence_ids=frozenset({"e1"}), freshness={"snapshot:s1": FreshnessStatus.INVALIDATED}), ArgumentAssessment.INCOMPLETE)
    def test_challenge_link_makes_assessment_contested(self):
        challenge = ArgumentLink("l2", "c1", ArgumentRelation.CHALLENGES, ("p2",), "w2", ("e2",), ("snapshot:s1",))
        self.assertEqual(self.assess(links=(self.link, challenge)), ArgumentAssessment.CONTESTED)
    def test_undercutter_must_target_existing_link(self):
        bad = Defeater("d2", "c1", DefeaterKind.UNDERCUTTING, "missing", "bad warrant", ("e2",))
        with self.assertRaises(AssuranceContractError): self.assess((bad,))
    def test_store_is_append_only_idempotent_and_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            with AssuranceStore(Path(td)/"a.sqlite", max_events=2) as store:
                self.assertTrue(store.record(self.claim)); self.assertFalse(store.record(self.claim))
                self.assertTrue(store.record(self.link))
                with self.assertRaises(AssuranceStorageLimitError): store.record(self.defeater)
                self.assertTrue(store.verify_integrity())
                changed = AssuranceClaim("c1", "p1", "repo", "scope", "snap", "changed statement")
                with self.assertRaises(AssuranceDuplicateError): store.record(changed)
    def test_store_detects_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            with AssuranceStore(Path(td)/"a.sqlite") as store:
                store.record(self.claim)
                store._db.execute("DROP TRIGGER assurance_no_update")
                store._db.execute("UPDATE assurance_events SET payload='{}' WHERE record_id='c1'")
                store._db.commit()
                self.assertFalse(store.verify_integrity())
                with self.assertRaises(Exception): store.record(self.link)

if __name__ == "__main__": unittest.main()

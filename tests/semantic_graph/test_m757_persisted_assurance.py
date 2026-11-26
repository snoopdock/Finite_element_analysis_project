import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    AssuranceClaim,
    ArgumentAssessment,
    ArgumentLink,
    ArgumentRelation,
    AssertionPolarity,
    Defeater,
    DefeaterAction,
    DefeaterEvent,
    DefeaterKind,
    EpistemicStore,
    EvidenceAssertion,
    EvidenceRef,
    FreshnessStatus,
    ProvenanceManifest,
    AssuranceStore,
    evaluate_persisted_assurance,
)


class PersistedAssuranceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.epistemic = EpistemicStore(root / "epistemic.sqlite")
        self.assurance = AssuranceStore(root / "assurance.sqlite")
        self.claim = AssuranceClaim(
            "claim:1", "proposition:1", "repo", "scope:repo",
            "snap-1", "The source snapshot contains the declared object",
        )
        self.ref = EvidenceRef(
            "e1", "snap-1", "scanner",
            "inventory", "2026-11-27T10:00:00Z",
            "a" * 64,
        )
        self.assertion = EvidenceAssertion(
            "assertion:1", "proposition:1", AssertionPolarity.SUPPORTS,
            (self.ref,), "scope:repo", "method:inventory",
            "2026-11-27T10:00:01Z",
        )
        self.link = ArgumentLink(
            "link:1", "claim:1", ArgumentRelation.SUPPORTS,
            ("premise:1",), "warrant:1", ("e1",),
            ("evidence:e1",),
        )

    def tearDown(self):
        self.assurance.close()
        self.epistemic.close()
        self.temp.cleanup()

    def declare_terminal(self, node_id):
        self.epistemic.record_dependency_manifest(ProvenanceManifest(
            f"manifest:{node_id}", node_id, (), "m7.5.7/terminal-v1"
        ))

    def persist_valid_evidence(self):
        self.epistemic.record_assertion(self.assertion)
        self.epistemic.record_assertion_dependencies(self.assertion)
        for node in (
            "snapshot:snap-1", "producer:scanner", "method:inventory",
            f"artifact-sha256:{'a' * 64}",
        ):
            self.declare_terminal(node)

    def persist_claim_and_link(self):
        self.assurance.record(self.claim)
        self.assurance.record(self.link)

    def test_store_backed_evaluation_uses_persisted_evidence_and_closure(self):
        self.persist_valid_evidence()
        self.persist_claim_and_link()
        result = evaluate_persisted_assurance(
            "claim:1", self.assurance, self.epistemic
        )
        self.assertIs(result.assessment, ArgumentAssessment.SUPPORTS_WITHOUT_OPEN_DEFEATERS, repr(result))
        self.assertTrue(result.ledger_consistent)
        self.assertEqual(result.missing_evidence_ids, ())
        self.assertTrue(result.freshness_results)
        self.assertTrue(all(x.status is FreshnessStatus.FRESH for x in result.freshness_results))

    def test_unpersisted_evidence_id_is_incomplete(self):
        self.persist_claim_and_link()
        result = evaluate_persisted_assurance(
            "claim:1", self.assurance, self.epistemic
        )
        self.assertIs(result.assessment, ArgumentAssessment.INCOMPLETE)
        self.assertEqual(result.missing_evidence_ids, ("e1",))
        self.assertTrue(result.ledger_consistent)

    def test_evidence_without_closed_terminal_provenance_is_incomplete(self):
        self.epistemic.record_assertion(self.assertion)
        self.epistemic.record_assertion_dependencies(self.assertion)
        self.persist_claim_and_link()
        result = evaluate_persisted_assurance(
            "claim:1", self.assurance, self.epistemic
        )
        self.assertIs(result.assessment, ArgumentAssessment.INCOMPLETE)
        self.assertTrue(any(x.status is FreshnessStatus.UNKNOWN for x in result.freshness_results))

    def test_transitive_invalidation_blocks_assurance_assessment(self):
        self.persist_valid_evidence()
        self.persist_claim_and_link()
        self.epistemic.invalidate_dependency(
            "producer:scanner",
            root_change_id="producer-change:1",
            reason="scanner deployment changed",
            observed_at="2026-11-27T11:00:00Z",
        )
        result = evaluate_persisted_assurance(
            "claim:1", self.assurance, self.epistemic
        )
        self.assertIs(result.assessment, ArgumentAssessment.INCOMPLETE)
        self.assertTrue(any(x.status is FreshnessStatus.INVALIDATED for x in result.freshness_results), repr(result))

    def test_evidence_metadata_must_match_claim_snapshot(self):
        wrong_ref = EvidenceRef(
            "e1", "other-snapshot", "scanner",
            "inventory", "2026-11-27T10:00:00Z",
        )
        wrong_assertion = EvidenceAssertion(
            "assertion:wrong", "proposition:1", AssertionPolarity.SUPPORTS,
            (wrong_ref,), "scope:repo", "method:inventory",
            "2026-11-27T10:00:01Z",
        )
        self.epistemic.record_assertion(wrong_assertion)
        self.persist_claim_and_link()
        result = evaluate_persisted_assurance(
            "claim:1", self.assurance, self.epistemic
        )
        self.assertIs(result.assessment, ArgumentAssessment.INCOMPLETE)
        self.assertTrue(any("different source snapshot" in x for x in result.reasons))

    def test_conflicting_persisted_evidence_metadata_is_incomplete(self):
        self.epistemic.record_assertion(self.assertion)
        conflict_ref = EvidenceRef(
            "e1", "snap-1", "other-producer",
            "inventory", "2026-11-27T10:00:00Z",
        )
        conflict = EvidenceAssertion(
            "assertion:conflict", "proposition:1", AssertionPolarity.SUPPORTS,
            (conflict_ref,), "scope:repo", "method:inventory",
            "2026-11-27T10:00:02Z",
        )
        self.epistemic.record_assertion(conflict)
        self.persist_claim_and_link()
        result = evaluate_persisted_assurance(
            "claim:1", self.assurance, self.epistemic
        )
        self.assertIs(result.assessment, ArgumentAssessment.INCOMPLETE)
        self.assertTrue(any("conflicting" in x for x in result.reasons))

    def test_defeater_resolution_evidence_must_also_be_persisted_and_fresh(self):
        self.persist_valid_evidence()
        second_ref = EvidenceRef(
            "e-response", "snap-1", "reviewer",
            "independent-review", "2026-11-27T12:00:00Z",
        )
        second_assertion = EvidenceAssertion(
            "assertion:response", "proposition:1", AssertionPolarity.SUPPORTS,
            (second_ref,), "scope:repo", "method:independent-review",
            "2026-11-27T12:00:01Z",
        )
        self.epistemic.record_assertion(second_assertion)
        self.epistemic.record_assertion_dependencies(second_assertion)
        for node in ("producer:reviewer", "method:independent-review"):
            self.declare_terminal(node)
        defeater = Defeater(
            "defeater:1", "claim:1", DefeaterKind.REBUTTING, None,
            "The scanner may omit generated files", ("e1",),
        )
        event = DefeaterEvent(
            "event:resolve", "defeater:1", DefeaterAction.RESOLVE,
            "Independent review answered the objection",
            ("e-response",),
        )
        self.assurance.record(defeater)
        self.assurance.record(event)
        self.persist_claim_and_link()
        result = evaluate_persisted_assurance(
            "claim:1", self.assurance, self.epistemic
        )
        self.assertIs(result.assessment, ArgumentAssessment.SUPPORTS_WITHOUT_OPEN_DEFEATERS)

    def test_cross_ledger_change_during_evaluation_fails_closed(self):
        self.persist_valid_evidence()
        self.persist_claim_and_link()
        original = self.epistemic.snapshot_token
        calls = {"count": 0}

        def changing_snapshot_token():
            calls["count"] += 1
            if calls["count"] == 2:
                extra = EvidenceAssertion(
                    "assertion:concurrent", "other-proposition",
                    AssertionPolarity.NEUTRAL,
                    (EvidenceRef(
                        "evidence:concurrent", "snap-1", "scanner",
                        "method:inventory", "2026-11-27T13:00:00Z",
                    ),),
                    "scope:repo", "method:inventory", "2026-11-27T13:00:01Z",
                )
                self.epistemic.record_assertion(extra)
            return original()

        self.epistemic.snapshot_token = changing_snapshot_token
        result = evaluate_persisted_assurance(
            "claim:1", self.assurance, self.epistemic
        )
        self.assertIs(result.assessment, ArgumentAssessment.INCOMPLETE)
        self.assertFalse(result.ledger_consistent)
        self.assertTrue(any("changed during" in x for x in result.reasons))

    def test_missing_claim_is_incomplete(self):
        result = evaluate_persisted_assurance(
            "claim:absent", self.assurance, self.epistemic
        )
        self.assertIs(result.assessment, ArgumentAssessment.INCOMPLETE)
        self.assertIsNone(result.claim)


if __name__ == "__main__":
    unittest.main()

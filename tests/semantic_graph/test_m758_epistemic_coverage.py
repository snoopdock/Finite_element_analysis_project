"""M7.5.8 epistemic coverage and unknown-state assurance tests."""
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    AssuranceClaim, AssuranceStore, ArgumentAssessment, ArgumentLink,
    ArgumentRelation, AssertionPolarity, CoverageObligation,
    EpistemicCoverageManifest, EpistemicCoverageStatus, EpistemicStore,
    EvidenceAssertion, EvidenceRef, ObligationDisposition, ProvenanceManifest,
    evaluate_epistemic_coverage,
)


class EpistemicCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.epistemic = EpistemicStore(root / "epistemic.sqlite")
        self.assurance = AssuranceStore(root / "assurance.sqlite")
        self.claim = AssuranceClaim(
            "claim:coverage", "prop:coverage", "repo", "scope:repo",
            "snapshot:1", "Coverage test claim",
        )
        self.assurance.record(self.claim)
        self.ref = EvidenceRef(
            "evidence:1", "snapshot:1", "enumerator:v1",
            "inventory:v1", "2026-11-27T10:00:00Z", "a" * 64,
        )
        self.assertion = EvidenceAssertion(
            "assertion:1", "prop:coverage", AssertionPolarity.SUPPORTS,
            (self.ref,), "scope:repo", "inventory:v1",
            "2026-11-27T10:00:01Z",
        )
        self.epistemic.record_assertion(self.assertion)
        self.epistemic.record_assertion_dependencies(self.assertion)
        for node in (
            "snapshot:snapshot:1", "producer:enumerator:v1",
            "method:inventory:v1", f"artifact-sha256:{'a' * 64}",
        ):
            self.epistemic.record_dependency_manifest(ProvenanceManifest(
                f"manifest:{node}", node, (), "test-terminal-v1"
            ))

    def tearDown(self):
        self.assurance.close()
        self.epistemic.close()
        self.temp.cleanup()

    def manifest(self, obligations=None, expected=("inventory", "parser")):
        if obligations is None:
            obligations = (
                CoverageObligation("inventory", ObligationDisposition.EVIDENCE_BOUND, ("evidence:1",)),
                CoverageObligation("parser", ObligationDisposition.EVIDENCE_BOUND, ("evidence:1",)),
            )
        return EpistemicCoverageManifest(
            "coverage:1", "claim:coverage", "prop:coverage", "repo",
            "scope:repo", "snapshot:1", "coverage-registry", "v1",
            "b" * 64, expected, obligations,
        )

    def evaluate(self, manifest):
        return evaluate_epistemic_coverage(
            "claim:coverage", manifest, self.assurance, self.epistemic
        )

    def test_all_declared_obligations_require_persisted_fresh_evidence(self):
        result = self.evaluate(self.manifest())
        self.assertIs(result.status, EpistemicCoverageStatus.EVIDENCE_COMPLETE_WITHIN_DECLARED_MANIFEST)
        self.assertTrue(result.ledger_consistent)
        self.assertEqual(dict(result.freshness_results)["evidence:1"], "fresh")

    def test_omitted_expected_obligation_is_unknown_not_complete(self):
        result = self.evaluate(self.manifest(obligations=(
            CoverageObligation("inventory", ObligationDisposition.EVIDENCE_BOUND, ("evidence:1",)),
        )))
        self.assertIs(result.status, EpistemicCoverageStatus.UNKNOWN)
        self.assertEqual(result.missing_obligation_ids, ("parser",))

    def test_unknown_and_not_assessed_are_not_negative_or_complete(self):
        result = self.evaluate(self.manifest(obligations=(
            CoverageObligation("inventory", ObligationDisposition.EVIDENCE_BOUND, ("evidence:1",)),
            CoverageObligation("parser", ObligationDisposition.UNKNOWN),
        )))
        self.assertIs(result.status, EpistemicCoverageStatus.UNKNOWN)

    def test_unsupported_or_excluded_obligation_is_incomplete(self):
        result = self.evaluate(self.manifest(obligations=(
            CoverageObligation("inventory", ObligationDisposition.EVIDENCE_BOUND, ("evidence:1",)),
            CoverageObligation("parser", ObligationDisposition.UNSUPPORTED),
        )))
        self.assertIs(result.status, EpistemicCoverageStatus.INCOMPLETE)

    def test_challenging_assertion_marks_obligation_contested(self):
        challenge = EvidenceAssertion(
            "assertion:challenge", "prop:coverage", AssertionPolarity.CHALLENGES,
            (self.ref,), "scope:repo", "review:v1", "2026-11-27T10:02:00Z",
        )
        self.epistemic.record_assertion(challenge)
        result = self.evaluate(self.manifest())
        self.assertIs(result.status, EpistemicCoverageStatus.CONTESTED)
        self.assertEqual(result.contested_obligation_ids, ("inventory", "parser"))

    def test_missing_persisted_evidence_is_unknown(self):
        result = self.evaluate(self.manifest(obligations=(
            CoverageObligation("inventory", ObligationDisposition.EVIDENCE_BOUND, ("missing",)),
            CoverageObligation("parser", ObligationDisposition.EVIDENCE_BOUND, ("evidence:1",)),
        )))
        self.assertIs(result.status, EpistemicCoverageStatus.UNKNOWN)

    def test_stale_provenance_invalidates_coverage(self):
        self.epistemic.invalidate_dependency(
            "producer:enumerator:v1", root_change_id="change:1",
            reason="enumerator changed", observed_at="2026-11-27T11:00:00Z",
        )
        result = self.evaluate(self.manifest())
        self.assertIs(result.status, EpistemicCoverageStatus.INVALIDATED)

    def test_claim_scope_mismatch_fails_closed(self):
        bad = EpistemicCoverageManifest(
            "coverage:bad", "claim:coverage", "prop:coverage", "repo",
            "other-scope", "snapshot:1", "coverage-registry", "v1",
            "b" * 64, ("inventory",), (
                CoverageObligation("inventory", ObligationDisposition.EVIDENCE_BOUND, ("evidence:1",)),
            ),
        )
        result = self.evaluate(bad)
        self.assertIs(result.status, EpistemicCoverageStatus.INCOMPLETE)

    def test_unresolved_gap_prevents_coverage_closure(self):
        from audit_engine.semantic_audit.epistemic import GapKind, GapState, KnowledgeGap
        gap = KnowledgeGap(
            "gap:1", "repo", GapKind.PARTIAL_EXTRACTION, GapState.OPEN,
            "scope:repo", "parser-inspection:v1", "parser coverage uncertain",
        )
        self.epistemic.record_gap(gap)
        manifest = self.manifest(obligations=(
            CoverageObligation("inventory", ObligationDisposition.EVIDENCE_BOUND,
                               ("evidence:1",), ("gap:1",)),
            CoverageObligation("parser", ObligationDisposition.EVIDENCE_BOUND, ("evidence:1",)),
        ))
        result = self.evaluate(manifest)
        self.assertIs(result.status, EpistemicCoverageStatus.INCOMPLETE)

    def test_registry_and_manifest_are_explicitly_bound_in_digest(self):
        first = self.manifest()
        second = EpistemicCoverageManifest(
            "coverage:2", "claim:coverage", "prop:coverage", "repo",
            "scope:repo", "snapshot:1", "other-registry", "v2",
            "c" * 64, first.expected_obligation_ids, first.obligations,
        )
        self.assertNotEqual(first.manifest_sha256, second.manifest_sha256)


if __Name__ == "__main__":
    unittest.main()

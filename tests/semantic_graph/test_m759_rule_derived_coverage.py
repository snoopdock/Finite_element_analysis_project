"""M7.5.9 rule-derived trusted coverage registry tests."""
import unittest

from audit_engine.semantic_audit.epistemic import (
    AssuranceClaim, CoverageObligation, ObligationDisposition,
    build_rule_derived_coverage_manifest, derive_rule_coverage_plan,
    verify_rule_derived_manifest, RuleCoverageDerivationError,
)
from audit_engine.semantic_audit.ae32c.rule_contracts import rule_registry


class RuleDerivedCoverageTests(unittest.TestCase):
    def setUp(self):
        self.claim = AssuranceClaim(
            "claim:rules", "prop:rules", "repository", "scope:repo",
            "snapshot:source-1", "Rule coverage assurance",
        )

    def plan(self, rule_ids=("AE32A-AE28-EXTERNAL-MODEL-INPUT",)):
        return derive_rule_coverage_plan(
            self.claim, source_snapshot_id="snapshot:source-1",
            graph_snapshot_id="graph:1", rule_ids=rule_ids,
        )

    def test_rule_requirements_are_derived_not_caller_declared(self):
        plan = self.plan()
        self.assertEqual(set(plan.expected_obligation_ids), {
            "rule:AE32A-AE28-EXTERNAL-MODEL-INPUT:evidence:external_model_response_intake",
            "rule:AE32A-AE28-EXTERNAL-MODEL-INPUT:coverage:python_ast",
            "rule:AE32A-AE28-EXTERNAL-MODEL-INPUT:coverage:source_manifest",
        })
        self.assertEqual(plan.registry_sha256, rule_registry()["registry_sha256"])

    def test_absence_and_mixed_rules_are_explicitly_not_closed_world(self):
        plan = self.plan(("AE32A-NO-TOOL-LOOP", "AE32A-FIXED-DIAGNOSTIC-CONTEXT"))
        self.assertEqual(dict(plan.claim_polarities)["AE32A-NO-TOOL-LOOP"], "absence")
        self.assertEqual(dict(plan.claim_polarities)["AE32A-FIXED-DIAGNOSTIC-CONTEXT"], "mixed")
        self.assertEqual(plan.closed_world_rule_ids, ())

    def test_omitted_derived_obligation_stays_unknown_in_manifest(self):
        plan = self.plan()
        first = plan.expected_obligation_ids[0]
        manifest = build_rule_derived_coverage_manifest(
            self.claim, plan,
            assessments={first: CoverageObligation(first, ObligationDisposition.UNKNOWN)},
        )
        self.assertEqual(manifest.expected_obligation_ids, plan.expected_obligation_ids)
        self.assertEqual(tuple(x.obligation_id for x in manifest.obligations), (first,))

    def test_caller_cannot_shrink_expected_universe(self):
        plan = self.plan()
        manifest = build_rule_derived_coverage_manifest(self.claim, plan)
        shrunk = type(manifest)(
            manifest.manifest_id, manifest.claim_id, manifest.proposition_id,
            manifest.subject_id, manifest.scope_id, manifest.source_snapshot_id,
            manifest.registry_id, manifest.registry_version, manifest.registry_sha256,
            manifest.expected_obligation_ids[:-1], manifest.obligations,
        )
        with self.assertRaisesRegex(RuleCoverageDerivationError, "derived_obligation_universe"):
            verify_rule_derived_manifest(self.claim, plan, shrunk)

    def test_assessment_cannot_add_unknown_rule_obligation(self):
        plan = self.plan()
        with self.assertRaisesRegex(RuleCoverageDerivationError, "outside_derived_rule_universe"):
            build_rule_derived_coverage_manifest(
                self.claim, plan,
                assessments={"invented": CoverageObligation("invented", ObligationDisposition.UNKNOWN)},
            )

    def test_unknown_or_ambiguous_rule_fails_closed(self):
        with self.assertRaisesRegex(RuleCoverageDerivationError, "unknown_or_ambiguous_rule"):
            self.plan(("UNREGISTERED-RULE",))

    def test_duplicate_rule_ids_rejected(self):
        with self.assertRaisesRegex(RuleCoverageDerivationError, "must_not_contain_duplicates"):
            self.plan(("AE32A-AE28-EXTERNAL-MODEL-INPUT", "AE32A-AE28-EXTERNAL-MODEL-INPUT"))

    def test_claim_and_snapshot_binding_is_enforced(self):
        plan = self.plan()
        other_claim = AssuranceClaim(
            "claim:other", "prop:rules", "repository", "scope:repo",
            "snapshot:source-2", "Other claim",
        )
        with self.assertRaisesRegex(RuleCoverageDerivationError, "plan_claim_or_source_snapshot_mismatch"):
            build_rule_derived_coverage_manifest(other_claim, plan)

    def test_manifest_registry_digest_is_pinned_to_plan(self):
        plan = self.plan()
        manifest = build_rule_derived_coverage_manifest(self.claim, plan)
        altered = type(manifest)(
            manifest.manifest_id, manifest.claim_id, manifest.proposition_id,
            manifest.subject_id, manifest.scope_id, manifest.source_snapshot_id,
            manifest.registry_id, manifest.registry_version, "f" * 64,
            manifest.expected_obligation_ids, manifest.obligations,
        )
        with self.assertRaisesRegex(RuleCoverageDerivationError, "registry_digest"):
            verify_rule_derived_manifest(self.claim, plan, altered)


if __name__ == "__main__":
    unittest.main()

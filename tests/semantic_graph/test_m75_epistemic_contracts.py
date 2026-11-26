"""Structural and behavioral tests for M7.5.1 epistemic contracts."""

import unittest

from audit_engine.semantic_audit.epistemic import (
    AssertionPolarity,
    CompletenessClaim,
    CompletenessStatus,
    EvidenceAssertion,
    EvidenceRef,
    GapKind,
    GapState,
    KnowledgeGap,
)
from audit_engine.semantic_audit.epistemic.contracts import ContractError


def evidence(evidence_id="ev-1"):
    return EvidenceRef(
        evidence_id=evidence_id,
        source_snapshot_id="git:abc",
        producer_id="git-object-reader:v2",
        method_id="sha256-stream:v1",
        observed_at="2026-11-26T10:00:00Z",
        artifact_sha256="a" * 64,
    )


class EvidenceAssertionTests(unittest.TestCase):
    def test_assertion_requires_evidence_and_preserves_polarity(self):
        support = EvidenceAssertion(
            "as-1", "prop-1", AssertionPolarity.SUPPORTS, (evidence("ev-support"),),
            "scope-repo-tree", "extractor:v1", "2026-11-26T10:00:00Z",
        )
        challenge = EvidenceAssertion(
            "as-2", "prop-1", AssertionPolarity.CHALLENGES, (evidence("ev-challenge"),),
            "scope-repo-tree", "independent-check:v1", "2026-11-26T10:01:00Z",
        )
        self.assertEqual(support.proposition_id, challenge.proposition_id)
        self.assertNotEqual(support.polarity, challenge.polarity)
        self.assertEqual(support.assertion_id, "as-1")
        self.assertEqual(challenge.assertion_id, "as-2")

    def test_assertion_without_evidence_is_rejected(self):
        with self.assertRaises(ContractError):
            EvidenceAssertion(
                "as-1", "prop-1", AssertionPolarity.SUPPORTS, (),
                "scope-1", "method-1", "2026-11-26T10:00:00Z",
            )

    def test_invalid_digest_is_rejected(self):
        with self.assertRaises(ContractError):
            EvidenceRef("ev-1", "snap-1", "producer", "method", "now", "not-a-digest")


class KnowledgeGapTests(unittest.TestCase):
    def test_unknown_cause_is_preserved(self):
        gap = KnowledgeGap(
            gap_id="gap-1", subject_id="submodule:vendor/x", kind=GapKind.UNKNOWN_CAUSE,
            state=GapState.OPEN, scope_id="scope-source-tree",
            discovery_method="gitlink-inventory:v1", impact="submodule contents not inspected",
        )
        self.assertEqual(gap.kind, GapKind.UNKNOWN_CAUSE)
        self.assertIsNone(gap.reason_detail)

    def test_resource_limit_is_an_operational_gap_not_a_truth_assertion(self):
        gap = KnowledgeGap(
            gap_id="gap-budget", subject_id="proof:cnf-1", kind=GapKind.RESOURCE_LIMIT,
            state=GapState.BLOCKED, scope_id="scope-proof-check",
            discovery_method="rup-checker:v1", impact="certificate not fully checked",
        )
        self.assertEqual(gap.kind, GapKind.RESOURCE_LIMIT)
        self.assertEqual(gap.state, GapState.BLOCKED)

    def test_resolved_gap_requires_resolution_evidence(self):
        with self.assertRaises(ContractError):
            KnowledgeGap(
                "gap-1", "source:x", GapKind.SOURCE_NOT_SUPPLIED, GapState.RESOLVED,
                "scope-1", "inventory:v1", "required source unavailable",
            )

    def test_accepted_residual_requires_disposition_and_authority(self):
        with self.assertRaises(ContractError):
            KnowledgeGap(
                "gap-1", "source:x", GapKind.SOURCE_UNAVAILABLE, GapState.ACCEPTED_RESIDUAL,
                "scope-1", "inventory:v1", "source cannot be obtained",
            )
        gap = KnowledgeGap(
            "gap-2", "source:y", GapKind.SOURCE_UNAVAILABLE, GapState.ACCEPTED_RESIDUAL,
            "scope-1", "inventory:v1", "external source unavailable",
            disposition="exclude from this audit scope", authorized_by="audit-policy:reviewer",
        )
        self.assertEqual(gap.state, GapState.ACCEPTED_RESIDUAL)


class CompletenessClaimTests(unittest.TestCase):
    def test_supported_claim_requires_exact_scoped_coverage(self):
        claim = CompletenessClaim(
            claim_id="cc-1", subject_id="regular-git-blobs", scope_id="commit:abc",
            source_snapshot_id="git:abc", enumeration_method="git-tree-walk",
            method_version="v2", covered_units=12, expected_units=12,
            status=CompletenessStatus.SUPPORTED_WITHIN_SCOPE,
            evidence_refs=(evidence("inventory-manifest"),),
            verification_method_id="manifest-postflight:v1",
            predicate_id="enumerates:git-blob",
            covered_unit_ids=tuple(f"blob-{i}" for i in range(12)),
            expected_unit_ids=tuple(f"blob-{i}" for i in range(12)),
        )
        self.assertEqual(claim.status, CompletenessStatus.SUPPORTED_WITHIN_SCOPE)

    def test_unknown_denominator_cannot_support_completeness(self):
        with self.assertRaises(ContractError):
            CompletenessClaim(
                "cc-1", "repository-dependencies", "repo-snapshot", "git:abc",
                "dependency-extractor", "v1", 10, None,
                CompletenessStatus.SUPPORTED_WITHIN_SCOPE,
                evidence_refs=(evidence(),), verification_method_id="postflight:v1",
            )

    def test_unsupported_construct_prevents_supported_completeness(self):
        with self.assertRaises(ContractError):
            CompletenessClaim(
                "cc-1", "source-constructs", "scope-1", "git:abc",
                "extractor", "v1", 10, 10, CompletenessStatus.SUPPORTED_WITHIN_SCOPE,
                evidence_refs=(evidence(),), verification_method_id="independent-enumeration:v1",
                unsupported_constructs=("dynamic import",),
            )

    def test_coverage_over_denominator_is_rejected(self):
        with self.assertRaises(ContractError):
            CompletenessClaim(
                "cc-1", "source", "scope-1", "git:abc", "enumerator", "v1",
                11, 10, CompletenessStatus.PARTIAL,
            )



class ContractTypeValidationTests(unittest.TestCase):
    def test_non_string_artifact_digest_is_rejected_cleanly(self):
        with self.assertRaises(ContractError):
            EvidenceRef("ev-1", "snap-1", "producer", "method", "now", 123)

    def test_non_string_verification_method_is_rejected_cleanly(self):
        with self.assertRaises(ContractError):
            CompletenessClaim(
                "cc-1", "source", "scope-1", "git:abc", "enumerator", "v1",
                1, 1, CompletenessStatus.SUPPORTED_WITHIN_SCOPE,
                evidence_refs=(evidence(),), verification_method_id=123,
                predicate_id="enumerates:source-unit",
                covered_unit_ids=("unit-1",), expected_unit_ids=("unit-1",),
            )

    def test_completeness_evidence_references_must_be_unique(self):
        with self.assertRaises(ContractError):
            CompletenessClaim(
                "cc-1", "source", "scope-1", "git:abc", "enumerator", "v1",
                1, 1, CompletenessStatus.SUPPORTED_WITHIN_SCOPE,
                evidence_refs=(evidence("same"), evidence("same")),
                verification_method_id="postflight:v1", predicate_id="enumerates:source-unit",
                covered_unit_ids=("unit-1",), expected_unit_ids=("unit-1",),
            )


if __name__ == "__main__":
    unittest.main()

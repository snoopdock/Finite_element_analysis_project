"""M7.5.3 scope-bound completeness and negative-claim admissibility tests."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    CompletenessClaim, CompletenessStatus, EpistemicStore, EvidenceRef,
    NegativeClaimRequest, evaluate_negative_claim,
)


def evidence(identifier="inventory-1"):
    return EvidenceRef(
        evidence_id=identifier, source_snapshot_id="git:snapshot-42",
        producer_id="tree-enumerator:v2", method_id="git-tree-walk:v2",
        observed_at="2026-11-27T00:00:00Z",
    )


def claim(**overrides):
    values = dict(
        claim_id="cc-1", subject_id="repository:source-units",
        scope_id="scope:stage1-source", source_snapshot_id="git:snapshot-42",
        enumeration_method="git-tree-walk", method_version="v2",
        covered_units=3, expected_units=3,
        status=CompletenessStatus.SUPPORTED_WITHIN_SCOPE,
        evidence_refs=(evidence(),), verification_method_id="independent-manifest-check:v1",
        predicate_id="contains:python-source-unit",
        covered_unit_ids=("src/a.py", "src/b.py", "src/c.py"),
        expected_unit_ids=("src/a.py", "src/b.py", "src/c.py"),
    )
    values.update(overrides)
    return CompletenessClaim(**values)


def request(**overrides):
    values = dict(
        subject_id="repository:source-units",
        predicate_id="contains:python-source-unit",
        scope_id="scope:stage1-source",
        source_snapshot_id="git:snapshot-42",
        closed_world_rule_id="rule:no-unmatched-python-source:v1",
        rule_allows_closed_world=True,
    )
    values.update(overrides)
    return NegativeClaimRequest(**values)


class CompletenessContractTests(unittest.TestCase):
    def test_manifest_must_match_denominator(self):
        with self.assertRaises(ValueError):
            claim(covered_unit_ids=("src/a.py",), covered_units=3)

    def test_duplicate_unit_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            claim(covered_unit_ids=("src/a.py", "src/a.py", "src/c.py"))

    def test_supported_claim_requires_predicate_and_exact_manifest(self):
        with self.assertRaises(ValueError):
            claim(predicate_id=None)
        with self.assertRaises(ValueError):
            claim(expected_unit_ids=("src/a.py", "src/b.py"))

    def test_empty_enumerated_scope_can_be_explicitly_complete(self):
        empty = claim(
            covered_units=0, expected_units=0,
            covered_unit_ids=(), expected_unit_ids=(),
        )
        result = evaluate_negative_claim(empty, request())
        self.assertTrue(result.admissible)


class NegativeClaimAdmissibilityTests(unittest.TestCase):
    def test_exact_scope_snapshot_subject_predicate_and_rule_are_admissible(self):
        result = evaluate_negative_claim(claim(), request())
        self.assertTrue(result.admissible)
        self.assertEqual(result.reasons, ())

    def test_subject_predicate_scope_and_snapshot_mismatch_fail_closed(self):
        cases = (
            request(subject_id="other-subject"),
            request(predicate_id="other-predicate"),
            request(scope_id="other-scope"),
            request(source_snapshot_id="git:other-snapshot"),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                result = evaluate_negative_claim(claim(), candidate)
                self.assertFalse(result.admissible)
                self.assertTrue(result.reasons)

    def test_closed_world_rule_must_be_explicitly_authorized(self):
        result = evaluate_negative_claim(claim(), request(rule_allows_closed_world=False))
        self.assertFalse(result.admissible)
        self.assertIn("applicable rule does not explicitly authorize closed-world inference", result.reasons)

    def test_unknown_or_partial_completeness_cannot_admit_negative_claim(self):
        partial = claim(status=CompletenessStatus.PARTIAL)
        result = evaluate_negative_claim(partial, request())
        self.assertFalse(result.admissible)
        self.assertIn("completeness status is not SUPPORTED_WITHIN_SCOPE", result.reasons)

    def test_exclusions_unsupported_constructs_and_assumptions_block_admissibility(self):
        variants = (
            claim(status=CompletenessStatus.PARTIAL, exclusions=("generated files excluded",)),
            claim(status=CompletenessStatus.PARTIAL, unsupported_constructs=("dynamic source generation",)),
            claim(status=CompletenessStatus.PARTIAL, assumptions=("all plugins are declared",)),
        )
        expected = ("scope contains declared exclusions", "scope contains unsupported constructs",
                    "completeness depends on unverified assumptions")
        for item, reason in zip(variants, expected):
            with self.subTest(reason=reason):
                result = evaluate_negative_claim(item, request())
                self.assertFalse(result.admissible)
                self.assertIn(reason, result.reasons)

    def test_active_invalidation_trigger_blocks_stale_claim(self):
        item = claim(invalidation_triggers=("source-tree-changed",))
        result = evaluate_negative_claim(
            item, request(active_invalidation_triggers=("source-tree-changed",))
        )
        self.assertFalse(result.admissible)
        self.assertIn("one or more completeness invalidation triggers are active", result.reasons)

    def test_evidence_must_bind_to_the_claim_snapshot(self):
        item = claim(evidence_refs=(EvidenceRef(
            evidence_id="wrong-snapshot", source_snapshot_id="git:other",
            producer_id="enumerator", method_id="walk", observed_at="now",
        ),))
        result = evaluate_negative_claim(item, request())
        self.assertFalse(result.admissible)
        self.assertIn("evidence snapshot does not match completeness snapshot", result.reasons)

    def test_non_supported_claim_does_not_become_true_or_false(self):
        result = evaluate_negative_claim(
            claim(status=CompletenessStatus.NOT_SUPPORTED), request()
        )
        self.assertFalse(result.admissible)
        self.assertIsInstance(result.reasons, tuple)


class CompletenessPersistenceTests(unittest.TestCase):
    def test_m752_database_migrates_without_losing_existing_event_history(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy.sqlite"
            payload = json.dumps({
                "assertion_id": "legacy-assertion", "proposition_id": "prop",
                "polarity": "supports", "scope_id": "scope",
                "method_id": "method", "observed_at": "now",
                "evidence_refs": [], "limitations": [], "invalidation_triggers": [],
            }, sort_keys=True, separators=(",", ":"))
            payload_hash = hashlib.sha256(payload.encode()).hexdigest()
            event_id = "assertion:legacy-assertion:1"
            previous_hash = "0" * 64
            event_hash = hashlib.sha256(
                f"1\\n{event_id}\\n{payload_hash}\\n{previous_hash}".encode()
            ).hexdigest()
            raw = sqlite3.connect(database)
            raw.execute("""
                CREATE TABLE epistemic_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    record_type TEXT NOT NULL CHECK(record_type IN ('assertion', 'gap')),
                    record_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision >= 1),
                    payload TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE,
                    UNIQUE(record_type, record_id, revision)
                )
            """)
            raw.execute("""
                INSERT INTO epistemic_events VALUES
                (1, ?, 'assertion', 'legacy-assertion', 1, ?, ?, ?, ?)
            """, (event_id, payload, payload_hash, previous_hash, event_hash))
            raw.commit()
            raw.close()

            with EpistemicStore(database) as store:
                self.assertEqual(store.event_count(), 1)
                self.assertTrue(store.verify_integrity())
                self.assertTrue(store.record_completeness_claim(claim()))
                self.assertEqual(store.event_count(), 2)
                self.assertTrue(store.verify_integrity())

    def test_completeness_claim_is_persisted_idempotently_and_retrievable(self):
        with tempfile.TemporaryDirectory() as directory:
            with EpistemicStore(Path(directory) / "epistemic.sqlite") as store:
                item = claim()
                self.assertTrue(store.record_completeness_claim(item))
                self.assertFalse(store.record_completeness_claim(item))
                history = store.completeness_history("cc-1")
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["payload"]["predicate_id"], "contains:python-source-unit")
                self.assertTrue(store.verify_integrity())


if __name__ == "__main__":
    unittest.main()

"""M7.5.23 tests for independent execution/qualification composition."""
import hashlib
import json
import unittest

from audit_engine.semantic_audit.epistemic.obligation_composition import (
    ObligationCompositionError,
    compose_execution_and_semantic_obligations,
    verify_obligation_composition,
)


def seal(payload, identity):
    canonical = (json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False) + "\n").encode()
    return {**payload, identity: hashlib.sha256(canonical).hexdigest()}


class ObligationCompositionTests(unittest.TestCase):
    def setUp(self):
        self.ids = [
            "rule:AE32A-SOURCE:coverage:source_manifest",
            "rule:AE32A-EXAMPLE:evidence:example_observation",
        ]
        self.execution = seal({
            "schema": "ae32c/execution-obligation-reconciliation/v1",
            "claim_id": "claim:composition",
            "source_snapshot_id": "snapshot:composition",
            "plan_sha256": "a" * 64,
            "coverage_manifest_sha256": "b" * 64,
            "dossier_id": "dossier:composition",
            "obligations": [
                {"obligation_id": self.ids[0], "kind": "source_manifest",
                 "status": "MANIFEST_VERIFIED_WITHIN_DECLARED_INVENTORY",
                 "reason": "verified", "candidate_ids": [], "outcome_ids": []},
                {"obligation_id": self.ids[1], "kind": "typed_evidence",
                 "status": "UNKNOWN",
                 "reason": "extractor_output_is_not_typed_semantic_evidence",
                 "candidate_ids": [], "outcome_ids": []},
            ],
            "summary": {
                "extractor_execution_complete_for_declared_coverage": True,
                "epistemic_coverage_upgraded": False,
                "coverage_dossier_mutated": False,
            },
            "authority": {
                "semantic_evidence_sufficiency_established": False,
                "proposition_truth_established": False,
                "graph_completeness_established": False,
                "audit_decision_authority": False,
                "production_approval": False,
            },
        }, "reconciliation_sha256")
        self.execution_replay = {
            "reconciliation_sha256": self.execution["reconciliation_sha256"],
            "ledger_integrity": True,
            "semantic_replay": True,
            "dossier_unchanged": True,
        }
        self.qualification = seal({
            "schema": "ae32c/qualification-obligation-reconciliation/v1",
            "claim_id": "claim:composition",
            "source_snapshot_id": "snapshot:composition",
            "plan_sha256": "a" * 64,
            "coverage_manifest_sha256": "b" * 64,
            "expected_obligation_ids": self.ids,
            "qualification_replay": {"semantic_replay": True},
            "obligation_reconciliations": [
                {"obligation_id": self.ids[0], "dimension": "coverage",
                 "disposition": "NOT_IN_SCOPE", "reason": "coverage excluded",
                 "observation_ids": []},
                {"obligation_id": self.ids[1], "dimension": "evidence",
                 "disposition": "SUPPORTED_WITHIN_CONTRACT",
                 "reason": "narrow contract", "observation_ids": ["obs:1"]},
            ],
            "authority": {
                "all_evidence_obligations_satisfied": False,
                "epistemic_coverage_manifest_mutated": False,
                "epistemic_assertions_created": False,
                "proposition_truth_established": False,
                "audit_decision_authority": False,
                "allow_deny_authority": False,
                "production_approval": False,
            },
        }, "reconciliation_sha256")
        self.consumer = self.current_consumer()

    def current_consumer(self):
        return {
            "consumer_operation_status": "REPLAY_VERIFIED",
            "record_id": self.qualification["reconciliation_sha256"],
            "consumer_id": "test-consumer",
            "operation": "verify",
            "preflight": {"consumer_preflight_status": "CURRENTNESS_CONFIRMED"},
            "semantic_replay_performed": True,
            "replay_result": {
                "record_id": self.qualification["reconciliation_sha256"],
                "ledger_integrity": True,
                "historical_replay": True,
                "semantic_replay": True,
            },
            "downstream_authorization": "NOT_EVALUATED",
        }

    def test_current_results_compose_as_separate_assessment_axes(self):
        result = compose_execution_and_semantic_obligations(
            self.execution, self.execution_replay, self.qualification, self.consumer)
        by_id = {row["obligation_id"]: row for row in result["obligations"]}
        typed = by_id[self.ids[1]]
        self.assertEqual(typed["execution_assessment"]["status"], "UNKNOWN")
        self.assertEqual(typed["semantic_qualification"]["disposition"],
                         "SUPPORTED_WITHIN_CONTRACT")
        coverage = by_id[self.ids[0]]
        self.assertEqual(coverage["execution_assessment"]["status"],
                         "MANIFEST_VERIFIED_WITHIN_DECLARED_INVENTORY")
        self.assertEqual(coverage["semantic_qualification"]["disposition"], "NOT_IN_SCOPE")
        self.assertTrue(result["qualification_currentness"]["semantic_dispositions_are_current"])
        self.assertFalse(result["authority"]["epistemic_evidence_accepted"])
        self.assertFalse(result["authority"]["audit_decision_authority"])
        self.assertFalse(result["authority"]["production_approval"])

    def test_invalidated_qualification_is_retained_only_as_historical_context(self):
        blocked = dict(self.consumer)
        blocked.update({
            "consumer_operation_status": "BLOCKED_INVALIDATED",
            "preflight": {"consumer_preflight_status": "BLOCKED_INVALIDATED"},
            "semantic_replay_performed": False,
            "replay_result": None,
        })
        result = compose_execution_and_semantic_obligations(
            self.execution, self.execution_replay, self.qualification, blocked)
        typed = next(row for row in result["obligations"] if row["obligation_id"] == self.ids[1])
        self.assertEqual(typed["semantic_qualification"]["state"], "BLOCKED_INVALIDATED")
        self.assertIsNone(typed["semantic_qualification"]["disposition"])
        self.assertEqual(typed["semantic_qualification"]["historical_disposition"],
                         "SUPPORTED_WITHIN_CONTRACT")
        self.assertFalse(result["summary"]["semantic_qualification_current"])
        self.assertTrue(result["summary"]["semantic_qualification_blocked"])
        self.assertFalse(result["authority"]["qualification_reconciliation_currently_replayed"])

    def test_execution_replay_must_be_bound_and_verified(self):
        replay = dict(self.execution_replay, dossier_unchanged=False)
        with self.assertRaisesRegex(ObligationCompositionError, "execution_replay_not_verified"):
            compose_execution_and_semantic_obligations(
                self.execution, replay, self.qualification, self.consumer)

    def test_qualification_consumer_must_bind_the_same_persisted_record(self):
        consumer = dict(self.consumer, record_id="different")
        with self.assertRaisesRegex(ObligationCompositionError,
                                    "qualification_consumer_record_binding_mismatch"):
            compose_execution_and_semantic_obligations(
                self.execution, self.execution_replay, self.qualification, consumer)

    def test_preflight_success_without_semantic_replay_is_rejected(self):
        consumer = dict(self.consumer, semantic_replay_performed=False)
        with self.assertRaisesRegex(ObligationCompositionError,
                                    "qualification_consumer_outcome_invalid"):
            compose_execution_and_semantic_obligations(
                self.execution, self.execution_replay, self.qualification, consumer)

    def test_cross_layer_snapshot_plan_and_manifest_bindings_are_enforced(self):
        changed = dict(self.qualification, plan_sha256="f" * 64)
        changed = seal({k: v for k, v in changed.items() if k != "reconciliation_sha256"},
                       "reconciliation_sha256")
        consumer = self.current_consumer()
        consumer["record_id"] = changed["reconciliation_sha256"]
        consumer["replay_result"] = dict(consumer["replay_result"],
                                         record_id=changed["reconciliation_sha256"])
        with self.assertRaisesRegex(ObligationCompositionError,
                                    "cross_layer_binding_mismatch:plan_sha256"):
            compose_execution_and_semantic_obligations(
                self.execution, self.execution_replay, changed, consumer)

    def test_missing_or_duplicate_obligation_rows_fail_closed(self):
        changed = dict(self.qualification)
        changed["expected_obligation_ids"] = self.ids[:-1]
        changed = seal({k: v for k, v in changed.items() if k != "reconciliation_sha256"},
                       "reconciliation_sha256")
        consumer = self.current_consumer()
        consumer["record_id"] = changed["reconciliation_sha256"]
        consumer["replay_result"] = dict(consumer["replay_result"],
                                         record_id=changed["reconciliation_sha256"])
        with self.assertRaisesRegex(ObligationCompositionError,
                                    "cross_layer_obligation_inventory_mismatch"):
            compose_execution_and_semantic_obligations(
                self.execution, self.execution_replay, changed, consumer)

    def test_report_digest_tampering_is_rejected(self):
        changed = dict(self.execution)
        changed["summary"] = dict(changed["summary"], extractor_execution_complete_for_declared_coverage=False)
        with self.assertRaisesRegex(ObligationCompositionError,
                                    "execution_reconciliation_digest_mismatch"):
            compose_execution_and_semantic_obligations(
                changed, self.execution_replay, self.qualification, self.consumer)

    def test_source_layer_authority_expansion_is_rejected_even_with_a_valid_digest(self):
        changed = dict(self.execution)
        changed["authority"] = dict(changed["authority"], proposition_truth_established=True)
        changed = seal({k: v for k, v in changed.items() if k != "reconciliation_sha256"},
                       "reconciliation_sha256")
        replay = dict(self.execution_replay,
                      reconciliation_sha256=changed["reconciliation_sha256"])
        with self.assertRaisesRegex(ObligationCompositionError,
                                    "execution_reconciliation_authority_boundary_violation"):
            compose_execution_and_semantic_obligations(
                changed, replay, self.qualification, self.consumer)

    def test_qualification_replay_flag_and_authority_boundary_are_required(self):
        changed = dict(self.qualification)
        changed["qualification_replay"] = {"semantic_replay": False}
        changed = seal({k: v for k, v in changed.items() if k != "reconciliation_sha256"},
                       "reconciliation_sha256")
        consumer = self.current_consumer()
        consumer["record_id"] = changed["reconciliation_sha256"]
        consumer["replay_result"] = dict(consumer["replay_result"],
                                         record_id=changed["reconciliation_sha256"])
        with self.assertRaisesRegex(ObligationCompositionError,
                                    "qualification_reconciliation_replay_not_verified"):
            compose_execution_and_semantic_obligations(
                self.execution, self.execution_replay, changed, consumer)

    def test_composition_can_be_independently_replayed_and_tampering_detected(self):
        result = compose_execution_and_semantic_obligations(
            self.execution, self.execution_replay, self.qualification, self.consumer)
        replay = verify_obligation_composition(
            result, self.execution, self.execution_replay,
            self.qualification, self.consumer)
        self.assertTrue(replay["semantic_replay"])
        self.assertEqual(replay["obligation_count"], 2)
        changed = dict(result)
        changed["summary"] = dict(changed["summary"], epistemic_evidence_acceptance_established=True)
        with self.assertRaisesRegex(ObligationCompositionError, "composition_digest_mismatch"):
            verify_obligation_composition(
                changed, self.execution, self.execution_replay,
                self.qualification, self.consumer)


if __name__ == "__main__":
    unittest.main()

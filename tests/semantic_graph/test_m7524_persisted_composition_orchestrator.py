"""M7.5.24 orchestration tests: retrieval, invocation order and fail-closed paths."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator import (
    ObligationCompositionOrchestrationError,
    verify_orchestrated_obligation_composition,
    verify_persisted_cross_layer_obligation_composition,
)
from test_m7523_obligation_composition import ObligationCompositionTests


class PersistedCompositionOrchestrationTests(unittest.TestCase):
    def setUp(self):
        fixture = ObligationCompositionTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.fixture = fixture
        self.execution_store = MagicMock()
        self.qualification_store = MagicMock()
        self.check_store = MagicMock()
        self.execution_store.get.return_value = fixture.execution
        self.qualification_store.get.return_value = {
            "record_id": fixture.qualification["reconciliation_sha256"],
            "reconciliation": fixture.qualification,
            "qualification": {"qualification_sha256": "fixture"},
            "observation_bundle": {"bundle_sha256": "fixture"},
        }
        self.events = []

    def invoke(self, *, consumer_result=None):
        f = self.fixture
        self.execution_store.get.return_value = f.execution
        self.qualification_store.get.return_value = {
            "record_id": f.qualification["reconciliation_sha256"],
            "reconciliation": f.qualification,
            "qualification": {"qualification_sha256": "fixture"},
            "observation_bundle": {"bundle_sha256": "fixture"},
        }

        def execution_replay(*args, **kwargs):
            self.events.append("execution_replay")
            return f.execution_replay

        def qualification_context(**kwargs):
            self.events.append("derive_current_context")
            return {"source_snapshot_id": "snapshot:fixture"}

        def qualification_consumer(*args, **kwargs):
            self.events.append("qualification_consumer")
            self.assertEqual(kwargs["current_context"], {
                "source_snapshot_id": "snapshot:fixture"})
            return consumer_result or f.consumer

        with (
            patch(
                "audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator."
                "verify_execution_obligation_reconciliation",
                side_effect=execution_replay,
            ) as execution_verify,
            patch(
                "audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator."
                "qualification_consumer_current_context",
                side_effect=qualification_context,
            ),
            patch(
                "audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator."
                "verify_persisted_qualification_reconciliation_for_consumer",
                side_effect=qualification_consumer,
            ) as qualification_verify,
        ):
            result = verify_persisted_cross_layer_obligation_composition(
                "execution-id",
                f.qualification["reconciliation_sha256"],
                execution_reconciliation_store=self.execution_store,
                dossier_id="dossier",
                claim=object(),
                plan=object(),
                coverage_manifest=object(),
                source_manifest={},
                inventory={},
                execution_report={},
                repository_root=".",
                assurance_store=object(),
                epistemic_store=object(),
                dossier_store=object(),
                qualification_reconciliation_store=self.qualification_store,
                qualification_check_store=self.check_store,
                consumer_id="orchestrator-test",
                operation="verify",
                current_qualification={},
                current_observation_bundle={},
            )
        execution_verify.assert_called_once()
        qualification_verify.assert_called_once()
        return result

    def test_orchestrator_retrieves_records_and_invokes_real_verifier_contracts_in_order(self):
        result = self.invoke()
        self.assertEqual(self.events, [
            "execution_replay", "derive_current_context", "qualification_consumer"])
        self.assertEqual(result["schema"],
                         "ae32c/orchestrated-persisted-obligation-composition/v1")
        self.assertEqual(result["composition"]["schema"],
                         "ae32c/execution-semantic-obligation-composition/v1")
        self.assertTrue(result["authority"]["execution_replay_verified"])
        self.assertFalse(result["authority"]["epistemic_evidence_accepted"])
        self.assertEqual(result["authority"]["downstream_authorization"],
                         "NOT_EVALUATED")
        checked = verify_orchestrated_obligation_composition(result)
        self.assertTrue(checked["orchestration_envelope_integrity"])
        self.assertFalse(checked["semantic_replay_performed"])

    def test_historically_invalidated_qualification_is_composed_as_blocked(self):
        blocked = dict(self.fixture.consumer)
        blocked.update({
            "consumer_operation_status": "BLOCKED_INVALIDATED",
            "preflight": {"consumer_preflight_status": "BLOCKED_INVALIDATED"},
            "semantic_replay_performed": False,
            "replay_result": None,
        })
        result = self.invoke(consumer_result=blocked)
        self.assertEqual(
            result["composition"]["qualification_currentness"]["state"],
            "BLOCKED_INVALIDATED")
        self.assertFalse(result["authority"]["qualification_currently_replayed"])

    def test_missing_execution_record_fails_before_any_verifier_is_called(self):
        self.execution_store.get.return_value = None
        with self.assertRaisesRegex(
                ObligationCompositionOrchestrationError,
                "execution_reconciliation_not_found"):
            self.invoke()
        self.assertEqual(self.events, [])

    def test_missing_qualification_record_fails_closed(self):
        self.qualification_store.get.return_value = None
        with self.assertRaisesRegex(
                ObligationCompositionOrchestrationError,
                "qualification_reconciliation_not_found"):
            self.invoke()
        self.assertEqual(self.events, [])

    def test_persisted_qualification_identity_mismatch_is_rejected(self):
        self.qualification_store.get.return_value = {
            "record_id": "different",
            "reconciliation": self.fixture.qualification,
        }
        with self.assertRaisesRegex(
                ObligationCompositionOrchestrationError,
                "qualification_persisted_envelope_invalid"):
            self.invoke()
        self.assertEqual(self.events, [])

    def test_orchestration_envelope_tampering_is_detected(self):
        result = self.invoke()
        changed = dict(result)
        changed["authority"] = dict(
            changed["authority"], production_approval=True)
        with self.assertRaisesRegex(
                ObligationCompositionOrchestrationError,
                "orchestration_digest_mismatch"):
            verify_orchestrated_obligation_composition(changed)


if __name__ == "__main__":
    unittest.main()

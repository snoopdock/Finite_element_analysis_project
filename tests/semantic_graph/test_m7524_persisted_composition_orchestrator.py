"""M7.5.24 orchestration tests: retrieval, invocation order and fail-closed paths."""
from __future__ import annotations

import hashlib
import unittest
from unittest.mock import MagicMock, patch

import test_m7514_execution_obligation_reconciliation as execution_fixture
import test_m7517_qualification_reconciliation as qualification_fixture

from audit_engine.semantic_audit.epistemic.execution_obligation_reconciliation import (
    build_and_persist_execution_obligation_reconciliation,
)
from audit_engine.semantic_audit.epistemic.extractor_execution import (
    build_extractor_execution_report,
)
from audit_engine.semantic_audit.epistemic.source_inventory import (
    build_source_extractor_inventory,
)
from audit_engine.semantic_audit.epistemic.semantic_qualification import (
    qualify_typed_evidence_observations,
)
from audit_engine.semantic_audit.epistemic.qualification_reconciliation import (
    reconcile_semantic_qualifications,
)
from audit_engine.semantic_audit.epistemic.qualification_reconciliation_store import (
    QualificationReconciliationStore,
    persist_verified_qualification_reconciliation,
)
from audit_engine.semantic_audit.epistemic.qualification_consumer_gate import (
    QualificationConsumerCheckStore,
)
from audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator import (
    ObligationCompositionOrchestrationError,
    verify_orchestrated_obligation_composition,
    verify_persisted_cross_layer_obligation_composition,
)
import test_m7523_obligation_composition as composition_fixture


class PersistedCompositionOrchestrationTests(unittest.TestCase):
    def setUp(self):
        fixture = composition_fixture.ObligationCompositionTests()
        fixture.setUp()
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
                f.execution["reconciliation_sha256"],
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

    def test_orchestrator_retrieves_records_and_invokes_verification_apis_in_order(self):
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

    def test_execution_persisted_identity_mismatch_is_rejected(self):
        self.execution_store.get.return_value = dict(
            self.fixture.execution, reconciliation_sha256="different")
        with self.assertRaisesRegex(
                ObligationCompositionOrchestrationError,
                "execution_persisted_record_identity_mismatch"):
            self.invoke()
        self.assertEqual(self.events, [])

    def test_end_to_end_uses_real_persisted_ledgers_and_verification_apis(self):
        f = execution_fixture.ExecutionObligationReconciliationTests()
        f.setUp()
        self.addCleanup(f.tearDown)

        external_raw = b"response = 'untrusted'\\n"
        (f.root / "src/external.py").write_bytes(external_raw)
        entries = []
        for relative in ("src/app.py", "src/external.py"):
            raw = (f.root / relative).read_bytes()
            entries.append({
                "path": relative,
                "mode": "100644",
                "object_type": "blob",
                "content_sha256": hashlib.sha256(raw).hexdigest(),
            })
        f.source = execution_fixture.source_manifest(entries)
        f.inventory = build_source_extractor_inventory(f.source)
        f.execution = build_extractor_execution_report(
            f.source, f.inventory, f.root)

        execution_reconciliation = (
            build_and_persist_execution_obligation_reconciliation(
                reconciliation_store=f.reconciliations,
                **f.kwargs(),
            )
        )

        observation = qualification_fixture.observation(
            f.claim.source_snapshot_id,
            "src/external.py",
            external_raw,
            "external_model_response_intake",
            "rule:AE32A-AE28-EXTERNAL-MODEL-INPUT:evidence:external_model_response_intake",
            "unvalidated_external_model_response",
            {"response": "untrusted"},
        )
        bundle_payload = {
            "schema": "ae32c/typed-evidence-observation-bundle/v1",
            "source_snapshot_id": f.claim.source_snapshot_id,
            "plan_sha256": f.plan.plan_sha256,
            "inventory_sha256": f.inventory["inventory_sha256"],
            "execution_report_sha256": f.execution["report_sha256"],
            "observation_count": 1,
            "observations": [observation],
            "unresolved_evidence_kinds": [],
            "summary": {"semantic_evidence_accepted_count": 0},
            "authority": {"proposition_truth_established": False},
        }
        canonical = (
            __import__("json").dumps(
                bundle_payload, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ) + "\\n"
        ).encode()
        bundle = {
            **bundle_payload,
            "bundle_sha256": hashlib.sha256(canonical).hexdigest(),
        }
        qualification = qualify_typed_evidence_observations(
            bundle,
            claim=f.claim,
            plan=f.plan,
            coverage_manifest=f.manifest,
            source_manifest=f.source,
            repository_root=f.root,
        )
        qualification_reconciliation = reconcile_semantic_qualifications(
            qualification,
            bundle,
            claim=f.claim,
            plan=f.plan,
            coverage_manifest=f.manifest,
            source_manifest=f.source,
            repository_root=f.root,
        )

        root = f.root
        qualification_store = QualificationReconciliationStore(
            root / "qualification-reconciliation.sqlite")
        check_store = QualificationConsumerCheckStore(
            root / "qualification-consumer-checks.sqlite")
        self.addCleanup(qualification_store.close)
        self.addCleanup(check_store.close)
        persist_verified_qualification_reconciliation(
            qualification_store,
            qualification_reconciliation,
            qualification,
            bundle,
            claim=f.claim,
            plan=f.plan,
            coverage_manifest=f.manifest,
            source_manifest=f.source,
            repository_root=f.root,
        )

        result = verify_persisted_cross_layer_obligation_composition(
            execution_reconciliation["reconciliation_sha256"],
            qualification_reconciliation["reconciliation_sha256"],
            execution_reconciliation_store=f.reconciliations,
            dossier_id="dossier:m7514",
            claim=f.claim,
            plan=f.plan,
            coverage_manifest=f.manifest,
            source_manifest=f.source,
            inventory=f.inventory,
            execution_report=f.execution,
            repository_root=f.root,
            assurance_store=f.assurance,
            epistemic_store=f.epistemic,
            dossier_store=f.dossiers,
            qualification_reconciliation_store=qualification_store,
            qualification_check_store=check_store,
            consumer_id="m7524-end-to-end-test",
            operation="verify-persisted-cross-layer-composition",
            current_qualification=qualification,
            current_observation_bundle=bundle,
        )
        self.assertTrue(result["execution_replay"]["semantic_replay"])
        self.assertEqual(
            result["qualification_consumer_result"]["consumer_operation_status"],
            "REPLAY_VERIFIED",
        )
        self.assertEqual(
            result["composition"]["qualification_currentness"]["state"],
            "CURRENT_REPLAY_VERIFIED",
        )
        self.assertFalse(result["authority"]["epistemic_evidence_accepted"])
        self.assertEqual(len(check_store.history()), 1)

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

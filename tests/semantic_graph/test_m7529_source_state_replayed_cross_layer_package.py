"""M7.5.29 strict source-state-replayed cross-layer package tests."""
from __future__ import annotations

import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch

import test_m7526_cross_layer_snapshot_provenance as provenance_fixture
from audit_engine.semantic_audit.epistemic.cross_layer_snapshot_provenance import (
    verify_cross_layer_snapshot_provenance,
)
from audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator import (
    CrossLayerObligationPackageError,
    verify_cross_layer_obligation_package_envelope,
    verify_persisted_cross_layer_obligation_package,
)
from audit_engine.semantic_audit.epistemic.qualification_consumer_gate import (
    QualificationConsumerCheckStore,
)


def _canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _seal(value, key):
    payload = {name: item for name, item in value.items() if name != key}
    return {**payload, key: hashlib.sha256(_canonical(payload)).hexdigest()}


class M7529SourceStateReplayedPackageTests(unittest.TestCase):
    def setUp(self):
        fixture = provenance_fixture.M7526SnapshotProvenanceTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.fixture = fixture
        self.execution_store = MagicMock()
        self.qualification_store = MagicMock()
        self.check_store = MagicMock()
        self.execution_store.get.return_value = fixture.execution
        self.qualification_store.get.return_value = {
            "record_id": fixture.qualification_reconciliation["reconciliation_sha256"],
            "reconciliation": fixture.qualification_reconciliation,
            "qualification": fixture.qualification,
            "observation_bundle": fixture.bundle,
        }
        self.execution_replay = {
            "reconciliation_sha256": fixture.execution["reconciliation_sha256"],
            "ledger_integrity": True,
            "semantic_replay": True,
        }
        self.consumer = {
            "consumer_operation_status": "REPLAY_VERIFIED",
            "record_id": fixture.qualification_reconciliation["reconciliation_sha256"],
            "consumer_id": "m7529-test-consumer",
            "operation": "strict-package-test",
            "semantic_replay_performed": True,
            "replay_result": {"replay_verified": True},
            "downstream_authorization": "NOT_EVALUATED",
        }
        self.composition = fixture.composition
        self.events = []

    def _invoke(self, *, source_mutation=None, consumer=None, composition=None):
        f = self.fixture
        consumer_result = consumer or self.consumer
        composition_result = composition or self.composition

        def replay(*args, **kwargs):
            self.events.append("execution_replay")
            return self.execution_replay

        def derive_context(**kwargs):
            self.events.append("derive_current_context")
            return {"source_snapshot_id": f.manifest["source_snapshot_id"]}

        def consume(*args, **kwargs):
            self.events.append("qualification_consumer")
            return consumer_result

        patches = (
            patch(
                "audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator."
                "verify_execution_obligation_reconciliation",
                side_effect=replay,
            ),
            patch(
                "audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator."
                "qualification_consumer_current_context",
                side_effect=derive_context,
            ),
            patch(
                "audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator."
                "verify_persisted_qualification_reconciliation_for_consumer",
                side_effect=consume,
            ),
            patch(
                "audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator."
                "compose_execution_and_semantic_obligations",
                return_value=composition_result,
            ),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            return verify_persisted_cross_layer_obligation_package(
                f.execution["reconciliation_sha256"],
                f.qualification_reconciliation["reconciliation_sha256"],
                execution_reconciliation_store=self.execution_store,
                dossier_id="dossier:m7529",
                claim=object(),
                plan=object(),
                coverage_manifest=object(),
                source_manifest=f.manifest,
                inventory={},
                execution_report={},
                repository_root=f.root,
                assurance_store=object(),
                epistemic_store=object(),
                dossier_store=object(),
                qualification_reconciliation_store=self.qualification_store,
                qualification_check_store=self.check_store,
                consumer_id="m7529-test-consumer",
                operation="strict-package-test",
                current_qualification=f.qualification,
                current_observation_bundle=f.bundle,
            )

    def test_package_replays_source_state_and_reuses_exact_single_pass_artifacts(self):
        with patch(
            "audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator."
            "verify_cross_layer_snapshot_provenance",
            wraps=verify_cross_layer_snapshot_provenance,
        ) as provenance_verify:
            package = self._invoke()

        self.assertEqual(package["schema"], "ae32c/cross-layer-obligation-package/v1")
        self.assertEqual(
            package["provenance"]["snapshot_identity_assurance"],
            "SOURCE_STATE_REPLAY_VERIFIED",
        )
        self.assertEqual(self.execution_store.get.call_count, 1)
        self.assertEqual(self.qualification_store.get.call_count, 1)
        self.assertEqual(self.events, [
            "execution_replay", "derive_current_context",
            "qualification_consumer", "execution_replay",
        ])
        args, kwargs = provenance_verify.call_args
        self.assertIs(args[0], self.fixture.manifest)
        self.assertIs(args[1], self.fixture.execution)
        self.assertIs(args[2], self.fixture.qualification_reconciliation)
        self.assertIs(args[3], self.fixture.qualification)
        self.assertIs(args[4], self.fixture.bundle)
        self.assertEqual(
            kwargs["expected_source_revision"],
            self.fixture.manifest["source"]["commit_oid"],
        )
        self.assertIs(kwargs["repository_root"], self.fixture.root)
        checked = verify_cross_layer_obligation_package_envelope(package)
        self.assertTrue(checked["package_content_integrity"])
        self.assertFalse(checked["source_state_replay_performed_by_this_check"])

    def test_dirty_checkout_fails_closed_without_declared_only_downgrade(self):
        (self.fixture.root / "module.py").write_text("VALUE = 99\n", encoding="utf-8")
        with self.assertRaisesRegex(
            CrossLayerObligationPackageError,
            "strict_source_state_replay_or_binding_failed",
        ):
            self._invoke()

    def test_changed_commit_fails_closed(self):
        (self.fixture.root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.fixture._git("add", ".")
        self.fixture._git("commit", "-qm", "source changed after manifest")
        with self.assertRaisesRegex(
            CrossLayerObligationPackageError,
            "strict_source_state_replay_or_binding_failed",
        ):
            self._invoke()

    def test_declared_only_provenance_is_rejected_by_envelope_consumer(self):
        package = self._invoke()
        changed_provenance = dict(
            package["provenance"],
            snapshot_identity_assurance="DECLARED_ONLY",
        )
        changed_provenance = _seal(
            changed_provenance, "cross_layer_snapshot_identity_sha256")
        changed = dict(package, provenance=changed_provenance)
        changed = _seal(changed, "package_sha256")
        with self.assertRaisesRegex(
            CrossLayerObligationPackageError,
            "package_source_state_replay_not_verified",
        ):
            verify_cross_layer_obligation_package_envelope(changed)

    def test_qualification_invalidation_is_preserved_as_a_separate_axis(self):
        blocked_consumer = dict(
            self.consumer,
            consumer_operation_status="BLOCKED_INVALIDATED",
            semantic_replay_performed=False,
            replay_result=None,
        )
        blocked_composition = dict(
            self.composition,
            qualification_currentness={"state": "BLOCKED_INVALIDATED"},
        )
        blocked_composition = _seal(blocked_composition, "composition_sha256")
        package = self._invoke(
            consumer=blocked_consumer,
            composition=blocked_composition,
        )
        self.assertEqual(
            package["provenance"]["qualification_currentness"],
            "BLOCKED_INVALIDATED",
        )
        checked = verify_cross_layer_obligation_package_envelope(package)
        self.assertEqual(checked["qualification_currentness"], "BLOCKED_INVALIDATED")

    def test_resealed_orchestration_cannot_expand_v1_authority(self):
        package = self._invoke()
        changed_orchestration = dict(package["orchestration"])
        changed_orchestration["authority"] = dict(
            changed_orchestration["authority"], production_approval=True)
        changed_orchestration = _seal(
            changed_orchestration, "orchestration_sha256")
        changed_package = dict(package, orchestration=changed_orchestration)
        changed_package = _seal(changed_package, "package_sha256")
        with self.assertRaisesRegex(
            CrossLayerObligationPackageError,
            "package_orchestration_authority_claim_invalid",
        ):
            verify_cross_layer_obligation_package_envelope(changed_package)

    def test_resealed_provenance_cannot_expand_authority_or_claim_atomicity(self):
        package = self._invoke()
        changed_provenance = dict(package["provenance"])
        changed_provenance["authority"] = dict(
            changed_provenance["authority"], production_approval=True)
        changed_provenance = _seal(
            changed_provenance, "cross_layer_snapshot_identity_sha256")
        changed_package = dict(package, provenance=changed_provenance)
        changed_package = _seal(changed_package, "package_sha256")
        with self.assertRaisesRegex(
            CrossLayerObligationPackageError,
            "package_provenance_authority_claim_invalid",
        ):
            verify_cross_layer_obligation_package_envelope(changed_package)

        changed_provenance = dict(package["provenance"], atomic_cross_store_snapshot=True)
        changed_provenance = _seal(
            changed_provenance, "cross_layer_snapshot_identity_sha256")
        changed_package = dict(package, provenance=changed_provenance)
        changed_package = _seal(changed_package, "package_sha256")
        with self.assertRaisesRegex(
            CrossLayerObligationPackageError,
            "package_provenance_atomicity_claim_invalid",
        ):
            verify_cross_layer_obligation_package_envelope(changed_package)

    def test_package_and_each_inner_seal_detect_tampering(self):
        package = self._invoke()
        changed_outer = dict(package, trust_anchor="EXTERNAL")
        with self.assertRaisesRegex(CrossLayerObligationPackageError, "package_digest_mismatch"):
            verify_cross_layer_obligation_package_envelope(changed_outer)

        changed_orchestration = dict(package)
        changed_orchestration["orchestration"] = dict(
            package["orchestration"], authority=dict(
                package["orchestration"]["authority"], production_approval=True))
        changed_orchestration = _seal(changed_orchestration, "package_sha256")
        with self.assertRaisesRegex(
            CrossLayerObligationPackageError, "package_inner_seal_invalid"):
            verify_cross_layer_obligation_package_envelope(changed_orchestration)

        changed_provenance = dict(package)
        changed_provenance["provenance"] = dict(
            package["provenance"], production_approval=True)
        changed_provenance = _seal(changed_provenance, "package_sha256")
        with self.assertRaisesRegex(
            CrossLayerObligationPackageError, "package_inner_seal_invalid"):
            verify_cross_layer_obligation_package_envelope(changed_provenance)

    def test_missing_persisted_record_aborts_before_source_replay(self):
        self.execution_store.get.return_value = None
        with patch(
            "audit_engine.semantic_audit.epistemic.obligation_composition_orchestrator."
            "verify_cross_layer_snapshot_provenance",
            wraps=verify_cross_layer_snapshot_provenance,
        ) as provenance_verify:
            with self.assertRaisesRegex(Exception, "execution_reconciliation_not_found"):
                self._invoke()
        provenance_verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""M7.5.25 deterministic TOCTOU and cross-store failure-injection tests."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import test_m7521_qualification_reconciliation_consumer as m7521

from audit_engine.semantic_audit.epistemic.qualification_reconciliation_consumer import (
    QualificationConsumerReplayError,
)


class CrossStoreConsistencyFailureInjectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = m7521.QualificationReconciliationConsumerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def _invalidate(self):
        changed = dict(self.fixture.context, plan_sha256="f" * 64)
        return self.fixture.reconciliation_store.invalidate(
            self.fixture.record_id, changed)

    def test_invalidation_after_consumer_preflight_is_caught_before_replay(self):
        module = (
            "audit_engine.semantic_audit.epistemic."
            "qualification_reconciliation_consumer"
        )
        # The test patches the imported gate and injects a durable invalidation
        # immediately after CURRENTNESS_CONFIRMED has been recorded.
        from audit_engine.semantic_audit.epistemic import (
            qualification_reconciliation_consumer as consumer_module,
        )
        real_gate = consumer_module.evaluate_qualification_reconciliation_for_consumer

        def gate_then_invalidate(*args, **kwargs):
            result = real_gate(*args, **kwargs)
            self._invalidate()
            return result

        with (
            patch(module + ".evaluate_qualification_reconciliation_for_consumer",
                  side_effect=gate_then_invalidate),
            patch(module + ".verify_persisted_qualification_reconciliation") as replay,
        ):
            with self.assertRaisesRegex(
                    QualificationConsumerReplayError,
                    "qualification_invalidated_before_semantic_replay"):
                self.fixture.consume()
        replay.assert_not_called()
        history = self.fixture.reconciliation_store.invalidation_history(
            self.fixture.record_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(len(self.fixture.check_store.history()), 1)

    def test_invalidation_during_semantic_replay_is_caught_by_postflight(self):
        module = (
            "audit_engine.semantic_audit.epistemic."
            "qualification_reconciliation_consumer"
        )
        from audit_engine.semantic_audit.epistemic import (
            qualification_reconciliation_consumer as consumer_module,
        )
        real_replay = consumer_module.verify_persisted_qualification_reconciliation

        def replay_then_invalidate(*args, **kwargs):
            result = real_replay(*args, **kwargs)
            self._invalidate()
            return result

        with patch(module + ".verify_persisted_qualification_reconciliation",
                   side_effect=replay_then_invalidate):
            with self.assertRaisesRegex(
                    QualificationConsumerReplayError,
                    "qualification_invalidated_during_semantic_replay"):
                self.fixture.consume()
        history = self.fixture.reconciliation_store.invalidation_history(
            self.fixture.record_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(len(self.fixture.check_store.history()), 1)

    def test_successful_consumer_returns_pre_replay_and_post_replay_currentness(self):
        result = self.fixture.consume()
        self.assertEqual(
            result["replay_preflight"]["currentness_status"], "CURRENT")
        self.assertEqual(result["postflight"]["currentness_status"], "CURRENT")
        self.assertTrue(result["semantic_replay_performed"])


if __name__ == "__main__":
    unittest.main()

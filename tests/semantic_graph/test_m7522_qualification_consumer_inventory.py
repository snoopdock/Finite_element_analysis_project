"""M7.5.22 architecture guard for qualification-currentness consumers.

These tests lock the audited dependency boundary: only the explicit consumer
adapter may invoke the currentness gate and historical qualification replay.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[2] / "audit_engine" / "semantic_audit" / "epistemic"
CONSUMER = PACKAGE / "qualification_reconciliation_consumer.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class QualificationConsumerInventoryTests(unittest.TestCase):
    def test_currentness_and_persisted_replay_imports_have_one_explicit_consumer(self):
        allowed = {
            "__init__.py",  # Public re-exports, not execution.
            "qualification_consumer_gate.py",  # The gate calls M7.5.19.
            "qualification_reconciliation_consumer.py",  # The gated consumer.
        }
        violations = []
        for path in sorted(PACKAGE.glob("*.py")):
            if path.name in allowed:
                continue
            tree = _tree(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    names = {item.name for item in node.names}
                    if node.module == "qualification_consumer_gate" or (
                        node.module == "qualification_reconciliation_store"
                        and names.intersection({
                            "evaluate_persisted_qualification_reconciliation_currentness",
                            "verify_persisted_qualification_reconciliation",
                        })
                    ):
                        violations.append(f"{path.name}:{node.lineno}:{node.module}")
        self.assertEqual(violations, [])

    def test_coverage_dossier_and_dossier_replay_remain_qualification_independent(self):
        for name in ("coverage_dossier.py", "dossier_verification.py"):
            with self.subTest(module=name):
                tree = _tree(PACKAGE / name)
                imports = [
                    node for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                    and node.module
                    and ("qualification" in node.module or "qualification" in
                         " ".join(item.name for item in node.names))
                ]
                self.assertEqual(imports, [])

    def test_persisted_assurance_and_execution_reconciliation_remain_independent(self):
        for name in ("persisted_assurance.py", "execution_obligation_reconciliation.py",
                     "assurance.py", "assurance_store.py", "coverage.py", "store.py"):
            with self.subTest(module=name):
                tree = _tree(PACKAGE / name)
                imports = [
                    node for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                    and node.module
                    and ("qualification" in node.module or "qualification" in
                         " ".join(item.name for item in node.names))
                ]
                self.assertEqual(imports, [])

    def test_gated_consumer_orders_preflight_before_historical_semantic_replay(self):
        tree = _tree(CONSUMER)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "verify_persisted_qualification_reconciliation_for_consumer"
        )
        calls = [
            node for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        preflight = [node.lineno for node in calls
                     if node.func.id == "evaluate_qualification_reconciliation_for_consumer"]
        replay = [node.lineno for node in calls
                  if node.func.id == "verify_persisted_qualification_reconciliation"]
        self.assertEqual(len(preflight), 1)
        self.assertEqual(len(replay), 1)
        self.assertLess(preflight[0], replay[0])

    def test_semantic_qualification_reconciliation_is_not_a_persisted_consumer(self):
        tree = _tree(PACKAGE / "qualification_reconciliation.py")
        imports = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module in {"qualification_consumer_gate",
                                "qualification_reconciliation_store"}
        ]
        self.assertEqual(imports, [])


if __name__ == "__main__":
    unittest.main()

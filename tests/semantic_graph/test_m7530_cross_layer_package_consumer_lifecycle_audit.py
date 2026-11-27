"""M7.5.30 audit of cross-layer package consumers and lifecycle boundaries."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = Path(
    "audit_engine/semantic_audit/epistemic/obligation_composition_orchestrator.py"
)
PACKAGE_API_NAMES = {
    "verify_persisted_cross_layer_obligation_package",
    "verify_cross_layer_obligation_package_envelope",
}
PACKAGE_SCHEMA = "ae32c/cross-layer-obligation-package/v1"
PRODUCTION_ROOTS = (
    ROOT / "audit_engine",
    ROOT / "tools",
    ROOT / "decision_memory",
)
EXCLUDED_PARTS = {
    ".git", ".venv", "venv", "__pycache__", "build", "dist", "node_modules",
}
ADJACENT_INDEPENDENT_CONSUMERS = (
    "audit_engine/semantic_audit/epistemic/qualification_reconciliation_consumer.py",
    "audit_engine/semantic_audit/epistemic/execution_obligation_reconciliation.py",
    "audit_engine/semantic_audit/epistemic/coverage_dossier.py",
    "audit_engine/semantic_audit/epistemic/dossier_verification.py",
    "audit_engine/semantic_audit/epistemic/persisted_assurance.py",
)


def _production_files() -> list[Path]:
    files = []
    for root in PRODUCTION_ROOTS:
        if root.exists():
            files.extend(
                path for path in root.rglob("*.py")
                if not any(part in EXCLUDED_PARTS for part in path.parts)
            )
    return sorted(set(files))


def _tree(relative_path: str | Path) -> ast.Module:
    path = ROOT / relative_path
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one top-level function {name}, found {len(matches)}")
    return matches[0]


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


class M7530CrossLayerPackageConsumerLifecycleAuditTests(unittest.TestCase):
    def test_no_production_package_consumer_exists_outside_the_package_boundary(self):
        violations = []
        for path in _production_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            names = {
                node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
            }
            literals = {
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            }
            if path != ROOT / ORCHESTRATOR and (
                names & PACKAGE_API_NAMES or PACKAGE_SCHEMA in literals
            ):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            violations, [],
            "A production package consumer or schema dependency appeared without "
            "an updated consumer contract and inventory.",
        )

        tree = _tree(ORCHESTRATOR)
        definitions = {
            node.name: node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(PACKAGE_API_NAMES.issubset(definitions))
        self.assertIn(
            PACKAGE_SCHEMA,
            {
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            },
        )

        package_producer = definitions["verify_persisted_cross_layer_obligation_package"]
        package_envelope_checker = definitions["verify_cross_layer_obligation_package_envelope"]
        producer_calls = {
            _call_name(node) for node in ast.walk(package_producer)
            if isinstance(node, ast.Call)
        }
        envelope_calls = {
            _call_name(node) for node in ast.walk(package_envelope_checker)
            if isinstance(node, ast.Call)
        }
        self.assertIn("verify_cross_layer_snapshot_provenance", producer_calls)
        self.assertIn("verify_cross_layer_snapshot_provenance_envelope", envelope_calls)
        self.assertNotIn("verify_persisted_cross_layer_obligation_package", producer_calls)
        self.assertNotIn("verify_cross_layer_snapshot_provenance", envelope_calls)

    def test_known_adjacent_consumers_remain_independent(self):
        for relative_path in ADJACENT_INDEPENDENT_CONSUMERS:
            with self.subTest(module=relative_path):
                tree = _tree(relative_path)
                names = {
                    node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
                }
                literals = {
                    node.value for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                imports = [
                    node for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    and "obligation_composition_orchestrator" in ast.dump(node)
                ]
                self.assertTrue(names.isdisjoint(PACKAGE_API_NAMES))
                self.assertNotIn(PACKAGE_SCHEMA, literals)
                self.assertEqual(imports, [])

    def test_package_producer_is_an_ephemeral_return_value_not_a_persistence_api(self):
        tree = _tree(ORCHESTRATOR)
        producer = _function(tree, "verify_persisted_cross_layer_obligation_package")
        argument_names = {
            arg.arg for arg in producer.args.posonlyargs
            + producer.args.args + producer.args.kwonlyargs
        }
        self.assertFalse(any(
            "package_store" in name or "package_ledger" in name
            or "package_repository" in name
            for name in argument_names
        ))
        persistence_calls = {
            "record", "put", "save", "insert", "append_event", "persist"
        }
        invoked = {
            _call_name(node) for node in ast.walk(producer)
            if isinstance(node, ast.Call)
        }
        self.assertTrue(invoked.isdisjoint(persistence_calls))
        self.assertTrue(
            any(isinstance(node, ast.Return) for node in ast.walk(producer)),
            "The producer must continue to return the package explicitly.",
        )

    def test_envelope_checker_cannot_establish_freshness_or_replay(self):
        tree = _tree(ORCHESTRATOR)
        checker = _function(tree, "verify_cross_layer_obligation_package_envelope")
        argument_names = {
            arg.arg for arg in checker.args.posonlyargs
            + checker.args.args + checker.args.kwonlyargs
        }
        self.assertEqual(argument_names, {"package"})
        calls = {
            _call_name(node) for node in ast.walk(checker)
            if isinstance(node, ast.Call)
        }
        self.assertNotIn("verify_cross_layer_snapshot_provenance", calls)
        self.assertNotIn("verify_verified_manifest_data", calls)
        self.assertNotIn("verify_persisted_cross_layer_obligation_package", calls)
        literals = {
            node.value for node in ast.walk(checker)
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, bool))
        }
        self.assertIn(False, literals)
        self.assertIn("source_state_replay_performed_by_this_check", literals)
        self.assertIn("NOT_EVALUATED", literals)

    def test_legacy_m7524_api_does_not_require_or_silently_upgrade_to_a_package(self):
        tree = _tree(ORCHESTRATOR)
        legacy = _function(tree, "verify_persisted_cross_layer_obligation_composition")
        argument_names = {
            arg.arg for arg in legacy.args.posonlyargs
            + legacy.args.args + legacy.args.kwonlyargs
        }
        self.assertTrue(argument_names.isdisjoint(PACKAGE_API_NAMES))
        calls = {
            _call_name(node) for node in ast.walk(legacy)
            if isinstance(node, ast.Call)
        }
        self.assertNotIn("verify_persisted_cross_layer_obligation_package", calls)
        self.assertNotIn("verify_cross_layer_snapshot_provenance", calls)


if __name__ == "__main__":
    unittest.main()

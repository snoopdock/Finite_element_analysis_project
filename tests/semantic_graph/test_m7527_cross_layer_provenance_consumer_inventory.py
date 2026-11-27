"""M7.5.27 inventory guard for cross-layer snapshot provenance consumers.

The M7.5.26 verifier is currently a producer/verification API, not a dependency
of the downstream assurance, dossier, qualification, or orchestration paths.
Any future production consumer must update this inventory and state its
assurance-level and authority contract explicitly.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = Path("audit_engine/semantic_audit/epistemic/cross_layer_snapshot_provenance.py")
PACKAGE_INIT = Path("audit_engine/semantic_audit/epistemic/__init__.py")
ORCHESTRATOR = Path("audit_engine/semantic_audit/epistemic/obligation_composition_orchestrator.py")

API_NAMES = {
    "CrossLayerSnapshotProvenanceError",
    "verify_cross_layer_snapshot_provenance",
    "verify_cross_layer_snapshot_provenance_envelope",
}
ASSURANCE_TERMS = {
    "cross_layer_snapshot_identity_sha256",
    "snapshot_identity_assurance",
    "SOURCE_STATE_REPLAY_VERIFIED",
    "DECLARED_ONLY",
}
KNOWN_INDEPENDENT_CONSUMERS = (
    "audit_engine/semantic_audit/epistemic/coverage_dossier.py",
    "audit_engine/semantic_audit/epistemic/dossier_verification.py",
    "audit_engine/semantic_audit/epistemic/persisted_assurance.py",
    "audit_engine/semantic_audit/epistemic/execution_obligation_reconciliation.py",
    "audit_engine/semantic_audit/epistemic/qualification_reconciliation_consumer.py",
)


def _parse(relative_path: str | Path) -> ast.Module:
    path = ROOT / relative_path
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _production_python_files() -> list[Path]:
    roots = (ROOT / "audit_engine", ROOT / "tools", ROOT / "decision_memory")
    excluded = {".git", ".venv", "venv", "__pycache__", "build", "dist", "node_modules"}
    files = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if not any(part in excluded for part in path.parts):
                files.append(path)
    return sorted(set(files))


class CrossLayerProvenanceConsumerInventoryTests(unittest.TestCase):
    def test_no_uninventoried_production_import_or_reference_exists(self):
        expected_module = ROOT / PROVENANCE
        violations = []
        for path in _production_python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports_contract = False
            references_contract = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    imports_contract |= bool(
                        node.module
                        and node.module.endswith("cross_layer_snapshot_provenance")
                    )
                    imports_contract |= bool(
                        node.module
                        and node.module.endswith("epistemic")
                        and any(item.name in API_NAMES for item in node.names)
                    )
                elif isinstance(node, ast.Import):
                    imports_contract |= any(
                        alias.name.endswith("cross_layer_snapshot_provenance")
                        for alias in node.names
                    )
                if isinstance(node, ast.Name) and node.id in API_NAMES:
                    references_contract = True
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    references_contract |= (
                        node.value in ASSURANCE_TERMS
                        or node.value in API_NAMES
                    )
            if path not in (expected_module, ROOT / ORCHESTRATOR) and (imports_contract or references_contract):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            violations, [],
            "A production provenance consumer was added outside the M7.5.29 authorized package boundary",
        )
        tree = _parse(ORCHESTRATOR)
        provenance_imports = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "cross_layer_snapshot_provenance"
        ]
        self.assertEqual(
            {alias.name for node in provenance_imports for alias in node.names},
            API_NAMES,
        )
        for legacy_name in (
            "verify_persisted_cross_layer_obligation_composition",
            "_run_persisted_cross_layer_obligation_composition",
        ):
            function = next(
                node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == legacy_name
            )
            names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
            self.assertTrue(API_NAMES.isdisjoint(names), legacy_name)
        package_function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "verify_persisted_cross_layer_obligation_package"
        )
        package_names = {node.id for node in ast.walk(package_function) if isinstance(node, ast.Name)}
        self.assertIn("verify_cross_layer_snapshot_provenance", package_names)
        envelope_function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "verify_cross_layer_obligation_package_envelope"
        )
        envelope_names = {node.id for node in ast.walk(envelope_function) if isinstance(node, ast.Name)}
        self.assertIn("verify_cross_layer_snapshot_provenance_envelope", envelope_names)

    def test_known_adjacent_consumers_remain_independent(self):
        for relative_path in KNOWN_INDEPENDENT_CONSUMERS:
            with self.subTest(module=relative_path):
                tree = _parse(relative_path)
                imports = []
                references = []
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        rendered = ast.dump(node)
                        if "cross_layer_snapshot_provenance" in rendered:
                            imports.append(rendered)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        if node.value in ASSURANCE_TERMS or node.value in API_NAMES:
                            references.append(node.value)
                self.assertEqual(imports, [])
                self.assertEqual(references, [])

    def test_package_facade_does_not_export_provenance_as_a_general_gate(self):
        tree = _parse(PACKAGE_INIT)
        imported_modules = [
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        exported_names = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertNotIn("cross_layer_snapshot_provenance", imported_modules)
        self.assertTrue(API_NAMES.isdisjoint(exported_names))

    def test_legacy_orchestration_api_does_not_consume_or_promote_the_provenance_envelope(self):
        tree = _parse(ORCHESTRATOR)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "verify_persisted_cross_layer_obligation_composition"
        )
        argument_names = {arg.arg for arg in function.args.args + function.args.kwonlyargs}
        self.assertTrue(API_NAMES.isdisjoint(argument_names))
        self.assertNotIn("provenance_envelope", argument_names)
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        self.assertTrue(API_NAMES.isdisjoint(names))

    def test_envelope_checker_cannot_claim_source_state_replay_or_authorization(self):
        tree = _parse(PROVENANCE)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "verify_cross_layer_snapshot_provenance_envelope"
        )
        argument_names = {arg.arg for arg in function.args.args + function.args.kwonlyargs}
        self.assertEqual(argument_names, {"envelope"})
        calls = {
            node.func.id for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("verify_verified_manifest_data", calls)
        self.assertNotIn("verify_cross_layer_snapshot_provenance", calls)
        constants = {
            node.value for node in ast.walk(function)
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, bool))
        }
        self.assertIn(False, constants)
        self.assertIn("NOT_EVALUATED", constants)
        self.assertIn("content_binding_verified", constants)
        self.assertIn("source_state_replay_performed", constants)
        self.assertIn("downstream_authorization", constants)

    def test_inventory_does_not_treat_content_seal_as_producer_authentication(self):
        tree = _parse(PROVENANCE)
        verifier = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "verify_cross_layer_snapshot_provenance"
        )
        source = ast.get_source_segment((ROOT / PROVENANCE).read_text(encoding="utf-8"), verifier)
        self.assertIsNotNone(source)
        self.assertIn('"trust_anchor": "NONE"', source)
        self.assertIn('"atomic_cross_store_snapshot": False', source)
        self.assertIn("do not authenticate artifact producers", source)


if __name__ == "__main__":
    unittest.main()

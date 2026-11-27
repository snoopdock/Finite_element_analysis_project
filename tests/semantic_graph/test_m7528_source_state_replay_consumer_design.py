"""M7.5.28 source-state replay consumer requirements/design tests.

These tests establish the feasibility and seal topology of the proposed
M7.5.24 package integration. They deliberately do not wire M7.5.26 into
production orchestration; that is a separately reviewed implementation step.
"""
from __future__ import annotations

import ast
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = Path("audit_engine/semantic_audit/epistemic/obligation_composition_orchestrator.py")
PROVENANCE = Path("audit_engine/semantic_audit/epistemic/cross_layer_snapshot_provenance.py")
SOURCE_MANIFEST = Path("tools/ae32c_source_snapshot_manifest.py")
GRAPH_WORKFLOW = Path(".github/workflows/ae32c_source_snapshot_manifest.yml")
DESIGN_DOC = Path("docs/audit-engine/AE-32C-M7.5.28-Source-State-Replay-Consumer-Requirements-and-Integration-Design.md")


def _tree(path: Path) -> ast.Module:
    return ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=str(path))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


class M7528SourceStateReplayConsumerDesignTests(unittest.TestCase):
    def test_persisted_orchestrator_has_the_complete_candidate_context(self):
        tree = _tree(ORCHESTRATOR)
        function = _function(tree, "verify_persisted_cross_layer_obligation_composition")
        args = {arg.arg for arg in function.args.args + function.args.kwonlyargs}
        required = {
            "source_manifest", "repository_root", "current_qualification",
            "current_observation_bundle", "execution_reconciliation_store",
            "qualification_reconciliation_store",
        }
        self.assertTrue(required.issubset(args))
        local_names = {
            node.id for node in ast.walk(function)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        }
        self.assertTrue({
            "execution_reconciliation", "qualification_reconciliation",
            "qualification_consumer_result", "composition", "payload",
        }.issubset(local_names))

    def test_m7526_verifier_accepts_the_exact_artifacts_available_at_composition(self):
        tree = _tree(PROVENANCE)
        function = _function(tree, "verify_cross_layer_snapshot_provenance")
        args = [arg.arg for arg in function.args.args]
        self.assertEqual(args, [
            "source_manifest", "execution_reconciliation",
            "qualification_reconciliation", "qualification",
            "observation_bundle",
        ] + ["orchestration_result"])
        kwonly = {arg.arg for arg in function.args.kwonlyargs}
        self.assertTrue({"repository_root", "expected_source_revision"}.issubset(kwonly))

    def test_proposed_package_seal_topology_is_acyclic_and_tamper_evident(self):
        orchestration_core = {
            "schema": "ae32c/orchestrated-persisted-obligation-composition/v1",
            "execution_reconciliation_sha256": "a" * 64,
            "qualification_reconciliation_sha256": "b" * 64,
            "authority": {"downstream_authorization": "NOT_EVALUATED"},
        }
        orchestration = {
            **orchestration_core,
            "orchestration_sha256": _digest(orchestration_core),
        }
        provenance_payload = {
            "schema": "ae32c/cross-layer-snapshot-provenance/v1",
            "orchestration_sha256": orchestration["orchestration_sha256"],
            "snapshot_identity_assurance": "SOURCE_STATE_REPLAY_VERIFIED",
            "atomic_cross_store_snapshot": False,
            "trust_anchor": "NONE",
        }
        provenance = {
            **provenance_payload,
            "cross_layer_snapshot_identity_sha256": _digest(provenance_payload),
        }
        package_payload = {
            "schema": "ae32c/cross-layer-obligation-package/v1",
            "orchestration": orchestration,
            "provenance": provenance,
        }
        package = {**package_payload, "package_sha256": _digest(package_payload)}

        self.assertEqual(
            orchestration["orchestration_sha256"],
            _digest({k: v for k, v in orchestration.items() if k != "orchestration_sha256"}),
        )
        self.assertEqual(
            provenance["cross_layer_snapshot_identity_sha256"],
            _digest({k: v for k, v in provenance.items()
                     if k != "cross_layer_snapshot_identity_sha256"}),
        )
        self.assertEqual(
            package["package_sha256"],
            _digest({k: v for k, v in package.items() if k != "package_sha256"}),
        )
        changed = dict(package, provenance={**provenance, "trust_anchor": "EXTERNAL"})
        self.assertNotEqual(
            changed["package_sha256"],
            _digest({k: v for k, v in changed.items() if k != "package_sha256"}),
        )
        self.assertNotIn("package_sha256", provenance)
        self.assertNotIn("package_sha256", orchestration)

    def test_full_verifier_has_no_declared_only_fallback_when_repository_root_is_supplied(self):
        tree = _tree(PROVENANCE)
        function = _function(tree, "verify_cross_layer_snapshot_provenance")
        source = ast.get_source_segment((ROOT / PROVENANCE).read_text(encoding="utf-8"), function)
        self.assertIn("if repository_root is not None:", source)
        self.assertIn("verify_verified_manifest_data(", source)
        self.assertIn('assurance_level = "SOURCE_STATE_REPLAY_VERIFIED"', source)
        self.assertIn('raise CrossLayerSnapshotProvenanceError("source_state_replay_failed:', source)

    def test_source_manifest_replay_is_non_mutating_and_binds_checkout_state(self):
        tree = _tree(SOURCE_MANIFEST)
        function = _function(tree, "verify_verified_manifest_data")
        source = ast.get_source_segment((ROOT / SOURCE_MANIFEST).read_text(encoding="utf-8"), function)
        self.assertIn("expected_source_revision or source.get(\"commit_oid\")", source)
        self.assertIn('snapshot.get("source_inventory") != inventory', source)
        self.assertIn('"source_state_replay_verified": True', source)
        self.assertIn('"worktree_clean_at_replay": True', source)
        self.assertNotIn("_atomic_write(", source)

    def test_graph_snapshot_pipeline_already_performs_pre_and_post_source_verification(self):
        workflow = (ROOT / GRAPH_WORKFLOW).read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("tools/ae32c_source_snapshot_manifest.py verify"), 2)
        self.assertIn("Verify source identity before graph projection", workflow)
        self.assertIn("Verify source identity after graph projection", workflow)
        self.assertNotIn("cross_layer_snapshot_provenance", workflow)

    def test_existing_m7524_contract_remains_unmodified_until_separate_integration(self):
        tree = _tree(ORCHESTRATOR)
        imports = [
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        self.assertNotIn(
            "audit_engine.semantic_audit.epistemic.cross_layer_snapshot_provenance",
            imports,
        )
        self.assertNotIn("verify_cross_layer_snapshot_provenance", {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        })

    def test_design_document_records_non_authority_and_versioned_package_boundary(self):
        doc = (ROOT / DESIGN_DOC).read_text(encoding="utf-8")
        for phrase in (
            "M7.5.24 persisted cross-layer obligation orchestrator",
            "cross-layer-obligation-package/v1",
            "SOURCE_STATE_REPLAY_VERIFIED",
            "DECLARED_ONLY",
            "atomic_cross_store_snapshot = false",
            "trust_anchor = NONE",
            "does not authorize",
            "M7.5.29",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, doc)


if __name__ == "__main__":
    unittest.main()

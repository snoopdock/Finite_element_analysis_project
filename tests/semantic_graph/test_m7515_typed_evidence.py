"""M7.5.15 typed structural evidence observation tests."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    AssuranceClaim, AssuranceStore, CoverageDossierStore, EpistemicStore,
    CoverageObligation, ObligationDisposition, build_and_persist_coverage_dossier,
    build_rule_derived_coverage_manifest, derive_rule_coverage_plan,
    build_and_persist_execution_obligation_reconciliation,
    ExecutionObligationReconciliationStore,
)
from audit_engine.semantic_audit.epistemic.source_inventory import build_source_extractor_inventory
from audit_engine.semantic_audit.epistemic.extractor_execution import build_extractor_execution_report
from audit_engine.semantic_audit.epistemic.typed_evidence import (
    TypedEvidenceError, TypedEvidenceObservationStore,
    derive_typed_evidence_observations, verify_typed_evidence_observation_bundle,
    build_and_persist_typed_evidence_observations,
)


def seal(value):
    return hashlib.sha256((json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode()).hexdigest()


def source_manifest(root, files):
    entries = []
    for path, raw in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        entries.append({"path":path,"mode":"100644","object_type":"blob",
                        "content_sha256":hashlib.sha256(raw).hexdigest()})
    entries.sort(key=lambda x:x["path"].encode())
    inventory = {"schema":"ae32c/source-inventory/v1","entry_count":len(entries),
                 "entries":entries,"sha256":seal(entries)}
    manifest = {"manifest_schema":"ae32c/source-snapshot-manifest/v1","status":"VERIFIED",
                "source_snapshot_id":"snapshot:m7515","source":{"commit_oid":"b"*40},
                "source_inventory":inventory,"verification":{"status":"VERIFIED"},
                "authority":{"atomic_repository_snapshot_established":False}}
    manifest["manifest_sha256"] = seal(manifest)
    return manifest


class TypedEvidenceObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.files = {
            "src/graph.py": b"import networkx as nx\n",
            "src/plain.py": b"import os\n",
            "src/broken.py": b"def broken(:\n",
        }
        self.source = source_manifest(self.root, self.files)
        self.inventory = build_source_extractor_inventory(self.source)
        self.execution = build_extractor_execution_report(self.source,self.inventory,self.root)
        self.claim = AssuranceClaim("claim:m7515","prop:m7515","repository","scope:repo",
                                    "snapshot:m7515","typed evidence test")
        self.plan = derive_rule_coverage_plan(
            self.claim, source_snapshot_id="snapshot:m7515", graph_snapshot_id="graph:m7515",
            rule_ids=("AE32A-GRAPH-SERVICE-UNUSED","AE32A-INCOMPLETE-PYTHON-SCAN",
                      "AE32A-AE28-EXTERNAL-MODEL-INPUT"))
        self.manifest = build_rule_derived_coverage_manifest(
            self.claim,self.plan,
            assessments={oid:CoverageObligation(oid,ObligationDisposition.UNKNOWN,
                limitation="structural observations are not semantic acceptance")
                for oid in self.plan.expected_obligation_ids})
        self.assurance = AssuranceStore(self.root/"assurance.sqlite")
        self.epistemic = EpistemicStore(self.root/"epistemic.sqlite")
        self.dossiers = CoverageDossierStore(self.root/"dossiers.sqlite")
        self.reconciliation_store = ExecutionObligationReconciliationStore(
            self.root/"execution-reconciliation.sqlite")
        self.observation_store = TypedEvidenceObservationStore(self.root/"typed-evidence.sqlite")
        self.assurance.record(self.claim)
        build_and_persist_coverage_dossier(
            dossier_id="dossier:m7515",claim=self.claim,plan=self.plan,manifest=self.manifest,
            gap_to_obligations={},captured_at="2026-11-27T00:00:00Z",
            assurance_store=self.assurance,epistemic_store=self.epistemic,
            dossier_store=self.dossiers)
        self.execution_reconciliation = build_and_persist_execution_obligation_reconciliation(
            reconciliation_store=self.reconciliation_store,dossier_id="dossier:m7515",
            claim=self.claim,plan=self.plan,manifest=self.manifest,
            source_manifest=self.source,inventory=self.inventory,
            execution_report=self.execution,repository_root=self.root,
            assurance_store=self.assurance,epistemic_store=self.epistemic,
            dossier_store=self.dossiers)

    def tearDown(self):
        self.observation_store.close()
        self.reconciliation_store.close()
        self.dossiers.close()
        self.assurance.close()
        self.epistemic.close()
        self.tmp.cleanup()

    def test_graph_import_is_exact_source_bound_observation_not_rule_satisfaction(self):
        bundle = derive_typed_evidence_observations(
            plan=self.plan,inventory=self.inventory,execution_report=self.execution,
            repository_root=self.root)
        graph = [x for x in bundle["observations"] if x["evidence_kind"]=="graph_import"]
        self.assertEqual(len(graph),1)
        self.assertEqual(graph[0]["source_path"],"src/graph.py")
        self.assertEqual(graph[0]["source_line"],1)
        self.assertEqual(graph[0]["structural_value"]["module"],"networkx")
        self.assertEqual(graph[0]["semantic_acceptance"],"NOT_ESTABLISHED")
        self.assertEqual(graph[0]["status"],"STRUCTURALLY_OBSERVED")
        self.assertFalse(bundle["authority"]["rule_obligations_satisfied"])

    def test_syntax_error_is_bound_to_failed_ast_outcome(self):
        bundle = derive_typed_evidence_observations(
            plan=self.plan,inventory=self.inventory,execution_report=self.execution,
            repository_root=self.root)
        errors = [x for x in bundle["observations"] if x["evidence_kind"]=="python_syntax_error"]
        self.assertEqual(len(errors),1)
        self.assertEqual(errors[0]["source_path"],"src/broken.py")
        self.assertEqual(errors[0]["observation_type"],"python_ast_parse_failure")
        self.assertEqual(errors[0]["structural_value"]["diagnostic_code"],"source_parse_failed")

    def test_unsupported_semantic_kind_remains_explicitly_unresolved(self):
        bundle = derive_typed_evidence_observations(
            plan=self.plan,inventory=self.inventory,execution_report=self.execution,
            repository_root=self.root)
        unresolved = {x["evidence_kind"]:x for x in bundle["unresolved_evidence_kinds"]}
        self.assertEqual(unresolved["external_model_response_intake"]["status"],
                         "NO_AUTOMATIC_VALIDATOR")
        self.assertEqual(bundle["summary"]["semantic_evidence_accepted_count"],0)

    def test_exact_replay_and_source_drift_rejection(self):
        bundle = derive_typed_evidence_observations(
            plan=self.plan,inventory=self.inventory,execution_report=self.execution,
            repository_root=self.root)
        replay = verify_typed_evidence_observation_bundle(
            bundle,plan=self.plan,source_manifest=self.source,inventory=self.inventory,
            execution_report=self.execution,repository_root=self.root)
        self.assertTrue(replay["semantic_replay"])
        (self.root/"src/graph.py").write_text("import os\n")
        with self.assertRaises(TypedEvidenceError):
            verify_typed_evidence_observation_bundle(
                bundle,plan=self.plan,source_manifest=self.source,inventory=self.inventory,
                execution_report=self.execution,repository_root=self.root)

    def test_bundle_digest_tampering_rejected(self):
        bundle = derive_typed_evidence_observations(
            plan=self.plan,inventory=self.inventory,execution_report=self.execution,
            repository_root=self.root)
        bundle["summary"]["semantic_evidence_accepted_count"] = 4
        with self.assertRaisesRegex(TypedEvidenceError,"bundle_digest_mismatch"):
            verify_typed_evidence_observation_bundle(
                bundle,plan=self.plan,source_manifest=self.source,inventory=self.inventory,
                execution_report=self.execution,repository_root=self.root)

    def test_persistence_requires_independently_replayed_m7514_reconciliation(self):
        bundle = build_and_persist_typed_evidence_observations(
            store=self.observation_store,plan=self.plan,claim=self.claim,manifest=self.manifest,
            source_manifest=self.source,inventory=self.inventory,
            execution_report=self.execution,dossier_id="dossier:m7515",
            reconciliation_id=self.execution_reconciliation["reconciliation_sha256"],
            reconciliation_store=self.reconciliation_store,
            assurance_store=self.assurance,epistemic_store=self.epistemic,
            dossier_store=self.dossiers,repository_root=self.root)
        self.assertEqual(self.observation_store.get(bundle["bundle_sha256"]),bundle)
        self.assertEqual(bundle["summary"]["semantic_evidence_accepted_count"],0)

    def test_fabricated_or_missing_execution_reconciliation_is_rejected(self):
        with self.assertRaises(TypedEvidenceError):
            build_and_persist_typed_evidence_observations(
                store=self.observation_store,plan=self.plan,claim=self.claim,manifest=self.manifest,
                source_manifest=self.source,inventory=self.inventory,
                execution_report=self.execution,dossier_id="dossier:m7515",
                reconciliation_id="forged-reconciliation",
                reconciliation_store=self.reconciliation_store,
                assurance_store=self.assurance,epistemic_store=self.epistemic,
                dossier_store=self.dossiers,repository_root=self.root)
        self.assertEqual(self.observation_store.history(),())

    def test_ledger_idempotence_immutability_and_restart(self):
        bundle = derive_typed_evidence_observations(
            plan=self.plan,inventory=self.inventory,execution_report=self.execution,
            repository_root=self.root)
        db = self.root/"typed.sqlite"
        store = TypedEvidenceObservationStore(db)
        self.assertTrue(store.record(bundle))
        self.assertFalse(store.record(bundle))
        with self.assertRaises(sqlite3.IntegrityError):
            store._db.execute("DELETE FROM typed_evidence_events")
        store.close()
        store = TypedEvidenceObservationStore(db)
        self.assertTrue(store.verify_integrity())
        self.assertEqual(store.get(bundle["bundle_sha256"]),bundle)
        store.close()


if __name__ == "__main__":
    unittest.main()

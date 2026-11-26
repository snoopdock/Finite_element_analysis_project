"""M7.5.15 typed structural evidence observation tests."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    AssuranceClaim, CoverageObligation, ObligationDisposition,
    build_rule_derived_coverage_manifest, derive_rule_coverage_plan,
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

    def tearDown(self):
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
            bundle,plan=self.plan,inventory=self.inventory,
            execution_report=self.execution,repository_root=self.root)
        self.assertTrue(replay["semantic_replay"])
        (self.root/"src/graph.py").write_text("import os\n")
        with self.assertRaises(TypedEvidenceError):
            verify_typed_evidence_observation_bundle(
                bundle,plan=self.plan,inventory=self.inventory,
                execution_report=self.execution,repository_root=self.root)

    def test_bundle_digest_tampering_rejected(self):
        bundle = derive_typed_evidence_observations(
            plan=self.plan,inventory=self.inventory,execution_report=self.execution,
            repository_root=self.root)
        bundle["summary"]["semantic_evidence_accepted_count"] = 4
        with self.assertRaisesRegex(TypedEvidenceError,"bundle_digest_mismatch"):
            verify_typed_evidence_observation_bundle(
                bundle,plan=self.plan,inventory=self.inventory,
                execution_report=self.execution,repository_root=self.root)

    def test_persistence_requires_matching_m7514_execution_reconciliation(self):
        payload = {
            "schema":"ae32c/execution-obligation-reconciliation/v1",
            "source_snapshot_id":self.plan.source_snapshot_id,
            "plan_sha256":self.plan.plan_sha256,
            "execution_report_sha256":self.execution["report_sha256"],
            "authority":{"extractor_execution_reconciled_to_declared_obligations":True},
            "obligations":[{"obligation_id":oid} for oid in self.plan.expected_obligation_ids],
        }
        reconciliation = {**payload,"reconciliation_sha256":seal(payload)}
        store = TypedEvidenceObservationStore(self.root/"integrated.sqlite")
        try:
            bundle = build_and_persist_typed_evidence_observations(
                store=store,plan=self.plan,claim=self.claim,manifest=self.manifest,
                source_manifest=self.source,inventory=self.inventory,
                execution_report=self.execution,execution_reconciliation=reconciliation,
                repository_root=self.root)
            self.assertEqual(store.get(bundle["bundle_sha256"]),bundle)
            self.assertEqual(bundle["summary"]["semantic_evidence_accepted_count"],0)
        finally:
            store.close()

    def test_wrong_execution_reconciliation_is_rejected(self):
        payload = {
            "schema":"ae32c/execution-obligation-reconciliation/v1",
            "source_snapshot_id":"another-snapshot",
            "plan_sha256":self.plan.plan_sha256,
            "execution_report_sha256":self.execution["report_sha256"],
            "authority":{"extractor_execution_reconciled_to_declared_obligations":True},
            "obligations":[{"obligation_id":oid} for oid in self.plan.expected_obligation_ids],
        }
        reconciliation = {**payload,"reconciliation_sha256":seal(payload)}
        store = TypedEvidenceObservationStore(self.root/"rejected.sqlite")
        try:
            with self.assertRaisesRegex(TypedEvidenceError,"execution_reconciliation_binding_mismatch"):
                build_and_persist_typed_evidence_observations(
                    store=store,plan=self.plan,claim=self.claim,manifest=self.manifest,
                    source_manifest=self.source,inventory=self.inventory,
                    execution_report=self.execution,execution_reconciliation=reconciliation,
                    repository_root=self.root)
            self.assertEqual(store.history(),())
        finally:
            store.close()

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

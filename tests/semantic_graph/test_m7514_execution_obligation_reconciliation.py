"""M7.5.14 structural and behavioral tests."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    AssuranceClaim, AssuranceStore, CoverageDossierStore, CoverageObligation,
    EpistemicStore, ObligationDisposition, build_rule_derived_coverage_manifest,
    derive_rule_coverage_plan, build_and_persist_coverage_dossier,
)
from audit_engine.semantic_audit.epistemic.extractor_execution import (
    build_extractor_execution_report,
)
from audit_engine.semantic_audit.epistemic.source_inventory import build_source_extractor_inventory
from audit_engine.semantic_audit.epistemic.execution_obligation_reconciliation import (
    ExecutionObligationReconciliationError, ExecutionObligationReconciliationStore,
    build_and_persist_execution_obligation_reconciliation,
    verify_execution_obligation_reconciliation,
)


def seal(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()).hexdigest()


def source_manifest(entries):
    entries = sorted(entries, key=lambda x: x["path"].encode())
    inv = {"schema":"ae32c/source-inventory/v1","entry_count":len(entries),"entries":entries,"sha256":seal(entries)}
    x = {"manifest_schema":"ae32c/source-snapshot-manifest/v1","status":"VERIFIED",
         "source_snapshot_id":"snapshot:m7514","source":{"commit_oid":"a"*40},
         "source_inventory":inv,"verification":{"status":"VERIFIED"},
         "authority":{"atomic_repository_snapshot_established":False}}
    x["manifest_sha256"] = seal(x)
    return x


class ExecutionObligationReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.py = b"import os\nos.getenv('MODEL_URL')\n"
        (self.root/"src").mkdir()
        (self.root/"src/app.py").write_bytes(self.py)
        self.source = source_manifest([{"path":"src/app.py","mode":"100644","object_type":"blob",
                                        "content_sha256":hashlib.sha256(self.py).hexdigest()}])
        self.inventory = build_source_extractor_inventory(self.source)
        self.execution = build_extractor_execution_report(self.source,self.inventory,self.root)
        self.assurance = AssuranceStore(self.root/"assurance.sqlite")
        self.epistemic = EpistemicStore(self.root/"epistemic.sqlite")
        self.dossiers = CoverageDossierStore(self.root/"dossiers.sqlite")
        self.reconciliations = ExecutionObligationReconciliationStore(self.root/"reconciliations.sqlite")
        self.claim = AssuranceClaim("claim:m7514","prop:m7514","repository","scope:repo",
                                    "snapshot:m7514","M7.5.14 test claim")
        self.assurance.record(self.claim)
        self.plan = derive_rule_coverage_plan(self.claim,source_snapshot_id="snapshot:m7514",
                    graph_snapshot_id="graph:m7514",rule_ids=("AE32A-AE28-EXTERNAL-MODEL-INPUT",))
        self.manifest = build_rule_derived_coverage_manifest(
            self.claim,self.plan,
            assessments={self.plan.expected_obligation_ids[0]:CoverageObligation(
                self.plan.expected_obligation_ids[0],ObligationDisposition.UNKNOWN,
                limitation="typed evidence not yet supplied")})
        self.dossier = build_and_persist_coverage_dossier(
            dossier_id="dossier:m7514",claim=self.claim,plan=self.plan,manifest=self.manifest,
            gap_to_obligations={},captured_at="2026-11-27T00:00:00Z",
            assurance_store=self.assurance,epistemic_store=self.epistemic,dossier_store=self.dossiers)

    def tearDown(self):
        self.reconciliations.close()
        self.dossiers.close()
        self.assurance.close()
        self.epistemic.close()
        self.tmp.cleanup()

    def kwargs(self):
        return dict(dossier_id="dossier:m7514",claim=self.claim,plan=self.plan,manifest=self.manifest,
                    source_manifest=self.source,inventory=self.inventory,execution_report=self.execution,
                    repository_root=self.root,assurance_store=self.assurance,
                    epistemic_store=self.epistemic,dossier_store=self.dossiers)

    def test_execution_coverage_is_distinct_from_typed_evidence(self):
        report = build_and_persist_execution_obligation_reconciliation(
            reconciliation_store=self.reconciliations,**self.kwargs())
        by_id = {x["obligation_id"]:x for x in report["obligations"]}
        evidence = next(x for x in by_id.values() if x["kind"]=="typed_evidence")
        coverage = next(x for x in by_id.values() if x["kind"]=="extractor_coverage")
        self.assertEqual(evidence["status"],"UNKNOWN")
        self.assertEqual(evidence["reason"],"extractor_output_is_not_typed_semantic_evidence")
        self.assertEqual(coverage["status"],"EXTRACTOR_EXECUTION_COMPLETE")
        self.assertFalse(report["summary"]["epistemic_coverage_upgraded"])
        self.assertFalse(report["summary"]["coverage_dossier_mutated"])

    def test_replay_rederives_entire_reconciliation(self):
        report = build_and_persist_execution_obligation_reconciliation(
            reconciliation_store=self.reconciliations,**self.kwargs())
        result = verify_execution_obligation_reconciliation(
            report["reconciliation_sha256"],reconciliation_store=self.reconciliations,**self.kwargs())
        self.assertTrue(result["semantic_replay"])
        self.assertTrue(result["dossier_unchanged"])

    def test_changed_source_invalidates_attachment(self):
        (self.root/"src/app.py").write_bytes(b"print('changed')\n")
        with self.assertRaisesRegex(ExecutionObligationReconciliationError,"upstream_execution_evidence_verification_failed"):
            build_and_persist_execution_obligation_reconciliation(
                reconciliation_store=self.reconciliations,**self.kwargs())

    def test_missing_dossier_rejected(self):
        args=self.kwargs(); args["dossier_id"]="missing"
        with self.assertRaisesRegex(ExecutionObligationReconciliationError,"coverage_dossier_not_found"):
            from audit_engine.semantic_audit.epistemic.execution_obligation_reconciliation import build_execution_obligation_reconciliation
            build_execution_obligation_reconciliation(**args)

    def test_tampered_persisted_reconciliation_rejected(self):
        report = build_and_persist_execution_obligation_reconciliation(
            reconciliation_store=self.reconciliations,**self.kwargs())
        self.reconciliations.close()
        raw=sqlite3.connect(self.root/"reconciliations.sqlite")
        raw.execute("DROP TRIGGER execution_obligation_no_update")
        row=raw.execute("SELECT sequence,reconciliation_id,payload,previous_hash FROM execution_obligation_events").fetchone()
        payload=json.loads(row[2]); payload["summary"]["epistemic_coverage_upgraded"]=True
        replacement=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False)
        ph=hashlib.sha256(replacement.encode()).hexdigest()
        eh=hashlib.sha256(f"{row[0]}\n{row[1]}\n{ph}\n{row[3]}".encode()).hexdigest()
        raw.execute("UPDATE execution_obligation_events SET payload=?,payload_sha256=?,event_hash=?",(replacement,ph,eh))
        raw.commit(); raw.close()
        self.reconciliations=ExecutionObligationReconciliationStore(self.root/"reconciliations.sqlite")
        with self.assertRaisesRegex(ExecutionObligationReconciliationError,"ledger_integrity_failure"):
            self.reconciliations.get(report["reconciliation_sha256"])

    def test_dossier_manifest_mismatch_rejected(self):
        from dataclasses import replace
        wrong = replace(self.manifest, manifest_id="different")
        args=self.kwargs(); args["manifest"]=wrong
        with self.assertRaisesRegex(ExecutionObligationReconciliationError,"coverage_dossier_manifest_mismatch"):
            from audit_engine.semantic_audit.epistemic.execution_obligation_reconciliation import build_execution_obligation_reconciliation
            build_execution_obligation_reconciliation(**args)


if __name__ == "__main__":
    unittest.main()

"""M7.5.17 qualification-to-obligation reconciliation tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    AssuranceClaim, CoverageObligation, ObligationDisposition,
    derive_rule_coverage_plan, build_rule_derived_coverage_manifest,
)
from audit_engine.semantic_audit.epistemic.semantic_qualification import (
    qualify_typed_evidence_observations,
)
from audit_engine.semantic_audit.epistemic.qualification_reconciliation import (
    QualificationReconciliationError,
    qualification_aggregation_policy_registry,
    reconcile_semantic_qualifications,
    verify_qualification_obligation_reconciliation,
)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def observation(source_id, path, raw, kind, obligation, observation_type, structural):
    lines = raw.splitlines()
    payload = {
        "schema": "ae32c/typed-evidence-observation/v1",
        "source_snapshot_id": source_id,
        "rule_obligation_ids": [obligation],
        "evidence_kind": kind,
        "producer_id": "test-fixture",
        "producer_version": "1.0.0",
        "extractor_id": "python_ast",
        "extractor_version": "1.0.0",
        "candidate_id": "candidate:" + path,
        "outcome_id": "outcome:" + path,
        "source_path": path,
        "source_content_sha256": hashlib.sha256(raw).hexdigest(),
        "source_line": 1,
        "source_line_sha256": hashlib.sha256(lines[0]).hexdigest(),
        "observation_type": observation_type,
        "structural_value": structural,
        "status": "STRUCTURALLY_OBSERVED",
        "semantic_acceptance": "NOT_ESTABLISHED",
        "limitation": "fixture structural observation",
    }
    return {**payload, "evidence_observation_id": digest(payload)}


class QualificationReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source_id = "snapshot:m7517"
        self.files = {
            "src/broken_a.py": b"def broken(:\n",
            "src/broken_b.py": b"def also_broken(:\n",
            "src/graph.py": b"import networkx as nx\n",
            "src/external.py": b"response = 'untrusted'\n",
        }
        entries = []
        for path, raw in self.files.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            entries.append({
                "path": path, "content_sha256": hashlib.sha256(raw).hexdigest(),
                "mode": "100644", "object_type": "blob",
            })
        entries.sort(key=lambda item: item["path"])
        inventory = {"entries": entries, "entry_count": len(entries)}
        inventory["sha256"] = digest(entries)
        self.source_manifest = {
            "manifest_schema": "ae32c/source-snapshot-manifest/v1",
            "source_snapshot_id": self.source_id,
            "source_inventory": inventory,
        }
        self.source_manifest["manifest_sha256"] = digest(self.source_manifest)
        self.claim = AssuranceClaim(
            "claim:m7517", "prop:m7517", "repository", "scope:repo",
            self.source_id, "M7.5.17 reconciliation test")
        self.plan = derive_rule_coverage_plan(
            self.claim, source_snapshot_id=self.source_id, graph_snapshot_id="graph:m7517",
            rule_ids=("AE32A-GRAPH-SERVICE-UNUSED", "AE32A-INCOMPLETE-PYTHON-SCAN",
                      "AE32A-AE28-EXTERNAL-MODEL-INPUT"))
        self.coverage_manifest = build_rule_derived_coverage_manifest(
            self.claim, self.plan, assessments={
                oid: CoverageObligation(oid, ObligationDisposition.UNKNOWN,
                                        limitation="M7.5.17 fixture")
                for oid in self.plan.expected_obligation_ids})

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self, observations):
        payload = {
            "schema": "ae32c/typed-evidence-observation-bundle/v1",
            "source_snapshot_id": self.source_id,
            "plan_sha256": self.plan.plan_sha256,
            "inventory_sha256": "b" * 64,
            "execution_report_sha256": "c" * 64,
            "observation_count": len(observations),
            "observations": observations,
            "unresolved_evidence_kinds": [],
            "summary": {"semantic_evidence_accepted_count": 0},
            "authority": {"proposition_truth_established": False},
        }
        return {**payload, "bundle_sha256": digest(payload)}

    def qualification(self, observations, defeaters=()):
        bundle = self.bundle(observations)
        result = qualify_typed_evidence_observations(
            bundle, claim=self.claim, plan=self.plan,
            coverage_manifest=self.coverage_manifest,
            source_manifest=self.source_manifest, repository_root=self.root,
            defeaters=defeaters)
        return bundle, result

    def reconcile(self, bundle, qualification, defeaters=()):
        return reconcile_semantic_qualifications(
            qualification, bundle, claim=self.claim, plan=self.plan,
            coverage_manifest=self.coverage_manifest,
            source_manifest=self.source_manifest, repository_root=self.root,
            defeaters=defeaters)

    def find(self, result, rule_id, evidence_kind):
        obligation_id = f"rule:{rule_id}:evidence:{evidence_kind}"
        return next(row for row in result["obligation_reconciliations"]
                    if row["obligation_id"] == obligation_id)

    def syntax_observation(self, path):
        return observation(
            self.source_id, path, self.files[path], "python_syntax_error",
            "rule:AE32A-INCOMPLETE-PYTHON-SCAN:evidence:python_syntax_error",
            "python_ast_parse_failure",
            {"exception_type": "SyntaxError", "diagnostic_code": "source_parse_failed",
             "message": "invalid syntax"})

    def test_policy_registry_is_versioned_and_digest_bound(self):
        registry = qualification_aggregation_policy_registry()
        self.assertEqual(registry["schema"], "ae32c/qualification-aggregation-policy-registry/v1")
        self.assertEqual(registry["registry_sha256"], digest({
            "schema": registry["schema"], "policies": registry["policies"]}))
        self.assertIn("CONTESTED_THEN_UNKNOWN", next(iter(registry["policies"].values()))["aggregation"])

    def test_one_supported_observation_reconciles_narrowly(self):
        bundle, qualification = self.qualification([self.syntax_observation("src/broken_a.py")])
        result = self.reconcile(bundle, qualification)
        row = self.find(result, "AE32A-INCOMPLETE-PYTHON-SCAN", "python_syntax_error")
        self.assertEqual(row["disposition"], "SUPPORTED_WITHIN_CONTRACT")
        self.assertEqual(row["observation_count"], 1)
        self.assertFalse(result["authority"]["proposition_truth_established"])
        self.assertFalse(result["authority"]["epistemic_coverage_manifest_mutated"])

    def test_multiple_supported_observations_are_retained_and_reconciled(self):
        bundle, qualification = self.qualification([
            self.syntax_observation("src/broken_a.py"),
            self.syntax_observation("src/broken_b.py"),
        ])
        result = self.reconcile(bundle, qualification)
        row = self.find(result, "AE32A-INCOMPLETE-PYTHON-SCAN", "python_syntax_error")
        self.assertEqual(row["disposition"], "SUPPORTED_WITHIN_CONTRACT")
        self.assertEqual(row["observation_count"], 2)
        self.assertEqual(len(row["supported_observation_ids"]), 2)

    def test_any_unresolved_defeater_makes_aggregate_contested(self):
        obs_a = self.syntax_observation("src/broken_a.py")
        obs_b = self.syntax_observation("src/broken_b.py")
        raw = self.files["src/broken_b.py"]
        defeater = {
            "target_observation_id": obs_b["evidence_observation_id"],
            "source_snapshot_id": self.source_id,
            "source_path": "src/broken_b.py",
            "source_content_sha256": hashlib.sha256(raw).hexdigest(),
            "source_line": 1,
            "source_line_sha256": hashlib.sha256(raw.splitlines()[0]).hexdigest(),
            "reason": "Independent counterclaim awaiting semantic validation",
        }
        bundle, qualification = self.qualification([obs_a, obs_b], (defeater,))
        result = self.reconcile(bundle, qualification, (defeater,))
        row = self.find(result, "AE32A-INCOMPLETE-PYTHON-SCAN", "python_syntax_error")
        self.assertEqual(row["disposition"], "CONTESTED")
        self.assertEqual(len(row["supported_observation_ids"]), 1)
        self.assertEqual(len(row["contested_observation_ids"]), 1)

    def test_missing_qualification_is_unknown_not_negative(self):
        bundle, qualification = self.qualification([])
        result = self.reconcile(bundle, qualification)
        row = self.find(result, "AE32A-INCOMPLETE-PYTHON-SCAN", "python_syntax_error")
        self.assertEqual(row["disposition"], "UNKNOWN")
        self.assertEqual(row["reason"], "no_qualification_record_for_expected_evidence_obligation")

    def test_unsupported_evidence_remains_unknown(self):
        obs = observation(
            self.source_id, "src/external.py", self.files["src/external.py"],
            "external_model_response_intake",
            "rule:AE32A-AE28-EXTERNAL-MODEL-INPUT:evidence:external_model_response_intake",
            "unvalidated_external_model_response", {"response": "untrusted"})
        bundle, qualification = self.qualification([obs])
        result = self.reconcile(bundle, qualification)
        row = self.find(result, "AE32A-AE28-EXTERNAL-MODEL-INPUT",
                        "external_model_response_intake")
        self.assertEqual(row["disposition"], "UNKNOWN")
        self.assertEqual(row["qualification_states"], ["UNKNOWN"])

    def test_graph_import_remains_insufficient(self):
        obs = observation(
            self.source_id, "src/graph.py", self.files["src/graph.py"], "graph_import",
            "rule:AE32A-GRAPH-SERVICE-UNUSED:evidence:graph_import",
            "python_import_statement",
            {"module": "networkx", "imported_symbols": [], "matched_module_root": "networkx"})
        bundle, qualification = self.qualification([obs])
        result = self.reconcile(bundle, qualification)
        row = self.find(result, "AE32A-GRAPH-SERVICE-UNUSED", "graph_import")
        self.assertEqual(row["disposition"], "INSUFFICIENT")

    def test_coverage_obligations_are_not_relabelled_as_semantic_evidence(self):
        bundle, qualification = self.qualification([])
        result = self.reconcile(bundle, qualification)
        coverage_rows = [row for row in result["obligation_reconciliations"]
                         if row.get("dimension") == "coverage"]
        self.assertTrue(coverage_rows)
        self.assertTrue(all(row["disposition"] == "NOT_IN_SCOPE" for row in coverage_rows))

    def test_reconciliation_replay_and_source_drift_rejection(self):
        bundle, qualification = self.qualification([self.syntax_observation("src/broken_a.py")])
        result = self.reconcile(bundle, qualification)
        replay = verify_qualification_obligation_reconciliation(
            result, qualification, bundle, claim=self.claim, plan=self.plan,
            coverage_manifest=self.coverage_manifest, source_manifest=self.source_manifest,
            repository_root=self.root)
        self.assertTrue(replay["semantic_replay"])
        (self.root / "src/broken_a.py").write_text("import os\n")
        with self.assertRaises(QualificationReconciliationError):
            verify_qualification_obligation_reconciliation(
                result, qualification, bundle, claim=self.claim, plan=self.plan,
                coverage_manifest=self.coverage_manifest, source_manifest=self.source_manifest,
                repository_root=self.root)

    def test_reconciliation_digest_tampering_rejected(self):
        bundle, qualification = self.qualification([self.syntax_observation("src/broken_a.py")])
        result = self.reconcile(bundle, qualification)
        result["summary"]["UNKNOWN"] = 0
        with self.assertRaisesRegex(QualificationReconciliationError,
                                    "reconciliation_digest_mismatch"):
            verify_qualification_obligation_reconciliation(
                result, qualification, bundle, claim=self.claim, plan=self.plan,
                coverage_manifest=self.coverage_manifest, source_manifest=self.source_manifest,
                repository_root=self.root)


if __name__ == "__main__":
    unittest.main()

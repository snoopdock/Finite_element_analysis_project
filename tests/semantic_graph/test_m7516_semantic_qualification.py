"""M7.5.16 rule-specific semantic evidence qualification tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (\n    AssuranceClaim, CoverageObligation, ObligationDisposition,\n    derive_rule_coverage_plan, build_rule_derived_coverage_manifest,\n)\nfrom audit_engine.semantic_audit.epistemic.semantic_qualification import (
    SemanticQualificationError,
    qualify_typed_evidence_observations,
    semantic_evidence_contract_registry,
    verify_semantic_evidence_qualification,
)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def observation(source_id, path, raw, kind, line, obligation, observation_type, structural):
    lines = raw.splitlines()
    payload = {
        "schema": "ae32c/typed-evidence-observation/v1",
        "source_snapshot_id": source_id,
        "rule_obligation_ids": [obligation],
        "evidence_kind": kind,
        "producer_id": "test-fixture",
        "producer_version": "1.0.0",
        "extractor_id": "python_ast" if kind != "scope_exclusion" else None,
        "extractor_version": "1.0.0" if kind != "scope_exclusion" else None,
        "candidate_id": "candidate:test" if kind != "scope_exclusion" else None,
        "outcome_id": "outcome:test" if kind != "scope_exclusion" else None,
        "source_path": path,
        "source_content_sha256": hashlib.sha256(raw).hexdigest(),
        "source_line": line,
        "source_line_sha256": hashlib.sha256(lines[line - 1]).hexdigest() if line else None,
        "observation_type": observation_type,
        "structural_value": structural,
        "status": "STRUCTURALLY_OBSERVED",
        "semantic_acceptance": "NOT_ESTABLISHED",
        "limitation": "fixture structural observation",
    }
    return {**payload, "evidence_observation_id": digest(payload)}


class SemanticQualificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source_id = "snapshot:m7516"
        self.files = {
            "src/graph.py": b"import networkx as nx\n",
            "src/broken.py": b"def broken(:\n",
            "src/excluded.py": b"print('excluded')\n",
        }
        entries = []
        for path, raw in self.files.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            entries.append({"path": path, "content_sha256": hashlib.sha256(raw).hexdigest(),
                            "mode": "100644", "object_type": "blob"})
        entries.sort(key=lambda x: x["path"])
        inventory = {"entries": entries, "entry_count": len(entries)}
        inventory["sha256"] = digest(entries)
        self.manifest = {
            "manifest_schema": "ae32c/source-snapshot-manifest/v1",
            "source_snapshot_id": self.source_id,
            "source_inventory": inventory,
        }
        self.manifest["manifest_sha256"] = digest(self.manifest)\n        self.claim = AssuranceClaim("claim:m7516", "prop:m7516", "repository",\n                                    "scope:repo", self.source_id, "M7.5.16 qualification test")\n        self.plan = derive_rule_coverage_plan(\n            self.claim, source_snapshot_id=self.source_id, graph_snapshot_id="graph:m7516",\n            rule_ids=("AE32A-GRAPH-SERVICE-UNUSED", "AE32A-INCOMPLETE-PYTHON-SCAN",\n                      "AE32A-SCOPE-EXCLUSIONS", "AE32A-AE28-EXTERNAL-MODEL-INPUT"))\n        self.coverage_manifest = build_rule_derived_coverage_manifest(\n            self.claim, self.plan, assessments={oid: CoverageObligation(\n                oid, ObligationDisposition.UNKNOWN, limitation="M7.5.16 test fixture")\n                for oid in self.plan.expected_obligation_ids})

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

    def test_registry_is_versioned_and_digest_bound(self):
        registry = semantic_evidence_contract_registry()
        self.assertEqual(registry["schema"], "ae32c/semantic-evidence-contract-registry/v1")
        self.assertEqual(registry["registry_sha256"], digest({
            "schema": registry["schema"], "contracts": registry["contracts"]}))

    def test_graph_import_does_not_support_unused_or_not_in_llm_path(self):
        raw = self.files["src/graph.py"]
        obs = observation(self.source_id, "src/graph.py", raw, "graph_import", 1,
                          "rule:AE32A-GRAPH-SERVICE-UNUSED:evidence:graph_import",
                          "python_import_statement",
                          {"module": "networkx", "imported_symbols": [], "matched_module_root": "networkx"})
        bundle = self.bundle([obs])
        result = qualify_typed_evidence_observations(
            bundle, source_manifest=self.manifest, repository_root=self.root)
        self.assertEqual(result["qualifications"][0]["qualification"], "INSUFFICIENT")
        self.assertFalse(result["authority"]["proposition_truth_established"])

    def test_ast_parse_failure_supports_only_narrow_scan_limitation(self):
        raw = self.files["src/broken.py"]
        obs = observation(self.source_id, "src/broken.py", raw, "python_syntax_error", 1,
                          "rule:AE32A-INCOMPLETE-PYTHON-SCAN:evidence:python_syntax_error",
                          "python_ast_parse_failure",
                          {"exception_type": "SyntaxError", "diagnostic_code": "source_parse_failed",
                           "message": "invalid syntax"})
        result = qualify_typed_evidence_observations(
            self.bundle([obs]), source_manifest=self.manifest, repository_root=self.root)
        self.assertEqual(result["qualifications"][0]["qualification"], "SUPPORTED")
        self.assertIn("parse-coverage limitation", result["qualifications"][0]["limitation"])

    def test_scope_exclusion_supports_declaration_not_adequacy(self):
        raw = self.files["src/excluded.py"]
        obs = observation(self.source_id, "src/excluded.py", raw, "scope_exclusion", None,
                          "rule:AE32A-SCOPE-EXCLUSIONS:evidence:scope_exclusion",
                          "declared_scope_exclusion", {"reason": "fixture exclusion"})
        result = qualify_typed_evidence_observations(
            self.bundle([obs]), source_manifest=self.manifest, repository_root=self.root)
        self.assertEqual(result["qualifications"][0]["qualification"], "INSUFFICIENT")
        self.assertIn("independent verification", result["qualifications"][0]["limitation"])

    def test_unregistered_rule_remains_unknown(self):
        raw = self.files["src/graph.py"]
        obs = observation(self.source_id, "src/graph.py", raw, "graph_import", 1,
                          "rule:AE32A-UNKNOWN-RULE:evidence:graph_import",
                          "python_import_statement",
                          {"module": "networkx", "imported_symbols": [], "matched_module_root": "networkx"})
        result = qualify_typed_evidence_observations(
            self.bundle([obs]), source_manifest=self.manifest, repository_root=self.root)
        self.assertEqual(result["qualifications"][0]["qualification"], "UNKNOWN")

    def test_source_bound_defeater_makes_result_contested_but_unverified(self):
        raw = self.files["src/broken.py"]
        obs = observation(self.source_id, "src/broken.py", raw, "python_syntax_error", 1,
                          "rule:AE32A-INCOMPLETE-PYTHON-SCAN:evidence:python_syntax_error",
                          "python_ast_parse_failure",
                          {"exception_type": "SyntaxError", "diagnostic_code": "source_parse_failed",
                           "message": "invalid syntax"})
        defeater = {
            "target_observation_id": obs["evidence_observation_id"],
            "source_snapshot_id": self.source_id,
            "source_path": "src/broken.py",
            "source_content_sha256": hashlib.sha256(raw).hexdigest(),
            "source_line": 1,
            "source_line_sha256": hashlib.sha256(raw.splitlines()[0]).hexdigest(),
            "reason": "Independent reviewer disputes the interpretation.",
        }
        result = qualify_typed_evidence_observations(
            self.bundle([obs]), source_manifest=self.manifest, repository_root=self.root,
            defeaters=(defeater,))
        item = result["qualifications"][0]
        self.assertEqual(item["qualification"], "CONTESTED")
        self.assertEqual(item["defeaters"][0]["validation"], "NOT_ESTABLISHED")

    def test_replay_and_source_drift_rejection(self):
        raw = self.files["src/graph.py"]
        obs = observation(self.source_id, "src/graph.py", raw, "graph_import", 1,
                          "rule:AE32A-GRAPH-SERVICE-UNUSED:evidence:graph_import",
                          "python_import_statement",
                          {"module": "networkx", "imported_symbols": [], "matched_module_root": "networkx"})
        bundle = self.bundle([obs])
        result = qualify_typed_evidence_observations(
            bundle, source_manifest=self.manifest, repository_root=self.root)
        replay = verify_semantic_evidence_qualification(
            result, bundle, source_manifest=self.manifest, repository_root=self.root)
        self.assertTrue(replay["semantic_replay"])
        (self.root / "src/graph.py").write_text("import os\n")
        with self.assertRaises(SemanticQualificationError):
            verify_semantic_evidence_qualification(
                result, bundle, source_manifest=self.manifest, repository_root=self.root)

    def test_line_tampering_and_invalid_source_references_rejected(self):
        raw = self.files["src/graph.py"]
        obs = observation(self.source_id, "src/graph.py", raw, "graph_import", 1,
                          "rule:AE32A-GRAPH-SERVICE-UNUSED:evidence:graph_import",
                          "python_import_statement",
                          {"module": "networkx", "imported_symbols": [], "matched_module_root": "networkx"})
        obs["source_line_sha256"] = "0" * 64
        obs["evidence_observation_id"] = digest({k:v for k,v in obs.items() if k != "evidence_observation_id"})
        with self.assertRaises(SemanticQualificationError):
            qualify_typed_evidence_observations(
                self.bundle([obs]), source_manifest=self.manifest, repository_root=self.root)

    def test_bundle_digest_tampering_rejected(self):
        bundle = self.bundle([])
        bundle["summary"]["semantic_evidence_accepted_count"] = 9
        with self.assertRaisesRegex(SemanticQualificationError, "observation_bundle_digest_mismatch"):
            qualify_typed_evidence_observations(
                bundle, source_manifest=self.manifest, repository_root=self.root)


if __name__ == "__main__":
    unittest.main()

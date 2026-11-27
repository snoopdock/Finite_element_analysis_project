"""AE-45 C2 graph snapshot reconstruction tests; no provider factory is imported."""
import os
import subprocess
import unittest
from pathlib import Path

from tools.ae32d_c_snapshot import verify_c_graph_snapshot
from tools.ae32d_graph_assisted_audit import run_graph_assisted_audit
from tools.ae32d_trial_contracts import build_sanitized_task_projection


CASE_SHA = "dd80be6e7a3e0a912beace92ce0fac446ea6ed61"
FIXTURE = "tests/semantic_audit/fixtures/ae32d_no_defect_control"


def pinned_root():
    raw = os.environ.get("AE32D_CASE_SOURCE_ROOT")
    if not raw:
        raise RuntimeError("missing_pinned_case_source")
    root = Path(raw).resolve(strict=True)
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    if actual != CASE_SHA:
        raise RuntimeError("pinned_case_sha_mismatch")
    return root


def case_record():
    return {
        "case_id": "AE32D-CANDIDATE-NO-DEFECT-001",
        "source": {
            "repository": "snoopdock/Finite_element_analysis_project",
            "source_commit_sha": CASE_SHA,
            "fixture_path": FIXTURE,
        },
        "task": {
            "title": "Complete initialization negative control",
            "problem_statement": "Investigate the complete initialization negative control using only the declared read-only evidence.",
            "declared_scope": ["control.py", "expected_behavior.json", "incident.md"],
            "constraints": ["Do not modify source."],
        },
    }


class CSnapshotVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = pinned_root()
        cls.record = case_record()
        cls.b_report = run_graph_assisted_audit(
            build_sanitized_task_projection(cls.record, experiment_id="AE45-C2", condition="B_graph"),
            cls.root,
        )
        cls.c_projection = build_sanitized_task_projection(
            cls.record, experiment_id="AE45-C2", condition="C_graph_llm"
        )

    def test_exact_b_graph_snapshot_reconstructs_without_provider_access(self):
        result = verify_c_graph_snapshot(self.c_projection, self.b_report, self.root)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(
            result["observed_graph_snapshot"]["graph_fingerprint"],
            self.b_report["graph_snapshot"]["graph_fingerprint"],
        )
        self.assertEqual(result["observed_graph_snapshot"]["source_revision"], CASE_SHA)
        self.assertFalse(result["provider_dispatch_permitted"])
        self.assertEqual(result["provider_calls_attempted"], 0)
        self.assertFalse(result["credentials_accessed"])

    def test_tampered_graph_identity_is_blocked(self):
        import json
        tampered = json.loads(json.dumps(self.b_report))
        tampered["graph_snapshot"]["graph_fingerprint"] = "graph:" + "0" * 32
        result = verify_c_graph_snapshot(self.c_projection, tampered, self.root)
        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(any("graph_query_fingerprint_mismatch" in item for item in result["mismatches"]))
        self.assertFalse(result["provider_dispatch_permitted"])

    def test_projection_must_match_exact_b_source(self):
        altered = dict(self.c_projection)
        altered["source"] = dict(self.c_projection["source"])
        altered["source"]["source_commit_sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "C_snapshot_source_mismatch"):
            verify_c_graph_snapshot(altered, self.b_report, self.root)

    def test_a_projection_cannot_be_used_as_c_snapshot_input(self):
        a_projection = build_sanitized_task_projection(
            self.record, experiment_id="AE45-C2", condition="A_deterministic"
        )
        with self.assertRaisesRegex(ValueError, "C_snapshot_verification_requires_C_projection"):
            verify_c_graph_snapshot(a_projection, self.b_report, self.root)


if __name__ == "__main__":
    unittest.main()

"""AE-45 C0 tests: manual authorization preflight without provider access."""
import os
import subprocess
import unittest
from pathlib import Path

from tools.ae32d_c_preflight import build_c_preflight
from tools.ae32d_graph_assisted_audit import run_graph_assisted_audit
from tools.ae32d_trial_contracts import build_sanitized_task_projection


CASE_SHA = "dd80be6e7a3e0a912beace92ce0fac446ea6ed61"
SOURCE_ENV = "AE32D_CASE_SOURCE_ROOT"
FIXTURE = "tests/semantic_audit/fixtures/ae32d_no_defect_control"


def pinned_root():
    raw = os.environ.get(SOURCE_ENV)
    if not raw:
        raise RuntimeError("missing_pinned_source_environment:" + SOURCE_ENV)
    root = Path(raw).resolve(strict=True)
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    if actual != CASE_SHA:
        raise RuntimeError("pinned_source_sha_mismatch")
    return root


def build_b_report():
    record = {
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
    projection = build_sanitized_task_projection(
        record, experiment_id="AE45-C0-PREFLIGHT", condition="B_graph"
    )
    return run_graph_assisted_audit(projection, pinned_root())


def authorization_from_preflight(preflight):
    return {
        "schema_version": "ae32d/c-authorization/v1",
        "authorization_id": "TEST-AUTH-0001",
        "approved": True,
        "confirmation_phrase": "I_AUTHORIZE_ONE_AE32D_C_PROVIDER_RUN",
        "provider_name": "cloudflare",
        "model_name": "@cf/qwen/qwen3.8-27b",
        "max_model_rounds": 8,
        "max_tool_calls": 10,
        "max_tokens_per_call": 2048,
        "finalization_max_tokens_per_call": 4096,
        "max_total_tokens": 24576,
        "max_elapsed_seconds": 600,
        "max_cost_usd": 0.25,
        "cost_estimator_id": "cloudflare-qwen3.8-live-estimator/v1",
        "cost_estimator_sha256": preflight["cost_estimator_sha256"],
        "prompt_source_sha256": preflight["prompt_source_sha256"],
        "tool_catalog_sha256": preflight["tool_catalog_sha256"],
        "case_id": preflight["case_id"],
        "source_commit_sha": preflight["source_commit_sha"],
        "task_contract_digest": preflight["task_contract_digest"],
        "b_report_sha256": preflight["b_report_sha256"],
        "graph_fingerprint": preflight["graph_fingerprint"],
    }


class CPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b_report = build_b_report()

    def test_no_authorization_is_blocked_and_never_dispatches(self):
        report = build_c_preflight(self.b_report)
        self.assertEqual(report["status"], "blocked_manual_authorization_required")
        self.assertEqual(report["authorization_status"], "absent")
        self.assertFalse(report["provider_dispatch_permitted"])
        self.assertEqual(report["provider_calls_attempted"], 0)
        self.assertFalse(report["credentials_accessed"])
        self.assertIn("manual_authorization_required", report["blocking_reasons"])

    def test_exact_manual_authorization_produces_dispatch_readiness_only(self):
        preflight = build_c_preflight(self.b_report)
        authorization = authorization_from_preflight(preflight)
        report = build_c_preflight(self.b_report, authorization)
        self.assertEqual(report["status"], "ready_for_manual_dispatch")
        self.assertEqual(report["authorization_status"], "valid")
        self.assertFalse(report["provider_dispatch_permitted"])
        self.assertEqual(report["provider_calls_attempted"], 0)
        self.assertFalse(report["credentials_accessed"])
        self.assertTrue(report["manual_dispatch_required"])
        self.assertEqual(report["request_plan"]["provider_name"], "cloudflare")
        self.assertEqual(report["request_plan"]["model_name"], "@cf/qwen/qwen3.8-27b")

    def test_authorization_is_bound_to_exact_B_report_digest(self):
        preflight = build_c_preflight(self.b_report)
        authorization = authorization_from_preflight(preflight)
        authorization["b_report_sha256"] = "0" * 64
        report = build_c_preflight(self.b_report, authorization)
        self.assertEqual(report["status"], "blocked_invalid_authorization")
        self.assertIn("authorization_binding_mismatch:b_report_sha256", report["blocking_reasons"])

    def test_budget_above_hard_ceiling_is_rejected(self):
        preflight = build_c_preflight(self.b_report)
        authorization = authorization_from_preflight(preflight)
        authorization["max_tool_calls"] = 13
        report = build_c_preflight(self.b_report, authorization)
        self.assertEqual(report["status"], "blocked_invalid_authorization")
        self.assertIn("authorization_schema_invalid", report["blocking_reasons"])

    def test_unsupported_provider_model_pair_is_rejected(self):
        preflight = build_c_preflight(self.b_report)
        authorization = authorization_from_preflight(preflight)
        authorization["provider_name"] = "nararouter"
        authorization["model_name"] = "deepseek-v4-pro"
        report = build_c_preflight(self.b_report, authorization)
        self.assertEqual(report["status"], "blocked_invalid_authorization")

    def test_incomplete_B_scope_blocks_even_without_authorization(self):
        incomplete = dict(self.b_report)
        incomplete["coverage"] = dict(self.b_report["coverage"])
        incomplete["coverage"]["declared_scope_complete"] = False
        report = build_c_preflight(incomplete)
        self.assertEqual(report["status"], "blocked_incomplete_B_snapshot")
        self.assertIn("declared_scope_incomplete", report["blocking_reasons"])
        self.assertFalse(report["provider_dispatch_permitted"])

    def test_graph_query_provenance_mismatch_blocks_preflight(self):
        tampered = json_clone(self.b_report)
        tampered["graph_retrieval"][0]["provenance"]["graph_fingerprint"] = "graph:" + "0" * 32
        report = build_c_preflight(tampered)
        self.assertEqual(report["status"], "blocked_incomplete_B_snapshot")
        self.assertIn("graph_query_fingerprint_mismatch", report["blocking_reasons"])


def json_clone(value):
    import json
    return json.loads(json.dumps(value))


if __name__ == "__main__":
    unittest.main()

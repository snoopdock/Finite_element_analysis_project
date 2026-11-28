"""AE-45 C1 request-package tests; no investigator/provider is instantiated."""
import os
import subprocess
import unittest
from pathlib import Path

from tools.ae32d_c_preflight import build_c_preflight
from tools.ae32d_c_request import build_c_request_package
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


def build_auth(preflight):
    return {
        "schema_version": "ae32d/c-authorization/v1",
        "authorization_id": "TEST-C1-AUTH-0001",
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


class CRequestPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = case_record()
        cls.root = pinned_root()
        cls.b_report = run_graph_assisted_audit(
            build_sanitized_task_projection(cls.record, experiment_id="AE45-C1", condition="B_graph"),
            cls.root,
        )
        cls.c_projection = build_sanitized_task_projection(
            cls.record, experiment_id="AE45-C1", condition="C_graph_llm"
        )

    def test_without_authorization_package_is_blocked(self):
        result = build_c_request_package(self.c_projection, self.b_report)
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["request"])
        self.assertFalse(result["manual_dispatch_confirmed"])
        self.assertFalse(result["provider_dispatch_permitted"])
        self.assertEqual(result["provider_calls_attempted"], 0)
        self.assertFalse(result["credentials_accessed"])

    def test_valid_authorization_prepares_request_but_does_not_dispatch(self):
        preflight = build_c_preflight(self.b_report)
        authorization = build_auth(preflight)
        result = build_c_request_package(self.c_projection, self.b_report, authorization)
        self.assertEqual(result["status"], "prepared_manual_only")
        self.assertIsInstance(result["request_sha256"], str)
        request = result["request"]
        self.assertIn("complete initialization negative control", request["investigator_problem"].lower())
        self.assertIn("not ground truth", request["investigator_problem"].lower())
        self.assertLess(len(request["investigator_problem"]), 5_000)
        self.assertNotIn('"payload":', request["investigator_problem"])
        self.assertIn("payload", request["context"]["b_graph"]["retrieval"][0])
        self.assertEqual(request["investigation_requirements"]["required_source_paths"],
                         ["control.py", "expected_behavior.json", "incident.md"])
        self.assertTrue(request["investigation_requirements"]["require_graph_interaction"])
        self.assertEqual(request["investigation_requirements"]["required_context_target"], "control.py")
        self.assertEqual(
            request["investigation_requirements"]["required_context_paths"],
            ["expected_behavior.json", "incident.md"],
        )
        self.assertTrue(request["investigation_requirements"]["prefetch_required_context_trace"])
        self.assertFalse(request["dispatch"]["manual_dispatch_confirmed"])
        self.assertFalse(request["dispatch"]["provider_dispatch_permitted"])
        self.assertEqual(request["dispatch"]["provider_calls_attempted"], 0)
        self.assertFalse(request["dispatch"]["credentials_accessed"])

    def test_context_contract_is_nonempty_and_distinct_from_target(self):
        record = case_record()
        record["task"]["declared_scope"] = ["control.py"]
        b_projection = build_sanitized_task_projection(
            record, experiment_id="AE45-C1-SINGLE-PATH", condition="B_graph"
        )
        b_report = run_graph_assisted_audit(b_projection, self.root)
        projection = build_sanitized_task_projection(
            record, experiment_id="AE45-C1-SINGLE-PATH", condition="C_graph_llm"
        )
        authorization = build_auth(build_c_preflight(b_report))
        with self.assertRaisesRegex(ValueError, "C_request_requires_at_least_one_distinct_context_path"):
            build_c_request_package(projection, b_report, authorization)

    def test_request_contains_no_credential_fields(self):
        preflight = build_c_preflight(self.b_report)
        authorization = build_auth(preflight)
        result = build_c_request_package(self.c_projection, self.b_report, authorization)
        forbidden = {"api_key", "api_token", "account_id", "secret", "access_token"}
        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertNotIn(key.lower(), forbidden)
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(result)

    def test_request_rejects_mismatched_task_projection(self):
        altered = dict(self.c_projection)
        altered["task_contract_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "C_projection_task_digest_mismatch"):
            build_c_request_package(altered, self.b_report)


if __name__ == "__main__":
    unittest.main()

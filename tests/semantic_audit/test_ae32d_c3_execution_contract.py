"""AE-45 C3 provider-free execution-contract tests."""
import hashlib
import unittest
from unittest.mock import patch

from tools.ae32d_c3_execution_contract import _validated_budget, build_c3_execution_contract
from tools.ae32d_trial_contracts import canonical_json_bytes


def digest(char):
    return char * 64


def valid_budget():
    return {
        "max_model_rounds": 11,
        "max_tool_calls": 12,
        "max_tokens_per_call": 2048,
        "finalization_max_tokens_per_call": 6144,
        "max_total_tokens": 30720,
        "max_elapsed_seconds": 900,
        "max_cost_usd": 0.50,
    }


def valid_inputs():
    authorization = {
        "approved": True,
        "authorization_id": "AE45-AUTH-0001",
        "confirmation_phrase": "I_AUTHORIZE_ONE_AE32D_C_PROVIDER_RUN",
    }
    budget = valid_budget()
    case_id = "AE32D-CANDIDATE-EXCEPTION-SWALLOW-001"
    source_sha = "a" * 40
    task_digest = digest("b")
    graph_fingerprint = "graph:" + "d" * 32
    source_manifest = digest("i")
    task_projection = {
        "schema_version": "ae32d/sanitized-task-projection/v1",
        "case_id": case_id,
        "source": {
            "repository": "snoopdock/Finite_element_analysis_project",
            "source_commit_sha": source_sha,
            "fixture_path": "tests/semantic_audit/fixtures/ae32d_exception_swallow_incident",
        },
        "task": {
            "title": "Suppressed I/O exception",
            "problem_statement": "Determine whether the handler suppresses OSError.",
            "declared_scope": ["loader.py", "expected_behavior.json", "incident.md"],
            "constraints": ["Do not modify source."],
        },
        "experiment_id": "AE45-C3-TEST",
        "condition": "C_graph_llm",
        "task_contract_digest": task_digest,
    }
    baseline = {
        "decision": "defect",
        "findings": [],
        "counterevidence": [],
        "unresolved_questions": [],
        "limitations": [],
        "config_digest": digest("h"),
        "source_manifest_digest": source_manifest,
    }
    graph_snapshot = {
        "status": "complete",
        "source_revision": source_sha,
        "source_manifest_sha256": source_manifest,
        "graph_fingerprint": graph_fingerprint,
        "graph_projection_version": "test-v1",
        "evidence_index_status": "complete",
        "graph_backend": "networkx",
        "graph_node_count": 3,
        "graph_edge_count": 2,
        "backend_pipeline_wired": True,
    }
    b_report = {
        "case_id": case_id,
        "source_commit_sha": source_sha,
        "task_contract_digest": task_digest,
        "baseline_report": baseline,
        "graph_snapshot": graph_snapshot,
        "graph_retrieval": [],
    }
    preflight = {
        "schema_version": "ae32d/c-preflight/v1",
        "status": "ready_for_manual_dispatch",
        "authorization_status": "valid",
        "case_id": case_id,
        "source_commit_sha": source_sha,
        "task_contract_digest": task_digest,
        "b_report_sha256": digest("c"),
        "graph_fingerprint": graph_fingerprint,
        "graph_backend": "networkx",
        "prompt_source_sha256": digest("e"),
        "tool_catalog_sha256": digest("f"),
        "cost_estimator_sha256": digest("g"),
        "provider_dispatch_permitted": False,
        "provider_calls_attempted": 0,
        "credentials_accessed": False,
        "manual_dispatch_required": True,
        "blocking_reasons": [],
        "request_plan": {
            "provider_name": "cloudflare",
            "model_name": "@cf/qwen/qwen3.8-27b",
            "authorization_id": "AE45-AUTH-0001",
            "budget": dict(budget),
        },
    }
    c2_snapshot = {
        "schema_version": "ae32d/c-snapshot-verification/v1",
        "status": "verified",
        "case_id": case_id,
        "source_commit_sha": source_sha,
        "task_contract_digest": task_digest,
        "baseline_source_manifest_digest": source_manifest,
        "expected_graph_snapshot": dict(graph_snapshot),
        "observed_graph_snapshot": {
            "source_revision": source_sha,
            "source_manifest_sha256": source_manifest,
            "graph_fingerprint": graph_fingerprint,
        },
        "mismatches": [],
        "provider_dispatch_permitted": False,
        "provider_calls_attempted": 0,
        "credentials_accessed": False,
    }
    with patch("tools.ae32d_c_request.build_c_preflight", return_value=preflight):
        from tools.ae32d_c_request import build_c_request_package
        package = build_c_request_package(task_projection, b_report, authorization)
    return {
        "authorization": authorization,
        "preflight": preflight,
        "task_projection": task_projection,
        "b_report": b_report,
        "snapshot": c2_snapshot,
        "package": package,
    }


class C3ExecutionContractTests(unittest.TestCase):
    def call_contract(self, data, confirmed=False):
        with patch("tools.ae32d_c_request.build_c_preflight", return_value=data["preflight"]):
            return build_c3_execution_contract(
                data["task_projection"],
                data["b_report"],
                data["package"],
                data["snapshot"],
                data["authorization"],
                manual_dispatch_confirmed=confirmed,
            )

    def test_valid_contract_is_provider_free_until_separate_confirmation(self):
        result = self.call_contract(valid_inputs())
        self.assertEqual(result["status"], "ready_for_manual_confirmation")
        self.assertFalse(result["provider_dispatch_permitted"])
        self.assertEqual(result["provider_calls_attempted"], 0)
        self.assertFalse(result["credentials_accessed"])

    def test_manual_confirmation_only_authorizes_later_executor(self):
        result = self.call_contract(valid_inputs(), confirmed=True)
        self.assertEqual(result["status"], "ready_for_c3_executor")
        self.assertTrue(result["manual_dispatch_confirmed"])
        self.assertFalse(result["provider_dispatch_permitted"])
        self.assertEqual(result["provider_calls_attempted"], 0)
        self.assertFalse(result["credentials_accessed"])

    def test_budget_maps_exactly_to_investigator_limits(self):
        mapped = _validated_budget(valid_budget())
        self.assertEqual(mapped["max_rounds"], 11)
        self.assertEqual(mapped["max_tool_calls"], 12)
        self.assertEqual(mapped["max_total_tokens"], 30_720)
        self.assertEqual(mapped["max_elapsed_seconds"], 900)
        self.assertEqual(mapped["max_cost_usd"], 0.50)
        self.assertEqual(mapped["temperature"], 0.0)

    def test_lower_authorized_budget_is_not_widened(self):
        budget = valid_budget()
        budget.update(max_model_rounds=3, max_tool_calls=4,
                      max_total_tokens=4096, max_elapsed_seconds=120,
                      max_cost_usd=0.10)
        mapped = _validated_budget(budget)
        self.assertEqual(mapped["max_rounds"], 3)
        self.assertEqual(mapped["max_tool_calls"], 4)
        self.assertEqual(mapped["max_total_tokens"], 4096)
        self.assertEqual(mapped["max_elapsed_seconds"], 120)
        self.assertEqual(mapped["max_cost_usd"], 0.10)

    def test_budget_cannot_exceed_profile_ceiling(self):
        budget = valid_budget()
        budget["max_total_tokens"] = 30_721
        with self.assertRaisesRegex(ValueError, "C3_budget_exceeds_hard_limit:max_total_tokens"):
            _validated_budget(budget)

    def test_unverified_c2_snapshot_is_rejected(self):
        data = valid_inputs()
        data["snapshot"]["status"] = "mismatch"
        with self.assertRaisesRegex(ValueError, "C3_C2_snapshot_not_verified"):
            self.call_contract(data)

    def test_c2_snapshot_must_match_the_exact_b_graph(self):
        data = valid_inputs()
        data["snapshot"]["observed_graph_snapshot"]["graph_fingerprint"] = "graph:" + "z" * 32
        with self.assertRaisesRegex(ValueError, "C3_C2_graph_snapshot_mismatch:graph_fingerprint"):
            self.call_contract(data)

    def test_request_digest_mismatch_is_rejected(self):
        data = valid_inputs()
        data["package"]["request_sha256"] = digest("z")
        with self.assertRaisesRegex(ValueError, "C3_request_digest_mismatch"):
            self.call_contract(data)

    def test_preflight_mismatch_is_rejected(self):
        data = valid_inputs()
        data["package"]["preflight"]["graph_fingerprint"] = "graph:" + "z" * 32
        with self.assertRaisesRegex(ValueError, "C3_C1_request_package_reconstruction_mismatch"):
            self.call_contract(data)

    def test_task_projection_source_mismatch_is_rejected(self):
        data = valid_inputs()
        data["task_projection"]["source"]["source_commit_sha"] = "z" * 40
        with self.assertRaisesRegex(ValueError, "C_projection_source_mismatch"):
            self.call_contract(data)

    def test_budget_and_investigation_requirements_are_bound_to_rebuilt_c1_package(self):
        data = valid_inputs()
        data["package"]["request"]["budget"]["max_total_tokens"] = 2048
        data["package"]["request_sha256"] = hashlib.sha256(
            canonical_json_bytes(data["package"]["request"])
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "C3_C1_request_package_reconstruction_mismatch"):
            self.call_contract(data)


if __name__ == "__main__":
    unittest.main()

"""AE-45 C3 provider-free execution-contract tests."""
import hashlib
import unittest
from unittest.mock import patch

from tools.ae32d_c3_execution_contract import (
    _validated_budget,
    build_c3_execution_contract,
)
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


def valid_preflight(budget):
    return {
        "schema_version": "ae32d/c-preflight/v1",
        "status": "ready_for_manual_dispatch",
        "authorization_status": "valid",
        "case_id": "AE32D-CANDIDATE-EXCEPTION-SWALLOW-001",
        "source_commit_sha": "a" * 40,
        "task_contract_digest": digest("b"),
        "b_report_sha256": digest("c"),
        "graph_fingerprint": "graph:" + "d" * 32,
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


def valid_inputs():
    authorization = {"approved": True, "authorization_id": "AE45-AUTH-0001"}
    budget = valid_budget()
    preflight = valid_preflight(budget)
    request = {
        "schema_version": "ae32d/c-request/v1",
        "case_id": preflight["case_id"],
        "source_commit_sha": preflight["source_commit_sha"],
        "task_contract_digest": preflight["task_contract_digest"],
        "b_report_sha256": preflight["b_report_sha256"],
        "graph_fingerprint": preflight["graph_fingerprint"],
        "provider_name": "cloudflare",
        "model_name": "@cf/qwen/qwen3.8-27b",
        "authorization_id": "AE45-AUTH-0001",
        "authorization_sha256": hashlib.sha256(canonical_json_bytes(authorization)).hexdigest(),
        "prompt_source_sha256": preflight["prompt_source_sha256"],
        "tool_catalog_sha256": preflight["tool_catalog_sha256"],
        "cost_estimator_sha256": preflight["cost_estimator_sha256"],
        "budget": dict(budget),
        "context": {
            "task_title": "Suppressed I/O exception",
            "task_problem_statement": "Determine whether the handler suppresses OSError.",
            "declared_scope": ["loader.py"],
            "a_baseline": {
                "decision": "defect",
                "findings": [],
                "counterevidence": [],
                "unresolved_questions": [],
                "limitations": [],
                "config_digest": digest("h"),
            },
            "b_graph": {"graph_snapshot": {}, "retrieval": []},
            "interpretation_rule": "A/B are investigative context, not ground truth.",
        },
        "investigation_requirements": {
            "required_source_paths": ["loader.py"],
            "required_graph_target": "path:loader.py",
            "required_graph_relation_types": ["CALLS"],
            "required_graph_direction": "both",
            "require_graph_interaction": True,
            "require_complete_investigation_context": True,
            "prefetch_required_graph_query": True,
            "required_context_target": "loader.py",
            "required_context_paths": [],
            "prefetch_required_context_trace": False,
        },
        "dispatch": {
            "manual_dispatch_confirmed": False,
            "provider_dispatch_permitted": False,
            "provider_calls_attempted": 0,
            "credentials_accessed": False,
        },
        "investigator_problem": "Inspect the bounded source and graph evidence.",
    }
    b_report = {
        "case_id": preflight["case_id"],
        "baseline_report": {"source_manifest_digest": digest("i")},
        "graph_snapshot": {
            "source_manifest_sha256": digest("i"),
            "source_revision": preflight["source_commit_sha"],
            "graph_fingerprint": preflight["graph_fingerprint"],
        },
    }
    c2_snapshot = {
        "schema_version": "ae32d/c-snapshot-verification/v1",
        "status": "verified",
        "case_id": preflight["case_id"],
        "source_commit_sha": preflight["source_commit_sha"],
        "task_contract_digest": preflight["task_contract_digest"],
        "baseline_source_manifest_digest": digest("i"),
        "expected_graph_snapshot": {
            "source_manifest_sha256": digest("i"),
            "source_revision": preflight["source_commit_sha"],
            "graph_fingerprint": preflight["graph_fingerprint"],
        },
        "observed_graph_snapshot": {
            "source_manifest_sha256": digest("i"),
            "source_revision": preflight["source_commit_sha"],
            "graph_fingerprint": preflight["graph_fingerprint"],
        },
        "mismatches": [],
        "provider_dispatch_permitted": False,
        "provider_calls_attempted": 0,
        "credentials_accessed": False,
    }
    request_package = {
        "schema_version": "ae32d/c-request-package/v1",
        "status": "prepared_manual_only",
        "preflight": preflight,
        "request": request,
        "request_sha256": hashlib.sha256(canonical_json_bytes(request)).hexdigest(),
        "manual_dispatch_confirmed": False,
        "provider_dispatch_permitted": False,
        "provider_calls_attempted": 0,
        "credentials_accessed": False,
    }
    return {"authorization": authorization, "preflight": preflight,
            "request": request, "package": request_package,
            "b_report": b_report, "snapshot": c2_snapshot}


class C3ExecutionContractTests(unittest.TestCase):
    def call_contract(self, data, confirmed=False):
        with patch(
            "tools.ae32d_c3_execution_contract.build_c_preflight",
            return_value=data["preflight"],
        ):
            return build_c3_execution_contract(
                data["b_report"],
                data["package"],
                data["snapshot"],
                data["authorization"],
                manual_dispatch_confirmed=confirmed,
            )

    def test_valid_contract_is_provider_free_until_separate_confirmation(self):
        data = valid_inputs()
        result = self.call_contract(data)
        self.assertEqual(result["status"], "ready_for_manual_confirmation")
        self.assertFalse(result["provider_dispatch_permitted"])
        self.assertEqual(result["provider_calls_attempted"], 0)
        self.assertFalse(result["credentials_accessed"])

    def test_manual_confirmation_only_authorizes_later_executor(self):
        data = valid_inputs()
        result = self.call_contract(data, confirmed=True)
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

    def test_request_digest_mismatch_is_rejected(self):
        data = valid_inputs()
        data["package"]["request_sha256"] = digest("z")
        with self.assertRaisesRegex(ValueError, "C3_request_digest_mismatch"):
            self.call_contract(data)

    def test_preflight_mismatch_is_rejected(self):
        data = valid_inputs()
        data["package"]["preflight"]["graph_fingerprint"] = "graph:" + "z" * 32
        with self.assertRaisesRegex(ValueError, "C3_preflight_binding_mismatch"):
            self.call_contract(data)

    def test_request_source_binding_mismatch_is_rejected(self):
        data = valid_inputs()
        data["request"]["source_commit_sha"] = "z" * 40
        data["package"]["request_sha256"] = hashlib.sha256(
            canonical_json_bytes(data["request"])
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "C3_request_binding_mismatch:source_commit_sha"):
            self.call_contract(data)

    def test_duplicate_and_unsafe_source_paths_are_rejected(self):
        for paths in (["loader.py", "loader.py"], ["../outside.py"]):
            data = valid_inputs()
            data["request"]["investigation_requirements"]["required_source_paths"] = paths
            data["package"]["request_sha256"] = hashlib.sha256(
                canonical_json_bytes(data["request"])
            ).hexdigest()
            with self.subTest(paths=paths):
                with self.assertRaisesRegex(ValueError, "C3_required_source_paths_invalid"):
                    self.call_contract(data)

    def test_unverified_or_mismatched_c2_snapshot_is_rejected(self):
        data = valid_inputs()
        data["snapshot"]["status"] = "mismatch"
        with self.assertRaisesRegex(ValueError, "C3_C2_snapshot_not_verified"):
            self.call_contract(data)

    def test_c2_snapshot_must_match_the_exact_b_graph(self):
        data = valid_inputs()
        data["snapshot"]["observed_graph_snapshot"]["graph_fingerprint"] = "graph:" + "z" * 32
        with self.assertRaisesRegex(ValueError, "C3_C2_graph_snapshot_mismatch:graph_fingerprint"):
            self.call_contract(data)

    def test_graph_interaction_cannot_be_silently_disabled(self):
        data = valid_inputs()
        data["request"]["investigation_requirements"]["require_graph_interaction"] = False
        data["package"]["request_sha256"] = hashlib.sha256(
            canonical_json_bytes(data["request"])
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "C3_graph_interaction_must_be_required"):
            self.call_contract(data)


if __name__ == "__main__":
    unittest.main()

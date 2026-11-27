"""AE-45 B condition integration tests over pinned fixture-only graph snapshots."""
import os
import subprocess
import unittest
from pathlib import Path

from tools.ae32d_deterministic_audit import run_deterministic_audit
from tools.ae32d_graph_assisted_audit import run_graph_assisted_audit
from tools.ae32d_trial_contracts import build_sanitized_task_projection


PINNED = {
    "case": ("AE32D_CASE_SOURCE_ROOT", "dd80be6e7a3e0a912beace92ce0fac446ea6ed61"),
    "candidate": ("AE32D_CANDIDATE_SOURCE_ROOT", "afcb1cba064de6f3d680f6be3085a365c6687c7b"),
    "extended": ("AE32D_EXTENDED_SOURCE_ROOT", "c0d700c0a2599aabda8957f54e750a812ea2ef5d"),
}


def pinned_root(key):
    variable, expected_sha = PINNED[key]
    raw = os.environ.get(variable)
    if not raw:
        raise RuntimeError("missing_pinned_source_environment:" + variable)
    root = Path(raw).resolve(strict=True)
    actual_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    if actual_sha != expected_sha:
        raise RuntimeError("pinned_source_sha_mismatch:" + key)
    return root


def record(case_id, source_sha, fixture_path, title, statement, scope):
    return {
        "case_id": case_id,
        "source": {
            "repository": "snoopdock/Finite_element_analysis_project",
            "source_commit_sha": source_sha,
            "fixture_path": fixture_path,
        },
        "task": {
            "title": title,
            "problem_statement": statement,
            "declared_scope": scope,
            "constraints": ["Do not modify source."],
        },
    }


class GraphAssistedConditionBTests(unittest.TestCase):
    def test_b_preserves_exact_a_baseline_and_adds_native_graph_evidence(self):
        case_record = record(
            "AE32D-CANDIDATE-NO-DEFECT-001",
            "dd80be6e7a3e0a912beace92ce0fac446ea6ed61",
            "tests/semantic_audit/fixtures/ae32d_no_defect_control",
            "Complete initialization negative control",
            "Investigate the complete initialization negative control using only the declared read-only evidence.",
            ["control.py", "expected_behavior.json", "incident.md"],
        )
        root = pinned_root("case")
        a_projection = build_sanitized_task_projection(
            case_record, experiment_id="AE45-B-PAIR", condition="A_deterministic"
        )
        b_projection = build_sanitized_task_projection(
            case_record, experiment_id="AE45-B-PAIR", condition="B_graph"
        )
        a_report = run_deterministic_audit(a_projection, root)
        b_report = run_graph_assisted_audit(b_projection, root)

        self.assertEqual(b_report["baseline_report"], a_report)
        self.assertEqual(b_report["baseline_config_digest"], a_report["config_digest"])
        self.assertEqual(b_report["task_contract_digest"], a_report["task_contract_digest"])
        self.assertEqual(b_report["source_manifest_digest"], a_report["source_manifest_digest"])
        self.assertEqual(b_report["decision"], a_report["decision"])
        self.assertEqual(b_report["decision"], "no_defect")
        self.assertEqual(b_report["graph_snapshot"]["source_revision"], case_record["source"]["source_commit_sha"])
        self.assertEqual(b_report["graph_snapshot"]["graph_backend"], "networkx")
        self.assertTrue(b_report["graph_snapshot"]["backend_pipeline_wired"])
        self.assertGreater(b_report["graph_snapshot"]["graph_node_count"], 0)
        self.assertIn("repository_summary", [item["tool"] for item in b_report["graph_retrieval"]])
        self.assertIn("graph_neighbors", [item["tool"] for item in b_report["graph_retrieval"]])
        self.assertIn("search_symbols", [item["tool"] for item in b_report["graph_retrieval"]])
        self.assertIn("graph_path", [item["tool"] for item in b_report["graph_retrieval"]])
        self.assertFalse(any(item["payload"].get("network_calls_performed", False)
                             for item in b_report["graph_retrieval"]))

    def test_b_preserves_a_decision_for_all_remaining_pinned_case_families(self):
        cases = [
            (
                "case",
                record(
                    "AE32D-CANDIDATE-BRANCH-UNBOUND-001",
                    "dd80be6e7a3e0a912beace92ce0fac446ea6ed61",
                    "tests/semantic_audit/fixtures/ae32d_branch_unbound_incident",
                    "Conditional assignment with unbound local",
                    "Investigate the conditional assignment with unbound local using only the declared read-only evidence.",
                    ["branch_logic.py", "expected_behavior.json", "incident.md"],
                ),
            ),
            (
                "extended",
                record(
                    "AE32D-CANDIDATE-EXCEPTION-SWALLOW-001",
                    "c0d700c0a2599aabda8957f54e750a812ea2ef5d",
                    "tests/semantic_audit/fixtures/ae32d_exception_swallow_incident",
                    "Suppressed I/O exception",
                    "Determine whether load_config propagates the reader's OSError as required by the declared contract.",
                    ["loader.py", "expected_behavior.json", "incident.md"],
                ),
            ),
            (
                "extended",
                record(
                    "AE32D-CANDIDATE-DATAFLOW-STALE-VALUE-001",
                    "c0d700c0a2599aabda8957f54e750a812ea2ef5d",
                    "tests/semantic_audit/fixtures/ae32d_dataflow_stale_value_incident",
                    "Stale intermediate value at output sink",
                    "Trace the discounted intermediate through invoice_total and determine whether the return value implements the declared formula.",
                    ["invoice.py", "expected_behavior.json", "incident.md"],
                ),
            ),
            (
                "case",
                record(
                    "AE32D-CANDIDATE-AMBIGUOUS-PROVIDER-001",
                    "dd80be6e7a3e0a912beace92ce0fac446ea6ed61",
                    "tests/semantic_audit/fixtures/ae32d_ambiguous_provider_contract",
                    "Incomplete dynamic provider contract",
                    "Investigate the incomplete dynamic provider contract using only the declared read-only evidence.",
                    ["extractor.py", "adapter.py", "factory.py", "incident.md"],
                ),
            ),
        ]
        for key, case_record in cases:
            with self.subTest(case=case_record["case_id"]):
                root = pinned_root(key)
                a_projection = build_sanitized_task_projection(
                    case_record, experiment_id="AE45-B-ALL-CASES", condition="A_deterministic"
                )
                b_projection = build_sanitized_task_projection(
                    case_record, experiment_id="AE45-B-ALL-CASES", condition="B_graph"
                )
                a_report = run_deterministic_audit(a_projection, root)
                b_report = run_graph_assisted_audit(b_projection, root)
                self.assertEqual(b_report["baseline_report"], a_report)
                self.assertEqual(b_report["decision"], a_report["decision"])
                self.assertEqual(b_report["graph_snapshot"]["source_revision"], case_record["source"]["source_commit_sha"])
                self.assertTrue(b_report["graph_snapshot"]["backend_pipeline_wired"])
                self.assertIn("graph_neighbors", [item["tool"] for item in b_report["graph_retrieval"]])

    def test_b_provider_case_keeps_abstention_and_uses_declared_context_tools(self):
        fixture = "tests/semantic_audit/fixtures/ae32c_provider_interface_incident"
        case_record = record(
            "AE32D-CANDIDATE-PROVIDER-INTERFACE-001",
            "afcb1cba064de6f3d680f6be3085a365c6687c7b",
            fixture,
            "Provider interface attribute mismatch",
            "Investigate the controlled provider-interface incident and assess missing runtime evidence.",
            [fixture + "/pipeline/extractor.py", fixture + "/providers/adapter.py",
             "related tests and documented runtime behavior where present"],
        )
        root = pinned_root("candidate")
        projection = build_sanitized_task_projection(
            case_record, experiment_id="AE45-B-PROVIDER", condition="B_graph"
        )
        report = run_graph_assisted_audit(projection, root)
        tools = [item["tool"] for item in report["graph_retrieval"]]
        self.assertEqual(report["decision"], "abstain")
        self.assertIn("find_related_tests", tools)
        self.assertIn("trace_execution_context", tools)
        self.assertEqual(report["baseline_report"]["decision"], "abstain")
        self.assertTrue(report["graph_snapshot"]["backend_pipeline_wired"])


if __name__ == "__main__":
    unittest.main()

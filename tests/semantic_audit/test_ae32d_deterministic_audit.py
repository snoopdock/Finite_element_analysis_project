"""AE-45 A3 integration tests for deterministic condition A."""
import os
import subprocess
import unittest
from pathlib import Path

from tools.ae32d_deterministic_audit import run_deterministic_audit
from tools.ae32d_trial_contracts import build_sanitized_task_projection


PINNED = {
    "candidate": ("AE32D_CANDIDATE_SOURCE_ROOT", "afcb1cba064de6f3d680f6be3085a365c6687c7b"),
    "case": ("AE32D_CASE_SOURCE_ROOT", "dd80be6e7a3e0a912beace92ce0fac446ea6ed61"),
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


def task_record(case_id, source_sha, fixture_path, title, statement, scope, constraints):
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
            "constraints": constraints,
        },
    }


class DeterministicConditionATests(unittest.TestCase):
    def run_case(self, key, record):
        projection = build_sanitized_task_projection(
            record, experiment_id="AE45-A3-INTEGRATION", condition="A_deterministic"
        )
        return run_deterministic_audit(projection, pinned_root(key))

    def test_branch_control_produces_evidence_backed_defect(self):
        record = task_record(
            "AE32D-CANDIDATE-BRANCH-UNBOUND-001",
            "dd80be6e7a3e0a912beace92ce0fac446ea6ed61",
            "tests/semantic_audit/fixtures/ae32d_branch_unbound_incident",
            "Conditional assignment with unbound local",
            "Investigate the conditional assignment with unbound local using only the declared read-only evidence.",
            ["branch_logic.py", "expected_behavior.json", "incident.md"],
            ["Do not modify source code."],
        )
        report = self.run_case("case", record)
        self.assertEqual(report["decision"], "defect")
        self.assertTrue(any(item["finding_id"].startswith("A-CFG-") for item in report["findings"]))
        self.assertEqual(report["condition"], "A_deterministic")
        self.assertEqual(report["status"], "partial")

    def test_complete_initialization_control_produces_scoped_no_defect(self):
        record = task_record(
            "AE32D-CANDIDATE-NO-DEFECT-001",
            "dd80be6e7a3e0a912beace92ce0fac446ea6ed61",
            "tests/semantic_audit/fixtures/ae32d_no_defect_control",
            "Complete initialization negative control",
            "Investigate the complete initialization negative control. Report no defect if the source satisfies both outcomes.",
            ["control.py", "expected_behavior.json", "incident.md"],
            ["Do not modify source code."],
        )
        report = self.run_case("case", record)
        self.assertEqual(report["decision"], "no_defect")
        self.assertTrue(report["counterevidence"])
        self.assertEqual(report["status"], "completed")
        self.assertTrue(report["coverage"]["declared_scope_complete"])

    def test_exception_contract_produces_defect(self):
        record = task_record(
            "AE32D-CANDIDATE-EXCEPTION-SWALLOW-001",
            "c0d700c0a2599aabda8957f54e750a812ea2ef5d",
            "tests/semantic_audit/fixtures/ae32d_exception_swallow_incident",
            "Suppressed I/O exception",
            "Determine whether load_config propagates the reader's OSError as required by the declared contract.",
            ["loader.py", "expected_behavior.json", "incident.md"],
            ["Do not modify source."],
        )
        report = self.run_case("extended", record)
        self.assertEqual(report["decision"], "defect")
        self.assertTrue(any(item["finding_id"].startswith("A-EXC-") for item in report["findings"]))

    def test_stale_intermediate_sink_produces_defect(self):
        record = task_record(
            "AE32D-CANDIDATE-DATAFLOW-STALE-VALUE-001",
            "c0d700c0a2599aabda8957f54e750a812ea2ef5d",
            "tests/semantic_audit/fixtures/ae32d_dataflow_stale_value_incident",
            "Stale intermediate value at output sink",
            "Trace the discounted intermediate through invoice_total and determine whether the return value implements the declared formula.",
            ["invoice.py", "expected_behavior.json", "incident.md"],
            ["Trace values from definition to sink.", "Do not modify source."],
        )
        report = self.run_case("extended", record)
        self.assertEqual(report["decision"], "defect")
        self.assertTrue(any(item["finding_id"].startswith("A-DATAFLOW-") for item in report["findings"]))

    def test_provider_interface_without_complete_contract_abstains(self):
        fixture = "tests/semantic_audit/fixtures/ae32c_provider_interface_incident"
        record = task_record(
            "AE32D-CANDIDATE-PROVIDER-INTERFACE-001",
            "afcb1cba064de6f3d680f6be3085a365c6687c7b",
            fixture,
            "Provider interface attribute mismatch",
            "Investigate the controlled provider-interface incident; report confirmed observations, hypotheses, missing evidence and uncertainty.",
            [fixture + "/pipeline/extractor.py", fixture + "/providers/adapter.py",
             "related tests and documented runtime behavior where present"],
            ["Do not treat token presence as proof of causal correctness."],
        )
        report = self.run_case("candidate", record)
        self.assertEqual(report["decision"], "abstain")
        self.assertTrue(any(item["classification"] == "observation" for item in report["findings"]))
        self.assertTrue(report["unresolved_questions"])
        evidence_paths = {e["path"] for f in report["findings"] for e in f["evidence"]}
        self.assertIn("pipeline/extractor.py", evidence_paths)
        self.assertIn("providers/adapter.py", evidence_paths)

    def test_ambiguous_dynamic_provider_contract_abstains(self):
        record = task_record(
            "AE32D-CANDIDATE-AMBIGUOUS-PROVIDER-001",
            "dd80be6e7a3e0a912beace92ce0fac446ea6ed61",
            "tests/semantic_audit/fixtures/ae32d_ambiguous_provider_contract",
            "Incomplete dynamic provider contract",
            "Investigate the incomplete dynamic provider contract using only the declared read-only evidence.",
            ["extractor.py", "adapter.py", "factory.py", "incident.md"],
            ["Do not claim runtime behavior unless the supplied evidence establishes it."],
        )
        report = self.run_case("case", record)
        self.assertEqual(report["decision"], "abstain")
        self.assertTrue(any(item["classification"] == "observation" for item in report["findings"]))
        self.assertTrue(report["unresolved_questions"])

    def test_runner_rejects_non_a_condition_projection(self):
        record = task_record(
            "AE32D-CANDIDATE-NO-DEFECT-001",
            "dd80be6e7a3e0a912beace92ce0fac446ea6ed61",
            "tests/semantic_audit/fixtures/ae32d_no_defect_control",
            "Complete initialization negative control",
            "Investigate the complete initialization negative control.",
            ["control.py", "expected_behavior.json"],
            ["Do not modify source."],
        )
        projection = build_sanitized_task_projection(
            record, experiment_id="AE45-A3-INTEGRATION", condition="B_graph"
        )
        with self.assertRaisesRegex(ValueError, "condition_A_requires_A_deterministic_projection"):
            run_deterministic_audit(projection, pinned_root("case"))


if __name__ == "__main__":
    unittest.main()

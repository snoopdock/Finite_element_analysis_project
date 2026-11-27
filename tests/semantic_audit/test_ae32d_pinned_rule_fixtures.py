"""AE-45 A2 integration checks against exact pinned case fixture snapshots."""
import json
import os
import subprocess
import unittest
from pathlib import Path

from tools.ae32d_deterministic_rules import (
    analyze_exception_contract_suppression,
    analyze_stale_intermediate_sink,
    analyze_unbound_local_return,
    evaluate_function_subset,
    observe_dynamic_attribute_mismatch,
)


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
        raise RuntimeError("pinned_source_sha_mismatch:" + key + ":" + actual_sha)
    return root


def read_text(root, relative):
    path = (root / relative).resolve(strict=True)
    path.relative_to(root)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("fixture_file_not_regular:" + relative)
    return path.read_text(encoding="utf-8")


class PinnedDeterministicRuleFixtureTests(unittest.TestCase):
    def test_branch_unbound_and_complete_initialization_controls(self):
        root = pinned_root("case")
        branch = "tests/semantic_audit/fixtures/ae32d_branch_unbound_incident"
        control = "tests/semantic_audit/fixtures/ae32d_no_defect_control"
        branch_source = read_text(root, branch + "/branch_logic.py")
        control_source = read_text(root, control + "/control.py")
        branch_report = analyze_unbound_local_return(branch_source, "work", "result")
        control_report = analyze_unbound_local_return(control_source, "work", "result")
        self.assertTrue(branch_report["unbound_return_read"])
        self.assertFalse(control_report["unbound_return_read"])

        control_contract = json.loads(read_text(root, control + "/expected_behavior.json"))
        for case in control_contract["input_cases"]:
            result = evaluate_function_subset(control_source, "work", case["arguments"])
            self.assertEqual(result["status"], "supported")
            self.assertEqual(result["value"], case["expected"]["value"])

    def test_exception_rule_uses_pinned_task_visible_contract(self):
        root = pinned_root("extended")
        fixture = "tests/semantic_audit/fixtures/ae32d_exception_swallow_incident"
        source = read_text(root, fixture + "/loader.py")
        contract = json.loads(read_text(root, fixture + "/expected_behavior.json"))
        expected = contract["input_cases"][0]["expected"]
        self.assertEqual(expected["kind"], "raise")
        report = analyze_exception_contract_suppression(
            source, contract["function"], expected["exception"], expected["kind"], "reader"
        )
        self.assertEqual(report["status"], "supported")
        self.assertTrue(report["suppression_observed"])

    def test_dataflow_rule_uses_only_declared_fixture_examples(self):
        root = pinned_root("extended")
        fixture = "tests/semantic_audit/fixtures/ae32d_dataflow_stale_value_incident"
        source = read_text(root, fixture + "/invoice.py")
        contract = json.loads(read_text(root, fixture + "/expected_behavior.json"))
        cases = [
            {"arguments": row["arguments"], "expected": row["expected"]["value"]}
            for row in contract["input_cases"]
            if row["expected"]["kind"] == "return"
        ]
        report = analyze_stale_intermediate_sink(source, contract["function"], "discounted", cases)
        self.assertEqual(report["status"], "supported")
        self.assertTrue(report["stale_sink_observed"])

    def test_provider_interface_mismatch_remains_abstention(self):
        root = pinned_root("candidate")
        fixture = "tests/semantic_audit/fixtures/ae32c_provider_interface_incident"
        consumer = read_text(root, fixture + "/pipeline/extractor.py")
        provider = read_text(root, fixture + "/providers/adapter.py")
        report = observe_dynamic_attribute_mismatch(
            consumer, provider, "extract", "ProviderAdapter", "provider"
        )
        self.assertIn("total_calls", report["observed_unmatched_attribute_reads"])
        self.assertEqual(report["decision"], "abstain")

    def test_ambiguous_provider_fixture_keeps_missing_runtime_dependency_unresolved(self):
        root = pinned_root("case")
        fixture = "tests/semantic_audit/fixtures/ae32d_ambiguous_provider_contract"
        consumer = read_text(root, fixture + "/extractor.py")
        provider = read_text(root, fixture + "/adapter.py")
        factory = read_text(root, fixture + "/factory.py")
        self.assertIn("runtime_provider", factory)
        self.assertFalse((root / fixture / "runtime_provider.py").exists())
        report = observe_dynamic_attribute_mismatch(consumer, provider, "extract", "Adapter", "provider")
        self.assertEqual(report["decision"], "abstain")


if __name__ == "__main__":
    unittest.main()

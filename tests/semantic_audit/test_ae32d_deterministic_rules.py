"""AE-45 A2 tests for bounded deterministic semantic rule primitives."""
import unittest

from tools.ae32d_deterministic_rules import (
    UnsupportedRuleSyntax,
    analyze_exception_contract_suppression,
    analyze_stale_intermediate_sink,
    analyze_unbound_local_return,
    evaluate_function_subset,
    observe_dynamic_attribute_mismatch,
    safe_evaluate,
)
import ast


class DeterministicRulePrimitiveTests(unittest.TestCase):
    def test_unbound_local_is_detected_on_unassigned_branch(self):
        source = """def work(flag):
    if flag:
        result = 5
    return result
"""
        report = analyze_unbound_local_return(source, "work", "result")
        self.assertEqual(report["status"], "supported")
        self.assertTrue(report["unbound_return_read"])

    def test_complete_initialization_is_counterexample(self):
        source = """def work(flag):
    result = 0
    if flag:
        result = 5
    return result
"""
        report = analyze_unbound_local_return(source, "work", "result")
        self.assertEqual(report["status"], "supported")
        self.assertFalse(report["unbound_return_read"])
        self.assertEqual(evaluate_function_subset(source, "work", [True]), {
            "status": "supported", "kind": "return", "value": 5,
        })
        self.assertEqual(evaluate_function_subset(source, "work", [False]), {
            "status": "supported", "kind": "return", "value": 0,
        })

    def test_unsupported_control_flow_fails_closed(self):
        source = """def work(flag):
    try:
        result = 1
    except Exception:
        result = 0
    return result
"""
        report = analyze_unbound_local_return(source, "work", "result")
        self.assertEqual(report["status"], "unsupported")

    def test_exception_contract_suppression_detects_fallback_return(self):
        source = """def load_config(reader):
    try:
        return reader()
    except OSError:
        return {}
"""
        report = analyze_exception_contract_suppression(source, "load_config", "OSError", "raise")
        self.assertEqual(report["status"], "supported")
        self.assertTrue(report["suppression_observed"])

    def test_exception_reraise_is_counterevidence(self):
        source = """def load_config(reader):
    try:
        return reader()
    except OSError:
        raise
"""
        report = analyze_exception_contract_suppression(source, "load_config", "OSError", "raise")
        self.assertFalse(report["suppression_observed"])

    def test_stale_intermediate_is_detected_at_return_sink(self):
        source = """def invoice_total(subtotal, discount, tax):
    discounted = subtotal - discount
    return subtotal + tax
"""
        report = analyze_stale_intermediate_sink(
            source, "invoice_total", "discounted",
            [{"arguments": [100, 10, 5], "expected": 95}],
        )
        self.assertEqual(report["status"], "supported")
        self.assertTrue(report["intermediate_assigned"])
        self.assertFalse(report["sink_reads_intermediate"])
        self.assertTrue(report["stale_sink_observed"])
        self.assertEqual(report["comparisons"][0]["actual"], 105)

    def test_corrected_dataflow_is_counterexample(self):
        source = """def invoice_total(subtotal, discount, tax):
    discounted = subtotal - discount
    return discounted + tax
"""
        report = analyze_stale_intermediate_sink(
            source, "invoice_total", "discounted",
            [{"arguments": [100, 10, 5], "expected": 95}],
        )
        self.assertTrue(report["sink_reads_intermediate"])
        self.assertFalse(report["stale_sink_observed"])

    def test_safe_expression_interpreter_rejects_calls(self):
        with self.assertRaisesRegex(UnsupportedRuleSyntax, "unsupported_expression"):
            safe_evaluate(ast.parse("__import__('os').system('id')", mode="eval").body, {})

    def test_dynamic_attribute_mismatch_is_observation_plus_abstention(self):
        consumer = """def extract(provider):
    return provider.total_calls
"""
        provider = """class Provider:
    def __init__(self):
        self.calls = 0
"""
        report = observe_dynamic_attribute_mismatch(consumer, provider, "extract", "Provider")
        self.assertEqual(report["status"], "supported")
        self.assertEqual(report["observed_unmatched_attribute_reads"], ["total_calls"])
        self.assertEqual(report["decision"], "abstain")


if __name__ == "__main__":
    unittest.main()

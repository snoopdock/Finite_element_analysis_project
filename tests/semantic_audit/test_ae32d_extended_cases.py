"""Tests for AE-32D exception-flow and data-flow fixtures."""
import unittest
from pathlib import Path

from tools.ae32d_verify_extended_cases import verify_exception_swallow, verify_stale_dataflow

ROOT = Path(__file__).resolve().parents[2]


class ExtendedCaseTests(unittest.TestCase):
    def test_swallowed_oserror_is_reproduced(self):
        result = verify_exception_swallow(ROOT)
        self.assertEqual(result["status"], "verified", result["errors"])
        self.assertIn("runtime_confirms_declared_exception_is_swallowed", result["checks"])

    def test_stale_value_reaches_output_sink(self):
        result = verify_stale_dataflow(ROOT)
        self.assertEqual(result["status"], "verified", result["errors"])
        self.assertEqual(result["runtime"]["observed"], "105")
        self.assertEqual(result["runtime"]["expected"], 95)


if __name__ == "__main__":
    unittest.main()

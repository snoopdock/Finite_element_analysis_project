"""Deterministic AE-32D case-matrix verification tests."""
import unittest
from pathlib import Path

from tools.ae32d_verify_case_matrix import (
    verify_ambiguous_provider, verify_branch_unbound, verify_no_defect,
)

ROOT = Path(__file__).resolve().parents[2]


class CaseMatrixTests(unittest.TestCase):
    def test_branch_unbound_fixture_reproduces_control_flow_failure(self):
        result = verify_branch_unbound(ROOT)
        self.assertEqual(result["status"], "verified", result["errors"])
        self.assertIn("false_branch_unbound_local_reproduced", result["checks"])

    def test_no_defect_control_satisfies_both_declared_paths(self):
        result = verify_no_defect(ROOT)
        self.assertEqual(result["status"], "verified", result["errors"])
        self.assertIn("both_contract_paths_execute_as_declared", result["checks"])

    def test_ambiguous_case_proves_missing_evidence_without_claiming_runtime_failure(self):
        result = verify_ambiguous_provider(ROOT)
        self.assertEqual(result["status"], "ambiguity_boundary_verified", result["errors"])
        self.assertFalse(result["runtime"]["executed"])
        self.assertIn("factory_dependency_implementation_absent_from_evidence", result["checks"])


if __name__ == "__main__":
    unittest.main()

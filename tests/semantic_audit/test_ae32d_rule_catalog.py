"""AE-45 A1 deterministic rule catalog boundary tests."""
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.ae32d_validate_rule_catalog import ROOT, validate_catalog


class DeterministicRuleCatalogTests(unittest.TestCase):
    def test_catalog_schema_and_semantic_boundary(self):
        schema_path = ROOT / "evaluation" / "ae32d" / "deterministic-rule-catalog.schema.json"
        catalog_path = ROOT / "evaluation" / "ae32d" / "deterministic-rule-catalog.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(catalog)
        self.assertEqual(catalog["status"], "specification_only")
        self.assertFalse(catalog["ground_truth_read_allowed"])
        self.assertFalse(catalog["primary_benchmark_promotion_allowed"])

    def test_rule_ids_are_unique_and_rule_execution_is_not_claimed(self):
        report = validate_catalog()
        self.assertEqual(report["status"], "valid_specification_only")
        self.assertEqual(report["rule_count"], 5)
        self.assertEqual(len(report["rule_ids"]), len(set(report["rule_ids"])))
        self.assertFalse(report["rules_executed"])
        self.assertFalse(report["ground_truth_read_allowed"])
        self.assertFalse(report["primary_benchmark_promotion_allowed"])

    def test_catalog_has_positive_counterexample_and_insufficient_context_exercises(self):
        catalog = json.loads(
            (ROOT / "evaluation" / "ae32d" / "deterministic-rule-catalog.json").read_text(encoding="utf-8")
        )
        exercises = {
            item["exercise"]
            for rule in catalog["rules"]
            for item in rule["exercise_fixtures"]
        }
        self.assertIn("rule_exercise", exercises)
        self.assertIn("counterexample", exercises)
        self.assertIn("insufficient_context", exercises)

    def test_rule_specs_retain_counterevidence_and_abstention_conditions(self):
        catalog = json.loads(
            (ROOT / "evaluation" / "ae32d" / "deterministic-rule-catalog.json").read_text(encoding="utf-8")
        )
        for rule in catalog["rules"]:
            with self.subTest(rule=rule["rule_id"]):
                self.assertTrue(rule["counterevidence"])
                self.assertTrue(rule["abstain_when"])
                self.assertTrue(rule["preconditions"])
                self.assertTrue(rule["sufficient_evidence"])


if __name__ == "__main__":
    unittest.main()

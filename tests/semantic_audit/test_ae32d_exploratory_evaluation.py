"""AE-42 exploratory-reference and scoring boundary tests."""
import copy
import json
import unittest
from pathlib import Path

from tools.ae32d_exploratory_evaluation import (
    CONDITIONS, REGISTRY, ROOT, read_json, score_trials, validate_registry,
)


class ExploratoryEvaluationTests(unittest.TestCase):
    def setUp(self):
        errors, self.registry = validate_registry(ROOT)
        self.assertEqual(errors, [])

    def make_trials(self):
        records = []
        for ref in self.registry["records"]:
            outcome = {
                "defect": "defect",
                "no_defect": "no_defect",
                "ambiguous": "abstain",
            }[ref["provisional_outcome"]]
            for condition in CONDITIONS:
                records.append({
                    "trial_id": ref["case_id"] + "-" + condition,
                    "case_id": ref["case_id"],
                    "condition": condition,
                    "source_commit_sha": ref["source_commit_sha"],
                    "config_digest": "test-config-v1",
                    "status": "completed",
                    "outcome": outcome,
                    "output_ref": "synthetic-test-record",
                })
        return {
            "schema_version": "ae32d/exploratory-trials/v1",
            "experiment_id": "AE42-UNIT-TEST",
            "status": "exploratory_unfrozen",
            "records": records,
        }

    def test_registry_is_valid_and_never_promotes_gold(self):
        errors, registry = validate_registry(ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(len(registry["records"]), 6)
        self.assertFalse(registry["ground_truth_write_allowed"])
        self.assertFalse(registry["primary_benchmark_promotion_allowed"])
        for record in registry["records"]:
            self.assertEqual(record["independent_adjudication"], "not_performed")
            self.assertFalse(record["primary_benchmark_eligible"])

    def test_exploratory_score_is_correctly_labeled_and_reports_raw_counts(self):
        report = score_trials(ROOT, self.make_trials())
        self.assertEqual(report["status"], "exploratory_only_not_gold_adjudication")
        self.assertFalse(report["gold_adjudication_performed"])
        self.assertFalse(report["primary_benchmark_score"])
        self.assertEqual(report["primary_benchmark_eligible_cases"], 0)
        for condition in CONDITIONS:
            counts = report["conditions"][condition]["counts"]
            self.assertEqual(counts["true_positive"], 4)
            self.assertEqual(counts["false_positive"], 0)
            self.assertEqual(counts["appropriate_ambiguous_abstention"], 1)
            self.assertEqual(counts["missing"], 0)
            self.assertEqual(counts["exploratory_defect_detection_rate"], 1.0)
            self.assertEqual(counts["exploratory_false_positive_rate"], 0.0)

    def test_missing_trials_are_counted_not_dropped(self):
        trials = self.make_trials()
        trials["records"] = [
            row for row in trials["records"]
            if not (row["case_id"] == self.registry["records"][0]["case_id"]
                    and row["condition"] == "B_graph")
        ]
        report = score_trials(ROOT, trials)
        counts = report["conditions"]["B_graph"]["counts"]
        self.assertEqual(counts["missing"], 1)
        self.assertEqual(len(report["conditions"]["B_graph"]["case_outcomes"]), 6)

    def test_trial_source_mismatch_is_rejected(self):
        trials = self.make_trials()
        trials["records"][0]["source_commit_sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "trial_source_commit_mismatch"):
            score_trials(ROOT, trials)

    def test_duplicate_case_condition_is_rejected(self):
        trials = self.make_trials()
        trials["records"].append(copy.deepcopy(trials["records"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate_trial_id"):
            score_trials(ROOT, trials)


if __name__ == "__main__":
    unittest.main()

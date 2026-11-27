"""AE-32D deterministic outcome-classifier tests."""
import unittest

from tools.ae32d_score_outcomes import classify_outcome, summarize_outcomes


class OutcomeClassifierTests(unittest.TestCase):
    def test_confirmed_defect_categories(self):
        expected = {
            "defect_detected": "correct_detection",
            "no_defect": "missed_defect",
            "abstain": "incorrect_abstention",
        }
        for outcome, category in expected.items():
            with self.subTest(outcome=outcome):
                self.assertEqual(
                    classify_outcome("confirmed_defect", outcome, provenance_valid=True)["category"],
                    category,
                )

    def test_no_defect_categories(self):
        expected = {
            "defect_detected": "false_positive",
            "no_defect": "correct_no_defect",
            "abstain": "incorrect_abstention",
        }
        for outcome, category in expected.items():
            with self.subTest(outcome=outcome):
                self.assertEqual(
                    classify_outcome("no_defect", outcome, provenance_valid=True)["category"],
                    category,
                )

    def test_ambiguous_case_requires_abstention(self):
        self.assertEqual(
            classify_outcome("ambiguous", "abstain", provenance_valid=True)["category"],
            "correct_abstention",
        )
        self.assertEqual(
            classify_outcome("ambiguous", "defect_detected", provenance_valid=True)["category"],
            "false_positive",
        )

    def test_pending_or_invalid_provenance_is_not_scorable(self):
        self.assertEqual(
            classify_outcome("pending_adjudication", "defect_detected", provenance_valid=True)["category"],
            "not_scorable",
        )
        self.assertEqual(
            classify_outcome("confirmed_defect", "defect_detected", provenance_valid=False)["category"],
            "not_scorable",
        )
        self.assertEqual(
            classify_outcome("confirmed_defect", None, provenance_valid=True)["category"],
            "not_scorable",
        )

    def test_unknown_labels_and_outcomes_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown_ground_truth_label"):
            classify_outcome("maybe", "abstain", provenance_valid=True)
        with self.assertRaisesRegex(ValueError, "unknown_audit_outcome"):
            classify_outcome("no_defect", "probably", provenance_valid=True)

    def test_summary_preserves_all_categories_and_denominators(self):
        records = [
            {"ground_truth": "confirmed_defect", "audit_outcome": "defect_detected", "provenance_valid": True},
            {"ground_truth": "no_defect", "audit_outcome": "defect_detected", "provenance_valid": True},
            {"ground_truth": "ambiguous", "audit_outcome": "abstain", "provenance_valid": True},
            {"ground_truth": "pending_adjudication", "audit_outcome": "no_defect", "provenance_valid": True},
        ]
        result = summarize_outcomes(records)
        self.assertEqual(result["attempted_case_count"], 4)
        self.assertEqual(result["scorable_case_count"], 3)
        self.assertEqual(result["not_scorable_case_count"], 1)
        self.assertEqual(result["correct_case_count"], 2)
        self.assertAlmostEqual(result["case_level_correct_audit_outcome_rate"], 2 / 3)
        self.assertEqual(set(result["categories"]), {
            "correct_detection", "missed_defect", "false_positive",
            "correct_no_defect", "correct_abstention", "incorrect_abstention",
            "not_scorable",
        })


if __name__ == "__main__":
    unittest.main()

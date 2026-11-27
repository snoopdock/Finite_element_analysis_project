"""AE-45 A/B contract-schema and information-boundary tests."""
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from tools.ae32d_trial_contracts import build_sanitized_task_projection

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "evaluation" / "ae32d"


def load_schema(name):
    return json.loads((EVALUATION / name).read_text(encoding="utf-8"))


class ABContractSchemaTests(unittest.TestCase):
    def setUp(self):
        self.task_schema = load_schema("sanitized-task-projection.schema.json")
        self.report_schema = load_schema("condition-report.schema.json")
        Draft202012Validator.check_schema(self.task_schema)
        Draft202012Validator.check_schema(self.report_schema)
        self.task_validator = Draft202012Validator(self.task_schema)
        self.report_validator = Draft202012Validator(self.report_schema)

    def valid_task(self):
        return {
            "schema_version": "ae32d/sanitized-task-projection/v1",
            "case_id": "AE32D-CANDIDATE-EXCEPTION-SWALLOW-001",
            "source": {
                "repository": "snoopdock/Finite_element_analysis_project",
                "source_commit_sha": "c0d700c0a2599aabda8957f54e750a812ea2ef5d",
                "fixture_path": "tests/semantic_audit/fixtures/ae32d_exception_swallow_incident",
            },
            "task": {
                "title": "Suppressed I/O exception",
                "problem_statement": "Determine whether load_config propagates OSError.",
                "declared_scope": ["loader.py", "expected_behavior.json", "incident.md"],
                "constraints": ["Do not modify source."],
            },
            "experiment_id": "AE45-SCHEMA-TEST",
            "condition": "A_deterministic",
            "task_contract_digest": "a" * 64,
        }

    def valid_report(self):
        return {
            "schema_version": "ae32d/condition-report/v1",
            "case_id": "AE32D-CANDIDATE-EXCEPTION-SWALLOW-001",
            "condition": "A_deterministic",
            "adapter_revision": "test-adapter-v1",
            "source_commit_sha": "c0d700c0a2599aabda8957f54e750a812ea2ef5d",
            "task_contract_digest": "a" * 64,
            "config_digest": "b" * 64,
            "source_manifest_digest": "c" * 64,
            "status": "completed",
            "coverage": {
                "declared_scope_complete": True,
                "truncated": False,
                "unreadable_paths": [],
                "missing_paths": [],
            },
            "findings": [{
                "finding_id": "F-1",
                "statement": "The inspected handler suppresses OSError.",
                "classification": "observation",
                "evidence": [{
                    "path": "loader.py", "line_start": 1, "line_end": 5,
                    "file_sha256": "d" * 64, "role": "supports",
                }],
            }],
            "counterevidence": [],
            "unresolved_questions": [],
            "decision": "defect",
            "limitations": [],
            "execution_trace": [{
                "step_id": "S-1", "operation": "inspect_declared_scope", "status": "ok",
            }],
        }

    def case_record_with_hidden_fields(self):
        return {
            "case_id": "AE32D-CANDIDATE-EXCEPTION-SWALLOW-001",
            "source": {
                "repository": "snoopdock/Finite_element_analysis_project",
                "source_commit_sha": "c0d700c0a2599aabda8957f54e750a812ea2ef5d",
                "fixture_path": "tests/semantic_audit/fixtures/ae32d_exception_swallow_incident",
            },
            "task": {
                "title": "Suppressed I/O exception",
                "problem_statement": "Determine whether load_config propagates OSError.",
                "declared_scope": ["loader.py", "expected_behavior.json", "incident.md"],
                "constraints": ["Do not modify source."],
            },
            "ground_truth": {"label": "pending_adjudication", "expected_findings": [{"secret": "hidden"}]},
            "review": {"status": "pending"},
            "machine_reference": {"provisional_outcome": "defect"},
            "evaluation": {"primary_benchmark_eligible": False},
        }

    def test_task_projection_accepts_only_allowlisted_fields(self):
        self.assertEqual(list(self.task_validator.iter_errors(self.valid_task())), [])

    def test_task_projection_rejects_hidden_reference_and_adjudication_fields(self):
        for forbidden in (
            "ground_truth", "review", "machine_reference", "provisional_outcome",
            "expected_findings", "primary_benchmark_eligible",
        ):
            candidate = self.valid_task()
            candidate[forbidden] = {"label": "defect"}
            with self.subTest(forbidden=forbidden):
                self.assertTrue(list(self.task_validator.iter_errors(candidate)))

    def test_task_projection_requires_exact_source_sha_and_digest(self):
        for field, value in (("source_commit_sha", "not-a-commit"), ("task_contract_digest", "not-a-digest")):
            candidate = self.valid_task()
            if field == "source_commit_sha":
                candidate["source"][field] = value
            else:
                candidate[field] = value
            with self.subTest(field=field):
                self.assertTrue(list(self.task_validator.iter_errors(candidate)))

    def test_projection_builder_drops_hidden_fields_and_hashes_only_task_contract(self):
        record = self.case_record_with_hidden_fields()
        projection = build_sanitized_task_projection(
            record, experiment_id="AE45-UNIT-TEST", condition="A_deterministic"
        )
        self.assertEqual(list(self.task_validator.iter_errors(projection)), [])
        for forbidden in ("ground_truth", "review", "machine_reference", "evaluation"):
            self.assertNotIn(forbidden, projection)
        digest = projection["task_contract_digest"]
        record["ground_truth"]["label"] = "defect"
        record["machine_reference"]["provisional_outcome"] = "no_defect"
        repeated = build_sanitized_task_projection(
            record, experiment_id="AE45-UNIT-TEST", condition="A_deterministic"
        )
        self.assertEqual(repeated["task_contract_digest"], digest)

    def test_projection_builder_rejects_path_traversal_and_backslash_paths(self):
        for unsafe_path in ("../outside", "/absolute/path", "folder\\escape", "a/../b"):
            record = self.case_record_with_hidden_fields()
            record["task"]["declared_scope"] = [unsafe_path]
            with self.subTest(path=unsafe_path):
                with self.assertRaisesRegex(ValueError, "task_declared_scope_must_be_nonempty_unique_paths"):
                    build_sanitized_task_projection(
                        record, experiment_id="AE45-UNIT-TEST", condition="A_deterministic"
                    )

    def test_projection_builder_rejects_wrong_source_sha_and_condition(self):
        record = self.case_record_with_hidden_fields()
        record["source"]["source_commit_sha"] = "not-a-sha"
        with self.assertRaisesRegex(ValueError, "exact_lowercase_source_commit_sha_required"):
            build_sanitized_task_projection(record, experiment_id="AE45-UNIT-TEST", condition="A_deterministic")
        record = self.case_record_with_hidden_fields()
        with self.assertRaisesRegex(ValueError, "unsupported_deterministic_condition"):
            build_sanitized_task_projection(record, experiment_id="AE45-UNIT-TEST", condition="C_graph_llm")

    def test_completed_report_requires_explicit_decision(self):
        candidate = self.valid_report()
        del candidate["decision"]
        self.assertTrue(list(self.report_validator.iter_errors(candidate)))

    def test_completed_report_rejects_infrastructure_error_as_no_defect(self):
        candidate = self.valid_report()
        candidate["status"] = "failed"
        candidate["decision"] = "no_defect"
        candidate["error_code"] = "checkout_failed"
        self.assertTrue(list(self.report_validator.iter_errors(candidate)))

    def test_failed_report_requires_error_code_and_null_decision(self):
        candidate = self.valid_report()
        candidate["status"] = "failed"
        candidate["decision"] = None
        candidate["error_code"] = "checkout_failed"
        self.assertEqual(list(self.report_validator.iter_errors(candidate)), [])

    def test_evidence_requires_hash_bound_positive_line_ranges(self):
        candidate = self.valid_report()
        candidate["findings"][0]["evidence"][0]["line_start"] = 0
        candidate["findings"][0]["evidence"][0]["file_sha256"] = "bad"
        self.assertTrue(list(self.report_validator.iter_errors(candidate)))

    def test_report_rejects_unrecognized_hidden_fields(self):
        candidate = self.valid_report()
        candidate["machine_reference_outcome"] = "defect"
        self.assertTrue(list(self.report_validator.iter_errors(candidate)))

    def test_valid_abstention_is_not_missing_or_error(self):
        candidate = self.valid_report()
        candidate["decision"] = "abstain"
        candidate["unresolved_questions"] = ["The permitted evidence does not establish runtime behavior."]
        self.assertEqual(list(self.report_validator.iter_errors(candidate)), [])


if __name__ == "__main__":
    unittest.main()

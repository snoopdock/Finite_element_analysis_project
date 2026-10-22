from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = {
    ".github/workflows/ae32c-live-evaluation.yml": "live-evaluation",
    ".github/workflows/ae32c-provider-compatibility-preflight.yml": "preflight",
}


class AE32CValidationGateWorkflowTests(unittest.TestCase):
    def test_live_provider_workflows_remain_manual_only(self):
        for relative, _ in WORKFLOWS.items():
            with self.subTest(workflow=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertRegex(text, r"(?m)^on:\s*\n\s+workflow_dispatch:\s*$")
                self.assertNotRegex(text, r"(?m)^\s{2}(push|pull_request|schedule|workflow_call):")
                self.assertIn("validation_run_id:", text)
                self.assertRegex(text, r"(?m)^\s+required: true\s*$")
                self.assertIn("actions: read", text)
                self.assertIn("contents: read", text)

    def test_provider_jobs_depend_on_the_validation_gate_and_pin_source_sha(self):
        for relative, job_name in WORKFLOWS.items():
            with self.subTest(workflow=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                job = re.search(
                    rf"(?ms)^  {re.escape(job_name)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
                    text,
                )
                self.assertIsNotNone(job)
                body = job.group(1)
                self.assertIn("needs: [guard, validation-gate]", body)
                self.assertIn("ref: ${{ needs.validation-gate.outputs.source_commit_sha }}", body)

    def test_validation_gate_checks_dispatcher_and_independent_evidence(self):
        for relative, _ in WORKFLOWS.items():
            with self.subTest(workflow=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("gh api", text)
                self.assertIn("manual-validation-evidence-${VALIDATION_RUN_ID}-${VALIDATION_RUN_ATTEMPT}", text)
                self.assertIn("validation_gate.py check-run", text)
                self.assertIn("validation_gate.py verify", text)

    def test_validation_gate_job_does_not_receive_provider_secrets(self):
        for relative, _ in WORKFLOWS.items():
            with self.subTest(workflow=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                gate = re.search(r"(?ms)^  validation-gate:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", text)
                self.assertIsNotNone(gate)
                self.assertNotIn("secrets.", gate.group(1))


if __name__ == "__main__":
    unittest.main()

"""Contract checks against GitHub Actions' manual, pinned serial batch workflow."""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class BatchWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow=(ROOT/'.github/workflows/ae32c-round-robin-evaluation.yml').read_text(encoding='utf-8')

    def test_manual_only_and_explicit_consent(self):
        self.assertRegex(self.workflow, r'(?m)^on:\s*\n\s+workflow_dispatch:')
        self.assertNotRegex(self.workflow, r'(?m)^\s{2}(?:push|pull_request|schedule|workflow_call):')
        for required in ('validation_run_id:', 'confirm_live_provider_calls:', 'pause_seconds:', 'rounds:'):
            self.assertIn(required,self.workflow)
        self.assertIn('"$CONFIRMED" == "true"',self.workflow)
        self.assertIn('"refs/heads/main"',self.workflow)

    def test_validation_gate_precedes_secrets_and_pins_source(self):
        gate=re.search(r'(?ms)^  validation-gate:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)',self.workflow)
        self.assertIsNotNone(gate)
        self.assertNotIn('secrets.',gate.group(1))
        self.assertIn('validation_gate.py verify',gate.group(1))
        self.assertIn('gh run download',gate.group(1))
        provider_job=re.search(r'(?ms)^  round-robin-evaluation:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)',self.workflow)
        self.assertIsNotNone(provider_job)
        self.assertIn('needs: [guard, validation-gate]',provider_job.group(1))
        self.assertIn('ref: ${{ needs.validation-gate.outputs.source_commit_sha }}', provider_job.group(1))

    def test_round_order_serial_delay_and_failures_preserved(self):
        self.assertIn('providers=(cloudflare nararouter openrouter)',self.workflow)
        self.assertIn('for (( round=1; round<=BATCH_ROUNDS; round++ ))',self.workflow)
        self.assertIn('for provider in "${providers[@]}"',self.workflow)
        self.assertIn('sleep "$PAUSE_SECONDS"',self.workflow)
        self.assertIn('continue-on-error: true',self.workflow)
        self.assertIn('runner-exit-code.txt',self.workflow)
        self.assertIn('timeout --signal=TERM',self.workflow)
        self.assertIn('if: always()',self.workflow)
        self.assertIn('Enforce complete batch gate after evidence publication',self.workflow)

if __name__=='__main__':
    unittest.main()


def test_phase_e4_retains_one_dispatch_and_machine_readable_batch_summary():
    workflow = (ROOT/'.github/workflows/ae32c-round-robin-evaluation.yml').read_text(encoding='utf-8')
    assert workflow.count('workflow_dispatch:') == 1
    assert 'python -m audit_engine.semantic_audit.ae32c.batch_evaluation' in workflow
    assert '--batch-dir "$RUNNER_TEMP/ae32c-batch"' in workflow
    assert 'batch-summary.md" >> "$GITHUB_STEP_SUMMARY"' in workflow
    assert 'name: ae32c-round-robin-${{ github.run_id }}-${{ github.run_attempt }}' in workflow
    assert 'Enforce complete batch gate after evidence publication' in workflow


def test_e5_round_robin_retains_single_manual_dispatch_and_independent_trials():
    workflow = (ROOT/'.github/workflows/ae32c-round-robin-evaluation.yml').read_text(encoding='utf-8')
    assert workflow.count('workflow_dispatch:') == 1
    assert 'providers=(cloudflare nararouter openrouter)' in workflow
    assert 'for provider in "${providers[@]}"' in workflow
    assert 'sleep "$PAUSE_SECONDS"' in workflow
    assert 'validation_gate.py verify' in workflow
    assert 'runner-exit-code.txt' in workflow
    assert '--confirm-live-provider-calls' in workflow
    assert 'Enforce complete batch gate after evidence publication' in workflow
    assert not __import__('re').search(r'(?m)^  (?:schedule|push|pull_request):', workflow)


def test_e5_report_schema_and_historical_pause_default_are_explicit():
    workflow = (ROOT/'.github/workflows/ae32c-round-robin-evaluation.yml').read_text(encoding='utf-8')
    assert "default: '120'" in workflow
    assert "ae32c/batch-evaluation/v3" in workflow
    assert "ae32c/batch-evaluation/v2" not in workflow

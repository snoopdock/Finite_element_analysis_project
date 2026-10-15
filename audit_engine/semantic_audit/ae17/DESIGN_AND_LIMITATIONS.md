# AE-17 — Evidence-Seeking Investigation / G9.19

AE-17 **replays AE-16 supplied evidence** and constructs a deterministic,
bounded investigation dossier. It is a hypothesis-generation and retrieval layer,
**not an authenticated GitHub-run analyzer, causal proof engine, or finding authority**.

## Read-only lifecycle

1. Verify an existing AE-16 generation against actual declaration and evidence files.
2. Recreate its graph and observation report, check authority boundaries.
3. Retrieve one-hop graph context and exact artifact hash references for each issue.
4. Enumerate two alternative explanations and specific discriminating evidence to seek
   (where appropriate), never assign probability or claim one explanation is true.
5. Seal the bounded dossier; independently replay it from underlying AE-16 inputs.
6. Optionally persist it through **existing** G3.2 `AuditLongTermMemory`, explicitly
   as historical, snapshot-bound hypothesis context, not reusable current proof.
7. For *actual independently admitted verification obligations*, use the **existing**
   G3.3 `AuditOrchestrationService.plan`. No verifier is run by AE-17.

## Scope and limitations

- Only issues emitted by AE-16 are investigated. A successful AE-16 declaration
  with no issues **does not** certify code correctness or completeness.
- AE-16's source evidence remains **supplied, unauthenticated execution evidence**.
- Unknown issue types receive generic competing hypotheses with explicit uncertainty.
- Hypotheses are fixed-version review prompts, not LLM judgments.
- One-hop retrieval does not claim runtime reachability or causality.
- G3.3 planner accepts only existing G3 obligations from trusted caller; AE-17
  does **not** manufacture obligations from speculative explanations.
- Historical memory is snapshot-filtered; an old record is never current proof.
- No subprocess, code execution, remote access, model invocation, GitHub write,
  workflow trigger, automated remediation or merge.
- Budgets: at most 80 issues and 64 adjacent relationships per issue.
- Out-of-budget records are flagged `truncated` and not silently discarded.
- The publication contract is source replay and exact-bytes integrity, not
  authenticated provenance of an external workflow.

## Example CLI

```bash
PYTHONPATH=. python tools/run_ae17_investigation.py \
  --declaration INPUT/run.json \
  --evidence-root INPUT/evidence \
  --ae16-output INPUT/ae16_results \
  --output INPUT/ae17_results
```

When the original AE-16 run included AE-01/AE-09 source correlation, repeat the
same `--ae01-output` and `--source-root` options for independent replay.

To replay without writing: add `--verify-only`.

# AE-32C Phase E.3 — Source-Evidence Fidelity and Round-Robin Evaluation

## Scope and assurance limits

AE-32C is a read-only repository investigator. E.3 reduces confusion between a **requested end beyond EOF** and **actual omitted indexed source lines**, strengthens evidence-phase inspection guidance, and separates live protocol completion from source-coverage acceptance. A source citation is not a proof of causal correctness: semantic claim support and runtime truth remain **not independently adjudicated**. The repository's historical interface incident remains evaluation data, never an automatically proved production defect.

### Source-read semantics

`read_source_file` retains the historical `truncated` boolean for compatibility. That field **must not** be interpreted as an omitted-line oracle: it may be true only because the model requested an end beyond EOF. Use these new response fields:

- `end_clamped_to_eof`: the requested end was beyond the indexed file's line count;
- `source_range_complete`: returned numbered lines span the entire indexed file;
- `content_omitted`: one or more indexed lines are absent from the response;
- `omitted_line_count`: indexed line count outside the returned interval;
- `read_coverage`: `complete_file`, `partial_file`, or `empty_file`.

Even a `complete_file` result may contain redactions. Coverage is evidence of indexed-line-span inclusion, not raw-byte disclosure or semantic entailment. Missing, unsafe and invalid paths remain rejected. The investigator cross-checks explicit non-omission flags against its line-span criteria rather than trusting only a claim made inside a response.

### Model guidance and findings

At the last evidence-gathering round before reserved finalization, an incomplete required-source policy adds a bounded reminder listing only the caller-declared indexed paths still needing full source reads. It does not execute any read itself. Finalization still closes evidence-gathering and preserves strict evidence-ID, line, hash, and citation checks. The comparison record labels semantic claim support as requiring independent adjudication, even when citations and declared source coverage pass.

### Full versus incomplete smoke outcomes

The original single-provider live workflow now fails its **evidence-complete** gate when an accepted diagnosis is `completed_with_incomplete_evidence`, required coverage is missing, or required root-cause citations are absent. It still preserves those reports as valuable incomplete evidence. The E.3-era batch assessor made this distinction explicit via `protocol_complete`, `evidence_complete`, and `passed`. The E.5 v2 reporting contract superseded the ambiguous batch-level name with `graph_evidence_complete` and `overall_accepted_trials`; the v3 follow-up separately distinguishes graph protocol failure classes, graph evidence failure classes, and provider error codes. No test that merely resolves citations can manufacture an overall accepted outcome.

### Round-robin workflow

The `main` branch gets `AE-32C Round-Robin Provider Evaluation (Manual)` (`.github/workflows/ae32c-round-robin-evaluation.yml`). One **manual** dispatch supplies a successful `validation_run_id`, explicit consent, 1–4 rounds (default 4), and 30/60/120 second pauses (default 120 for historical comparison). Each round executes **Cloudflare → NaraRouter → OpenRouter**, then repeats. One round is exactly three independent trials, not parallel jobs.

A separate validation-gate job verifies the selected successful G9.42 dispatcher run, its detached artifacts and provenance catalog and exact source commit **before any secrets or live-provider requests are used**. The live job checks out the pinned source commit, not the moving branch tip. Each evaluation has its own directory, bounded subprocess execution, result code, log, comparison report and smoke evidence. A failed provider trial does not block subsequent providers. A final aggregate report marks the batch failed if any required trial is missing, protocol-incomplete, or source-coverage-incomplete. Evidence is uploaded even when the batch fails.

The aggregate artifact is `ae32c-round-robin-<run_id>-<attempt>` and includes `run-context.json`, `round-01/cloudflare/...`, etc., `batch-summary.json`, `batch-summary.md`, and each trial's original reports. Raw provider credentials are never written to these summaries; the workflow runs each child provider subprocess with other providers' secret variables excluded. Standard GitHub-hosted job/runner time and provider budgets still apply; a successful batch is not evidence that all future calls will succeed.

### Manual validation order

1. Apply E.3 `STAGE1_SECTION_UUIDS/` payload to `stage1/section-uuids` and `MAIN_BRANCH/` payload to `main`; review both diffs and push manually.
2. From `main`, run **Manual Validation Dispatcher** targeting `stage1/section-uuids`, profile `G9.42`, regression mode `profile`.
3. Only after successful targeted/full regression and detached evidence, open **AE-32C Round-Robin Provider Evaluation (Manual)** in Actions, select `main`, enter that **new** validation run ID, choose rounds and pause, and check the explicit consent box.
4. Download the single batch evidence archive and the validation gate artifact. Review per-trial evidence, non-completion causes, coverage, and scientific validity independently. Human diagnostic review is required to accept the broader Phase E objective.

No `push`, `pull_request`, `schedule`, or automatic repair triggers are introduced. No stage source is edited by the workflow. Its provider calls are explicitly consented to for each batch dispatch, never launched by a separate scheduling system.

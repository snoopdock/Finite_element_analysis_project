# AE-32C E.7-R.3N.7.5.1 — Finalization Context Budget Compatibility

**Status:** Corrective patch prepared; GitHub validation pending  
**Exact failed baseline commit:** `8131ff7d7ebf6027ba784b8d209bd2e455221ea4`  
**Triggering validation run:** `44042875615` (G9.42, failed only in full regression)

## 1. Triggering failure

The N7.5 Manual Validation run passed all 404 G9.42 targeted tests and all 53 independent validation-engine tests. Full regression ran 3,405 tests: 3,396 passed, one failed, eight skipped, and zero errors.

The sole failure was:

`tests/semantic_audit/test_ae32c_finalization_context_compaction.py::test_recovery_feedback_is_compacted_before_exact_source_candidates_are_dropped`

The test's third finalization round stopped before a provider call. Its event was `finalization_context_budget_unavailable`. The recorded cumulative character budget was 30,000, with 21,450 already consumed and 8,550 remaining; the smallest evidence-preserving context variant was 9,469 characters. The shortfall was 919 characters.

The investigator correctly refused to discard exact source-reference candidates. That safety property must remain.

## 2. Root cause

N7.5 expanded the fixed `FINALIZATION_SYSTEM_INSTRUCTIONS`. The fixed prompt consumed unnecessary space in every rebuilt finalization context. The compaction variants reduced descriptive evidence details but could not shrink this fixed system message, so the smallest safe context remained above the cumulative character ceiling.

This is a prompt-size regression, not a provider-token exhaustion, SSE, tool authorization, or evidence-ledger defect.

## 3. Corrective implementation

- Replace the repetitive finalization system prompt with a compact equivalent.
- Preserve the virtual `submit_ae32c_response` response-channel contract.
- Preserve the exact diagnosis and claim keys.
- Preserve exact evidence-ID and source-reference requirements.
- Preserve mandatory required source-line anchors.
- Preserve untrusted-evidence handling and prohibition on tool/filesystem/network access.
- Preserve distinctions between static evidence, historical metadata, test candidates and actual runtime/test execution.
- Preserve EOF/truncation interpretation using `end_clamped_to_eof`, `source_range_complete`, `content_omitted` and `omitted_line_count`.
- Preserve concise output requirements and local validation.
- Do not reset or bypass cumulative prompt-character accounting.
- Do not drop evidence IDs or exact source-reference candidates to fit the budget.

The fixed finalization instruction text is reduced from 4,199 to 2,553 characters (1,646 fewer characters). This creates additional headroom while retaining the evidence and safety contract.

## 4. Tests

The existing regression test remains intact and must pass. It verifies that recovery feedback is compacted, exact source-reference candidates survive, the diagnosis is accepted, and the cumulative context target is respected.

An additional test asserts that the finalization instructions remain at or below 2,800 characters and retain the critical evidence, response-channel, source-anchor, runtime-evidence and truncation requirements.

The existing test that proves the investigator stops safely when no context can fit also remains unchanged.

## 5. Explicitly unchanged

- N7.5 Cloudflare/Qwen phase-specific token settings.
- Native virtual response tool behavior and local validation.
- Non-streaming, low-reasoning finalization profile.
- Finalization recovery allowance.
- N7.4 SSE parser and reasoning-only recovery.
- Cumulative prompt/token budgets and future-round reservations.
- Evidence ledger, exact source candidates, source hashes and snapshot verification.
- Citation coverage, provenance, G9.42, full regression and smoke-gate requirements.
- Existing monetary estimator and ceiling.
- No `main` branch changes.

## 6. Acceptance criteria

1. G9.42 passes on the exact new Stage1 commit.
2. Full repository regression passes on GitHub Actions.
3. The previously failing context-compaction test passes.
4. Recovery context fits within the cumulative prompt budget without resetting counters.
5. Exact source-reference candidates and all evidence IDs remain available.
6. The no-fit case still stops before a provider call and reports `finalization_context_budget_unavailable`.
7. Evidence digest and provenance verification pass.
8. No N7.5 provider profile, token, response-channel or monetary setting changes.

## 7. Build verification

- G9.42 target suite: 404 passed.
- Focused finalization/investigator/provider suites: 150 passed.
- Finalization context-compaction file: 4 passed.
- Python compilation: passed.
- Full local repository regression: attempted but did not complete before the execution timeout; no full-regression pass is claimed.

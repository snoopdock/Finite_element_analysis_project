# AE-32C Phase E.4 — Source-Line Evidence Support and Provider Protocol Adaptation

**Status:** implementation candidate, pending manually triggered G9.42 GitHub acceptance and independent live-evaluation/human review.

## Problem statement

After Phase E.3, the controlled round-robin executed all 12 scheduled evaluations on the same validated source. Cloudflare submitted no accepted diagnosis (0/4); NaraRouter and OpenRouter each submitted four (4/4). Citation resolution and full source-file inspection were not sufficient to establish that the cited code line supported the stated attribute-interface conclusion. The presence of the adapter's class declaration on an observed line does not establish the adapter's counter members.

## Design and contracts

E.4 introduces an **optional, caller-declared** `required_source_anchors` mapping to `RepositoryInvestigator`, retaining `required_source_paths`. Each `(path, token)` pair must be supported by a direct, source-hash-bound, **complete** `read_source_file` result and a root-cause citation to the exact line containing the literal token. Search hits, document narratives, other lines in the same file, and syntactically valid but unrelated citations do not meet this criterion. The mapping is bounded to 12 required indexed paths, four tokens per path and 120 chars per token; invalid configurations fail before provider requests.

For the controlled fixture only, the caller declares:

| Path | Literal source witness | What it supports |
|---|---|---|
| `pipeline/extractor.py` | `provider.total_calls` | A direct attribute access is written on that source line |
| `providers/adapter.py` | `self.calls` | That assignment appears in the inspected adapter implementation |

It does **not** establish absence of another Python attribute, class inheritance semantics, runtime reproduction, or correctness of the proposed fix. The model-generated causal conclusion still needs independent adjudication.

- Missing witnesses **reject high-confidence diagnoses**, with a bounded correction opportunity under the unchanged finalization budget.
- For lower-confidence diagnoses, the report records `source_textual_support.status=incomplete`, `completed_with_incomplete_evidence`, and `diagnosis_submitted_with_textual_source_support_gap`.
- Reports distinguish `required_source_coverage` from `source_textual_support`; the latter is a *textual evidence* gate, not a proof-of-correctness gate.
- Finalization includes a compact, provider-name-specific **prompt-only** response strategy. All providers still have precisely the same JSON, ledger, evidence, and citation validators. Provider/mode guarantees are **not inferred** from endpoint compatibility.

## Round-robin batch assessment

The existing manual workflow is unchanged: Cloudflare → NaraRouter → OpenRouter, 1–4 rounds, 30/60/120-second pauses. The development-branch batch assessor now additionally:

1. Rejects a trial if its comparison JSON or Markdown fails its SHA-256 manifest (including missing/unsafe member names).
2. Separates protocol completion, coverage completion, and exact-line textual witness completion.
3. Fails the evidence gate if textual support is missing or not assessed in the E.4 evaluation.
4. Emits per-provider denominators, protocol and evidence counts, textual support counts, observed median duration and failed stop reasons.
5. Always reports diagnostic accuracy as `not_assessed`, retaining every failed trial and the independent human-review requirement.

Artifact SHA-256 is an integrity/consistency check, not an external signature or statement of model accuracy.

## Adversarial validation

Tests must cover positive full-read/code-line witnesses, false class-line citations, low-confidence incomplete cases, invalid policies, corrupted comparison artifacts, all provider prompt strategies, and complete denominators that include failed trials. Existing AE32C regression tests must continue passing. Full GitHub G9.42 regression and exact-commit detached evidence are mandatory before live dispatch.

## Limitations and next steps

This work **does not implement an independent semantic entailment prover** or prove that `total_calls` is impossible at runtime. More general evidence support may require a separate structured claim type, a narrowly scoped static witness engine, and independent experimental adjudication. No autonomous repair or GitHub push is enabled.

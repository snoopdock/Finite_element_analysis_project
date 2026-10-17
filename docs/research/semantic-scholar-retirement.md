# Semantic Scholar — Retired from Active Retrieval, Retained for Provenance

## Decision

As of G9.37, `semantic_scholar` is removed from the active provider fan-out in `research/evidence.py` after the bounded anonymous-access trial returned HTTP 429 on all three live probe requests and no records. The trial also followed historical runs with repeated rate limiting. The project does not currently have an eligible institutional API key.

## What changes

- New live retrieval cycles call arXiv and Wikipedia only.
- The runtime provider registry records Semantic Scholar as `retired_from_active_retrieval` with the observed reason.
- Retirement metadata is kept separate from active provider outcomes so the provider is not falsely counted as a current failing provider on every run.

## What is deliberately retained

- `research/semantic_scholar.py` remains in the repository, unchanged by this retirement decision.
- Existing evidence records that name `provider: semantic_scholar`, `retriever_module: research.semantic_scholar`, URLs, timestamps, and provenance IDs are not rewritten or deleted by this patch.
- Existing output/state history and Git history remain untouched by this code change.
- `merge_evidence` continues to preserve old evidence records when no new record with the same source ID is supplied.

## Reconsideration criteria

Reactivation requires an explicit reviewed change and a successful, low-volume access qualification showing useful anonymous results without repeated HTTP 429. This patch does not add credentials, perform new Semantic Scholar calls, or delete the historical implementation.

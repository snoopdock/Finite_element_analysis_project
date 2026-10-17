# FEA Full-Pipeline LLM Provider Benchmark

## Purpose

The manual `FEA LLM Provider Benchmark (Report Only)` workflow runs the same FEA application pipeline in three isolated matrix jobs: Cloudflare Workers AI, NaraRouter, and OpenRouter. Each job checks out the same selected commit, resets generated runtime state and cache, uses the same configuration and limits, runs `python main.py --config config.yaml`, and runs the existing publication-integrity/LaTeX validation if the pipeline completes.

## Default models

- Cloudflare: `@cf/meta/llama-3.1-8b-instruct-fast`
- NaraRouter: `agnes-2.5-flash`
- OpenRouter: `deepseek/deepseek-v4.1-flash-1017`

These defaults are explicit to avoid model-discovery calls. Model availability and output limits can change at the provider.

## Extended-run budget

Defaults are 8,000 output tokens per call, up to 80 logical calls per provider, and a 240-minute hard timeout per provider job. Available inputs bound token caps to 4,000/8,000/12,000, calls to 30/50/80, and timeouts to 120/180/240 minutes. The operator must explicitly set `confirm_high_budget=true`.

The token cap is a ceiling, not a request to spend the entire allocation. The pipeline's prompts still determine actual response length. In benchmark mode the selected token cap is applied to every LLM request, including calls whose normal production cap is lower, so the experiment can expose provider/model output-limit behavior.

## Isolation and safety

- The workflow is manual only and uses `contents: read`.
- It does not commit or push pipeline state or generated documents.
- Each provider job starts from the same clean state and produces a separate artifact.
- Only the secret for the selected provider is injected into the pipeline step.
- API keys are not written to the report or state.
- Provider responses remain untrusted input to existing parsers and integrity checks.
- The benchmark can produce large technical documents and may consume substantial API quota or incur charges, particularly for the OpenRouter DeepSeek route. Confirm current provider pricing and data-handling terms before dispatch.

## Result artifacts

Each provider artifact contains the pipeline log, publication validation log, generated output/evidence files, state including `model_usage`, and a credential-free JSON/Markdown summary. The summary includes logical calls, successful/failed calls, HTTP attempts, reported token usage when available, runtime, artifact sizes and SHA-256 hashes. Missing token-usage fields are reported as unreported rather than estimated as actual usage.

A successful API call is not proof of scientific correctness. A successful full run requires the main application to finish, report `last_run_status=success`, and pass publication integrity validation. Partial retrieval/provider outcomes remain visible in the artifacts.

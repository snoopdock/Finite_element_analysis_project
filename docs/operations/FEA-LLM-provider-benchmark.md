# FEA LLM Provider Benchmark — Runtime Diagnostics

Each provider artifact now includes `output/provider_runtime_diagnostics.json`.

The file contains:
- source and workflow commit identifiers;
- phase events for research, extract, write, adjustment and assembly;
- provider call and HTTP-attempt deltas for each phase;
- reported token-usage deltas;
- final provider counters;
- the active phase and sanitized exception on a crash.

`provider-benchmark-summary.json` also records source/workflow revisions, error counts, and a compact phase trace. These are operational facts, not an evaluation of scientific correctness.

The workflow remains manual-only. A successful provider HTTP response is not equivalent to pipeline success, and a valid PDF is not equivalent to a complete run.

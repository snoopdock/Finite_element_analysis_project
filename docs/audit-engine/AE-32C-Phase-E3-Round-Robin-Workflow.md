# AE-32C Phase E.3: manually dispatched round-robin provider evaluations

Use the `AE-32C Round-Robin Provider Evaluation (Manual)` workflow on `main` only.

**Inputs**: `validation_run_id` (the freshly passing manual G9.42 dispatcher run), `rounds` (1/2/3/4; default 4), `pause_seconds` (30/60/120; default 60), and explicit `confirm_live_provider_calls` consent. Three providers run per round in the order Cloudflare → NaraRouter → OpenRouter; the next round repeats the same order. Each trial invokes one baseline and at most ten graph-assisted calls plus the existing bounded provider transport retry. A four-round dispatch can therefore authorize up to 12 trials and a significant number of billable model requests; select fewer rounds if costs/time are a concern.

**Gate**: The exact-commit validation job verifies the run's dispatcher metadata, detached evidence, G9.42 profile, source/engine commit, hashes, and provenance catalog before the provider job begins. Missing, failed, wrong-source or stale evidence rejects the batch. Live jobs check out exactly the validated source SHA.

**Failure handling**: Every trial is run separately with an independent output directory and hard wall-time bound. A failure is recorded and the next provider still executes. Between trials the job sleeps for the configured duration. `batch-summary.json` and `.md` aggregate the actual reports in round-robin order. Evidence is always uploaded. The final job step fails if any expected trial lacks a complete protocol and declared source-coverage result. Incomplete evidence is never silently treated as a fully supported diagnosis.

**Boundaries**: No scheduled or push triggers, provider repair, checkout modification, commits, or pushes. Credentials are confined to the live job and unrelated provider secrets are stripped from each child process. GitHub's job-time limit and the existing per-provider API limits still apply. Citation resolution and coverage do not prove causal claims; human review is required. See the stage branch's `AE-32C-Phase-E3-Source-Fidelity-and-Round-Robin.md` for full assurance semantics.

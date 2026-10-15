# AE-16 / G9.18 — Operational Execution Evidence (Observation Only)

## Mission and scope

Implement the **original Audit Engine Modes A and B** groundwork: distinguish declared
job/step states from nested test outcomes; explicitly account for mandatory check
coverage; model producer–consumer artifact contracts; preserve missing artifacts as
incomplete evidence; optionally reuse AE-09's source-bound traceback correlation.

AE-16 **does not authenticate GitHub-run metadata or prove a test executed**. Its
input is a supplied, untrusted execution declaration. A success assertion is only a
**declared outcome**; even a successful, replayed report has the assurance value
`consistent_declared_observations_unattested`. No verified findings are produced.
An independently authenticated run-identity source is future work. Never interpret
this output as a GitHub security attestation or an established root cause.

## Architecture

- **Canonical `SemanticGraph`**, not a second graph engine: job, step, check,
  nested-test, required-check, and artifact nodes, with labeled occurrence edges.
- All names are **scoped and occurrence-specific**. `test:job:step:check:test`
  cannot be confused with another test of the same name in another job.
- **Expected failing test != failed workflow step**. An observed failed test whose
  expected result is failed can coexist with a declared successful check.
- **Missing mandatory checks are never clean**: `required_check_not_executed`,
  `required_check_not_satisfied`, and `no_required_check_contract` become explicit issues.
- **Producer vs consumer**: same artifact ID, relative producer and consumer paths,
  SHA-256 of actual supplied bytes, required producer job dependency/order. Missing
  files and differences are explicit. Source-copy equality does **not** prove the
  original job actually produced the file.
- **AE-09 integration** optionally calls its bounded `build_report()` on supplied
  step logs and the already verified AE-01 source generation. Traceback paths
  remain bounded review hypotheses, never causal proof.
- **Publication**: reuse AE-01 atomic/locked last-attempt helpers; seal immutable
  generations and replay the entire bounded declaration and supplied evidence.
- No source or project code is executed; this is parser-only observational analysis.

## Input contract

Supply a canonical JSON file (`audit_engine.semantic_audit.ae01.publication.canonical()`),
with keys exactly `schema`, `run_id`, `reported_status`, `jobs`, `requirements`.

```
{
  "schema": "ae16/declared_execution/v1",
  "run_id": "a-run",
  "reported_status": "success",
  "jobs": [
    {"id":"build","status":"success","needs":[],"steps":[
      {"id":"tests","status":"success","exit_code":0,"log":"logs/build.txt",
       "checks":[{"id":"unit","status":"passed","tests":[
          {"id":"positive","expected":"passed","observed":"passed"},
          {"id":"negative_fixture","expected":"failed","observed":"failed"}
       ]}],
       "produces":[{"id":"unit-output","path":"producer/out.json"}],
       "consumes":[]}
    ]},
    {"id":"consumer","status":"success","needs":["build"],"steps":[
      {"id":"verify","status":"success","exit_code":0,"log":"logs/verify.txt",
       "checks":[{"id":"artifact","status":"passed","tests":[
          {"id":"hash_match","expected":"passed","observed":"passed"}
       ]}],
       "produces":[],
       "consumes":[{"id":"unit-output","path":"consumer/out.json"}]}
    ]}
  ],
  "requirements": [
    {"id":"required-unit","job":"build","step":"tests","check":"unit"},
    {"id":"required-artifact","job":"consumer","step":"verify","check":"artifact"}
  ]
}
```

The JSON above illustrates the contract but is whitespace-formatted for reading;
re-serialize canonically before using it. `evidence_root` contains relative log and
artifact paths. No absolute paths, traversal, symlinks, special files, or files over
budget are admitted. Missing files result in explicit incomplete observations rather
than false clean claims. Other unsafe types abort publication.

## Verification and return codes

```
python tools/run_ae16_operations.py --declaration /tmp/run.json \
  --evidence-root /tmp/input-evidence --output-root /tmp/output
python tools/run_ae16_operations.py --declaration /tmp/run.json \
  --evidence-root /tmp/input-evidence --output-root /tmp/output --verify-only
```

Optional `--ae01-output` and `--source-root` must be provided together. CLI return
codes: `0` = internally consistent supplied declaration with **no runtime
attestation**, `3` = incomplete or inconsistent supplied evidence, `4` = cannot
admit/verify supplied evidence. None of these represent independently verified
GitHub success or scientific/program runtime correctness.

## Explicit remaining limitations

1. **Authenticity**: no authenticated GitHub run/job/step ID or signing policy;
   the manual input can lie about outcomes or tests run. Complete assurance is impossible.
2. **Required-test oracle strength**: declared nested test results are validated for
   consistency, not checked against a trusted JUnit parser or independent test oracle.
3. **Executed file production**: matching bytes show the provided producer and
   consumer artifacts match, not that a particular program produced them.
4. **Complex execution**: parallel job scheduling uses declared `needs` ordering;
   no reconstruction of all conditional GitHub Actions semantics, retries,
   `continue-on-error`, matrix fan-out, or implicit dependencies.
5. **Resource bounds**: 32 jobs, 128 total steps, 512 checks, 256 requirements,
   512 artifact declarations, 2 MB per supplied file, 24 MB total unique evidence.
6. **Security**: a local filesystem reader cannot fully eliminate concurrent
   adversarial file substitution without an OS-level isolation boundary.
7. **Canonical JSON**: supplied manifest must be canonical; version upgrades
   require an explicit adapter, never silently ignored unknown keys.
8. **Evidence persistence**: the generation stores hashes, observations and graph,
   not full copies of input logs/artifacts. Independent replay requires the original
   input bytes; no credentials/exception text are stored in the report.
9. **Not AE-17**: no automatic hypothesis generator, experiment executor, or autonomous
   verifier authority is introduced.

## Validation

Selected G9.18 GitHub suite includes positive and negative fixtures for expected
nested failures, absent required checks, false success, wrong artifact bytes,
missing dependency, symlinks/FIFO, path traversal, tampering, stale last attempts,
and optional AE-09 correlation, plus AE-09/AE-15/AE-13 regressions. **Tests intentionally
are not run locally for this release at the user's request.** GitHub must supply
actual evidence before acceptance.

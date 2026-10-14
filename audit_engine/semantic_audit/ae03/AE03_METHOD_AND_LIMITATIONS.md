# AE-03 — Evidence-Bound Test-Oracle and Mutation Effectiveness

## Objective / claims / empirical design

**Goal.** Assess a bounded question: *do the selected trusted tests distinguish a designated, reproducible source mutation from the original?* This is an additional test-oracle observation, not an assessment of all test effectiveness, formal correctness, or scientific validity. The intended next reviewer action is to inspect survivors and missing coverage; AE-03 never patches the development branch.

**Experiment design.** The source root, source files, selected test files, supported operators, mutant budget and per-trial timeout are explicitly defined. The runner first copies a bounded repository workspace to a disposable directory, executes the unchanged baseline tests, then executes each supported mutant in a separate fresh copy. Any nonpassing baseline blocks mutant execution; no denominator is formed. The baseline, source/test SHA-256 records, workspace manifest digest, operator occurrence and mutated-byte SHA-256, process outcomes and provenance are saved. `record_sha256` seals canonical JSON serialization for accidental modification detection, **not cryptographic authentication by a trusted signing key**.

## Mutation operator model

Supported operators are six ordinary binary comparisons: `== ↔ !=`, `< → >=`, `<= → >`, `> → <=`, `>= → <`, `!= → ==`. AST traversal only accepts `Compare` expressions with exactly one comparator. The actual operator token must be independently found in the tokenizer interval between left-operand end and right-operand start. Chained comparisons, rich Python semantics, arbitrary runtime dispatch and unhandled encodings are explicitly outside scope. Each mutation has a content-addressed ID from path, SHA-256 source bytes, UTF-8 tokenizer position and exact operator edit. Test quality **cannot** be inferred from site count.

## Outcome logic

- **Killed:** baseline passed, mutant process returned pytest exit status 1. This means selected tests rejected the altered execution; failure may be an exception/setup failure, not necessarily a successful assertion oracle.
- **Survived:** baseline passed, mutant test process returned status 0. May be an equivalent mutant, unexecuted path, weak assertion or another limitation; not proven software defect.
- **Invalid mutant:** altered source fails Python AST parsing. Excluded from score.
- **Runner error:** pytest returned a nonzero status other than 1, such as collection, usage or infrastructure error; excluded from score.
- **Timeout:** per-trial deadline elapsed; excluded from score.
- **Inconclusive baseline:** unmutated selected tests fail or time out, so no mutant score is computed.
- **Partial experiment:** site budget exhausted, any mutant unscored, or authenticated AE-02 impact plan requires full review. Never report complete in these cases.
- **Complete for selected sites:** all supported occurrences in the *explicitly selected source files* were evaluated without unscored outcomes, and the baseline passed. This is not whole-repository completeness.

`mutation_score = killed / (killed + survived)`, only if the denominator is nonzero. Do **not** interpret this as precision, recall, Bayesian confidence or a general-purpose numerical test-quality rating. Correlation, equivalent mutants, limited operator family and fixture representativeness prevent such interpretation. Statistical inference would require a justified sampling plan and oracle adjudication.

## Evidence trust boundaries

1. The **source/test/workspace digests** allow live-repository byte rechecks; excluded generated/cache directories are enumerated in `workspace_manifest.exclusions`. External installed dependencies and operating-system state are **not** hashed.
2. `verify_record(..., replay=False)` checks canonical self-hash, current source/workspace bytes, independently rediscovers mutation sites, counts, bounded coverage and reported assurance. It **does not verify claimed subprocess outcomes**.
3. `verify_record(..., replay=True)` recomputes the experiment in fresh workspaces and compares status/outcome classes. A flaky test can change the outcomes, and such a disagreement fails verification. Replay does not establish equivalence of arbitrary runtime behavior.
4. With AE-02 integration, **do not trust an arbitrary impact-plan JSON**. The `verified_impact` constructor independently re-derives AE-02.1 from named sealed AE-01 generations. A detached record's impact evidence is only re-verified if the generation roots are re-supplied to the verification CLI.
5. The runner copies source/test files into disposable paths but **is not a security sandbox**. Python tests can access network, credentials, filesystem and subprocesses. Use trusted code only within an appropriately isolated CI host with minimal privileges. No arbitrary repository checkout should be executed solely to produce a score.
6. `record_sha256` is a consistency checksum, not a digital signature or third-party attestation. GitHub evidence verification is a separate required acceptance step.

## Reproduction (manual only)

```bash
python -m audit_engine.semantic_audit.ae03 \
  --repo /path/to/trusted/corpus \
  --source pkg/core.py --test tests/test_core.py \
  --max-mutants 10 --timeout 30 \
  --output /tmp/ae03-report.json

python -m audit_engine.semantic_audit.ae03 \
  --repo /path/to/trusted/corpus \
  --verify-report /tmp/ae03-report.json --replay
```

Optional generation binding accepts `--before-ae01 /path/to/outputA --after-ae01 /path/to/outputB`; both must contain complete, verifiable AE-01 artifacts. The JSON report must be written **outside** the source repository. A CLI exit of `0` means complete *within the selected mutation scope*; `3` means partial/inconclusive; `4` means execution or evidence-boundary error.

## Methodological positioning

This bounded design is informed by Barr et al., *The Oracle Problem in Software Testing: A Survey* (2015), Just et al., *Are Mutants a Valid Substitute for Real Faults in Software Testing?* (2014), and goal/question/metric audit framing. Citing these works **does not** establish conformance, validated measurement precision, or transferability of fixture results to real-world FEM algorithms. Independent fixture expectations are used to prevent a self-certifying auditor.

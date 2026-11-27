# AE-35 — Deterministic AE-32D Candidate Verification Against Immutable Source

**Status:** Implemented in source; exact-head Actions validation pending  
**Branch:** \`stage1/section-uuids\`  
**Scope:** AE-32D provider-interface candidate only

## 1. Finding

AE-34 restricted the verifier to one fixture, but it still analyzed the current checkout rather than the historical source SHA recorded in the case. Its earlier AST checks were also too broad: any \`total_calls\` access in the extractor and any \`self.calls\` assignment in the adapter module could satisfy them.

## 2. Implementation

The workflow now checks out the verifier at the exact Stage1 event revision and the candidate source at immutable commit \`afcb1cba064de6f3d680f6be3085a365c6687c7b\`. The verifier checks the candidate checkout's Git HEAD before reading or executing it. The source root is supplied by a fixed workflow environment setting, not a workflow-dispatch input or CLI argument.

AST checks now establish the typed \`ProviderAdapter\` parameter, direct \`provider.total_calls\` access, counter initialization and increment inside the actual adapter class, absence of inheritance and dynamic attribute hooks, direct factory construction, the entry-point call path, and the fixture test call. The prior lexical checks remain supplemental diagnostics.

The fixture is executed only after structural checks pass. The expected result is a nonzero exit with an AttributeError naming \`ProviderAdapter.total_calls\`. A timeout, launch failure, different exception, or successful execution does not count as reproduction.

## 3. Adversarial tests

New tests reject unrelated \`wrapper.total_calls\` access, a dynamic \`__getattr__\` hook, and a \`self.calls\` assignment in an unrelated class. Existing path/symlink, environment, isolated-mode, timeout, and CLI-argument tests remain.

## 4. Machine adjudication boundary

A passing report may label this one fixture \`confirmed_fixture_runtime_defect\`. This means only that the pinned source has the declared consumer/provider mismatch and its entry point reproduces the corresponding runtime exception under the controlled process environment.

It does not establish general Audit Engine accuracy, a provider ranking, benchmark-wide ground truth, or primary benchmark eligibility. The report continues to set \`primary_benchmark_eligible=false\` and \`human_independent_adjudication=not_performed\`. Human review is not a dependency for this deterministic software workstream, but no review is falsely claimed.

Python isolated mode and a reduced environment are not an operating-system sandbox; the child retains the hosted runner's filesystem and network capabilities. The workflow grants only \`contents: read\` and supplies no application secrets.

## 5. Acceptance and next work

The Stage1 push workflow runs the adversarial tests and immutable-source verification automatically. Acceptance requires the exact-head workflow run to pass; a commit alone is not execution evidence.

Next deterministic tasks are schema validation for case/rubric/plan records, case-to-source identity checks, machine-verifiable negative and ambiguous fixtures, and a scorer that rejects pending, stale, disputed, or provenance-invalid cases. An LLM may propose structured explanations, but an LLM judge alone remains insufficient ground truth.

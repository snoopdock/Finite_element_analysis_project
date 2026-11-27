# AE-44 G0 — Source-level executor mapping

**Status:** source inspection complete; no adapter implemented  
**Branch:** `stage1/section-uuids`  
**Inspected revision:** `stage1/section-uuids` as of AE-44 design commits  
**Purpose:** identify actual A/B/C execution entry points before wiring trial workflows

## 1. Result

The repository has substantial components that could participate in the experiment, but the current AE-32D condition definitions do not yet map one-to-one onto three validated, comparable executors.

| Component | Verified entry point / behavior | What it does not establish |
|---|---|---|
| AE-32A | `audit_engine.semantic_audit.ae32a.audit.audit_repository`; CLI `python -m audit_engine.semantic_audit.ae32a` | A deterministic architecture/wiring inventory is not, by itself, a case-level defect diagnosis or an equivalent diagnostic outcome for the AE-32D task statements |
| AE-32B | `RepositoryEvidenceTools`; CLI `python -m audit_engine.semantic_audit.ae32b --repo-root ... --request-json ...` | The CLI accepts one bounded evidence-tool request per process. It does not run a multi-step audit or emit a normalized defect/no-defect/abstain decision |
| AE-32C | `RepositoryInvestigator`; CLI `python -m audit_engine.semantic_audit.ae32c --problem ...` | It is a provider-backed interactive investigator, not the missing deterministic A baseline. It uses AE-32B evidence tools and includes graph tools under its investigation policy |
| AE-32C live evaluation | `audit_engine/semantic_audit/ae32c/live_evaluation.py` | It is an opt-in live comparison for the controlled provider-interface incident. Its baseline is a provider response and its graph-assisted arm is an LLM investigation; it is not the AE-32D A/B/C design |
| AE-32C batch evaluation | `audit_engine/semantic_audit/ae32c/batch_evaluation.py` | Offline operational assessment of AE-32C comparison artifacts; it explicitly does not assess diagnostic truth |

## 2. Detailed findings

### A — deterministic baseline

AE-32A is documented in source as a deterministic, report-only architecture and wiring audit. It inventories source-level relationships without importing or executing target modules. Its outputs concern components, tests, production consumers, workflow invocation, LLM transport, graph API use, tool loops and measurement.

That is useful deterministic evidence, but the current AE-32D case tasks ask an investigator to examine a particular incident, separate observations from hypotheses, assess counterevidence and choose an uncertainty level. No inspected entry point establishes that AE-32A produces that case-level diagnostic decision. Treating its architecture report as a `defect` or `no_defect` outcome would be an invalid semantic conversion.

The protocol's A condition therefore needs a separate deterministic case-audit contract: rules and ordinary source-search operations that consume the case task and emit an explicit structured diagnostic decision, or a revision of the benchmark question to measure a different outcome. Neither should be silently assumed.

### B — graph retrieval

AE-32B exposes a bounded read-only tool catalog, including lexical source search, exact source reads, symbol search, graph-neighbor/path queries, related-test discovery and workflow context. Its graph is a source-level projection built from AE-32A inventory and static relationships. The docs explicitly disclaim runtime-call-graph completeness and semantic retrieval beyond bounded lexical search.

The component is suitable as an evidence-tool substrate for B, but a one-shot invocation is not a complete B condition. A B runner must define a fixed deterministic retrieval policy (query plan, budgets, ordering, stopping and output assembly) and produce a case-level report/decision without an LLM. It must record source-manifest and graph fingerprints. The current code does not yet provide that end-to-end B runner.

### C — bounded LLM investigation

AE-32C's `RepositoryInvestigator` consumes the AE-32B evidence tools and a provider adapter. Its CLI builds a provider from configured provider/model/environment settings, constructs bounded `InvestigationLimits`, runs the investigator and emits a report. The live-evaluation module adds explicit opt-in execution and records operational comparison data.

This is the closest existing component to C, but the current live-evaluation path is an AE-32C provider-vs-graph-assisted comparison for one controlled incident. It must not be treated as an AE-32D C runner until it is adapted to the exact case manifest, exact source pin, paired A/B configuration, AE-32D outcome schema, explicit C-specific authorization, and immutable artifact bundle.

## 3. Consequence for the experiment design

The current A/B/C labels describe desired treatments, not proven executors. The valid implementation sequence is:

1. Define a deterministic case-audit contract and decide whether AE-32A contributes evidence or is outside the primary diagnostic baseline.
2. Implement a deterministic B retrieval runner over AE-32B. It must use fixed retrieval policy and must not invoke an LLM.
3. Adapt AE-32C as C only after A and B are frozen; C must reuse B's source and graph snapshot identity and add only the bounded provider investigation.
4. Build the artifact capture and normalizer around the real output shapes after those runners exist.
5. Only then run paired trials and feed actual outcomes to the AE-42 scorer.

A and B must not be populated by translating AE-32A/AE-32B operational statuses into diagnostic outcomes. The AE-32C batch evaluator must not be reused as a diagnostic scorer.

## 4. Safety and experiment integrity

- No live provider was invoked during this inspection.
- No provider secret was accessed and no cost was incurred.
- No source case, ground-truth label, registry record or primary-eligibility flag was changed.
- No trial output was generated.
- No workflow dispatch or automatic provider trigger was added.
- The graph backend remains a task-specific computation option; no universal backend ranking is introduced.

## 5. G0 disposition

**G0 is partially complete:** actual component entry points and semantic gaps have been identified. It is not complete for adapter implementation because the deterministic A case-audit contract and the deterministic B retrieval policy remain undefined.

**Next work:** specify and test those two deterministic contracts first. Do not create a workflow that advertises A/B/C execution until the underlying condition runners can produce explicit, case-bound diagnostic reports.

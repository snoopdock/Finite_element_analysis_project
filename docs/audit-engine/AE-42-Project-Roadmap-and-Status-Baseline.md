# Audit Engine consolidated roadmap and status baseline

**Baseline revision:** `c58f84ef3ec9e24c065cf96d99499d67b5876f2e`  
**Branch:** `stage1/section-uuids`  
**Review date:** 2026-11-27  
**Status:** project-level reconciliation; not a claim that all listed capabilities are implemented.

## 1. Purpose and governing rule

This document reconciles the Audit Engine roadmap across the architecture notes 001–006, the AE-01–AE-41 records, the E.8/M0–M7 graph-backend work, and the milestone decisions captured in the project conversations. It is the continuity record for work proceeding after AE-41.

The Audit Engine is a deterministic, evidence-producing repository-software auditor. It is reactive and externally activated, not an autonomous goal-seeking agent. Its conclusions must be traceable to immutable source state, declared analysis contracts, and inspectable evidence. LLMs may provide bounded interpretation; they do not become evidence authorities. Solvers establish properties of their encodings, not automatically of the repository. Remediation is separately constrained by policy and authorization.

Implementation work remains on `stage1/section-uuids`. Do not create an implementation branch and do not modify `main`.

## 2. System boundary (AE-33)

**Audit Engine:** audits the repository as functioning software: source, graph construction, adapters, dependencies, interfaces, workflows, tests, persistence, provenance, execution, security, and operational behavior.

**Future Supervisor:** audits the scientific/documentary content produced by the repository: FEM claims, equations, assumptions, numerical evidence, propositions, and semantic validity. This is deferred and is not part of the current Audit Engine acceptance scope. G5 numerical FEM evidence belongs to that future Supervisor.

The graph can establish represented relationships; it cannot certify that the representation is complete. A model response is interpretation, not ground truth. A solver result applies to its exact encoding. A remediation plan is not an authorized patch. These boundaries must remain explicit.

## 3. Parallel workstreams and status

| Workstream | Established position | Open obligations |
|---|---|---|
| Graph-native architecture (Note 001; E.8; M0–M7) | Five backend adapters have native-operation evidence for recorded operations; M7.4 seeded-topology acceptance and M7.5.30 cross-layer audit are recorded as validated | Task/backend suitability is still insufficiently evidenced; Graphify recorded all 20 task/backend outcomes as insufficient evidence. Preserve G4 snapshot/race limitations and M7.5 package-persistence/consumer boundary |
| Activation and incremental recomputation (Note 002) | Architectural contract is defined through iteration 15 | No inference of implementation from design. Event delivery, snapshot capture, delta reconstruction, incremental evaluation, and publication each need separate evidence |
| Pluggable LLM integration (Note 003; AE-31/32A/32B/32C) | Provider-neutral harness, graph-grounded evidence tools, bounded investigation and active provider policy have been developed | Per-provider/model compatibility, provenance, failure/abstention semantics, evidence support and live evaluation remain distinct acceptance obligations |
| Remediation decisions (Note 004) | Architecture for finite alternatives, explicit criteria, hard constraints, quantified decisions and patch verification | Full candidate generation, conflict-aware composition, decision records, stale-plan checks and authorized patch transactions remain future implementation obligations |
| Formal solver portfolio (Note 005) | Solver roles and evidence boundaries are architecturally defined | SAT/SMT, CP-SAT/MILP, Lean and counting capabilities require task-specific encodings, certificates, correspondence checks, budgets and native status preservation |
| Self-examination and termination (Note 006) | Frozen-kernel / mutable-engine architecture and termination vocabulary are defined | Trusted computing base, authorization, ranking functions, cancellation, cycle detection and independent improvement evidence require implementation and acceptance |
| Audit-quality evaluation (AE-32D; AE-33–AE-41) | Six machine-verified candidates, immutable evidence ledger, structural/runtime verifiers and non-promotion gates | Gold adjudication, rubric/pilot freeze and primary benchmark eligibility remain open; exploratory evaluation can proceed separately |

## 4. Graph-native roadmap: E.8 and M0–M7

The graph-backend work is not a speed contest. Backends are alternative computation options selected for relevance to a particular audit operation.

The milestone progression was M0 architecture baseline, M1 adapter contract, M2 repository graph-tool routing, M3 SciPy, M4 python-igraph, M5 graph-tool, M6 isolated SNAP, and M7 task-oriented evaluation/assurance. The recorded M7 sequence includes M7.1 integrity-cost smoke, M7.2 bounded traversal, M7.3 detached evidence dossier, M7.4 seeded-topology acceptance, and M7.5 epistemic/provenance/cross-layer assurance through M7.5.30.

Native operation evidence does not imply universal suitability. The Graphify assessment found all five backends functional for the operations tested but recorded 20 task/backend suitability outcomes as insufficient evidence. Backend selection must be operation-specific. Keep SNAP's isolated CPython 3.9/SNAP 6.0 boundary, SciPy's semantic edge-occurrence side channel, and projection-validation cost visible. G4 still has repository-wide atomic snapshot and filesystem race/aliasing limitations.

M7.5.30 validated the strict cross-layer package producer and its regression suite. It did not establish a universal persistent package store or general consumer gate; those were deliberately deferred pending a demonstrated consumer.

## 5. Note 002 — activation and incremental recomputation

The intended operating model is **event-driven at the boundary and dataflow-driven in the interior**. The engine is externally invoked by a concrete event. It does not select goals or autonomously plan new audits.

The note's correctness obligations are independent:

1. **Notification delivery:** event observed, or loss/gap/overflow detected and recovered.
2. **Coherent snapshot capture:** all analyzed inputs belong to one identified source state.
3. **Delta reconstruction:** exact base and target identities; event lists are hints, not authoritative source state.
4. **Incremental evaluation:** conservative dependency closure and supported rule fragment; otherwise rebuild or mark non-authoritative.
5. **Publication:** graph, findings, coverage, manifest and status form one coherent generation; late stale runs cannot overwrite newer results.

Further requirements carried forward from iterations 10–15:

- Duplicate/reordered/coalesced events must be idempotent; gaps, overflow and API truncation require authoritative reconciliation or incomplete status.
- Modification time and size are hints, not content identity. Hash/fingerprint strategy must cover correctness-critical inputs.
- Cache keys include every result-affecting input: source tree, build/preprocessor settings, parser/extractor/schema versions, rules, dependency graph, policy, external facts, baseline and normalization/evaluator semantics; model/solver settings when their outputs are cached.
- Delta application requires proof that the current graph matches the declared base. Deletions, negation, recursion, aggregation, alternate derivations and global rules require explicit semantics or conservative rebuild fallback.
- Define determinism per pipeline stage and equality semantics for incremental/rebuild parity.
- Clean rebuild is a differential reference within a declared domain, not independent semantic truth; pair it with independent expected fixtures to guard common-mode defects.
- Run IDs and source/configuration manifests are immutable. Publication uses a freshness/generation guard, not “last task to finish wins.”
- Repair plans are bound to an exact base snapshot and revalidated immediately before staging/application.
- Performance claims (including the one-file/3,000-file sub-second target) are hypotheses until measured with workload, hardware, cache state, parser/build cost, rule mix, p50/p95/p99 and fallback frequency.

**Status:** design contract only unless a specific implementation and acceptance record says otherwise. The next architecture-level work should audit existing activation, cache, delta and publication code against this contract rather than assume it exists.

## 6. AE-32D benchmark and evidence hierarchy

The benchmark distinguishes deterministic baseline (A), baseline plus graph retrieval (B), and graph retrieval plus bounded LLM investigation (C). Optional claim-level assessment (D) requires separate validation. Conditions must use the same pinned source snapshots and declared policy. Preserve failures, abstentions, missing outcomes and denominators.

The pilot target is 6–10 adjudicated cases, then expansion toward 30–50 only after annotation/scoring reliability is established. The current six-case matrix reaches only the numerical lower bound; it does not meet adjudication, rubric approval or freeze gates.

Evidence levels must not be conflated: source observation; structural/static verification; runtime reproduction; repository integration verification; machine-derived provisional reference; independent adjudication; primary benchmark eligibility.

## 7. AE-33–AE-41 status

- **AE-33:** formal Audit Engine / Future Supervisor boundary accepted.
- **AE-34–AE-35:** execution-boundary hardening, immutable candidate source pinning, structural and runtime verification.
- **AE-36:** machine-verification metadata and benchmark non-promotion gate.
- **AE-37:** negative control and dynamic-contract ambiguity controls.
- **AE-38:** deterministic outcome classification.
- **AE-39:** three-case machine-verifiable matrix expansion.
- **AE-40:** exception-flow and stale-data-flow defect families.
- **AE-41:** machine-verification evidence ledger linking six cases to immutable sources, verifier revisions, runs, artifacts and outcomes.

The six cases remain candidates. All have pending ground-truth labels, no independent adjudication, and `primary_benchmark_eligible=false`. This is intentional and must not be weakened by later exploratory scoring.

## 8. Continuation plan

### Immediate: complete the AE-41-to-AE-42 handoff

1. Preserve the evidence hierarchy and non-promotion invariant.
2. Create a separate machine-reference registry for the six pinned cases. Each entry records the fixture-contract basis and immutable source/ledger linkage.
3. Keep all benchmark `ground_truth.label` values pending and all primary eligibility flags false.
4. Add a deterministic validator and schema for the registry.
5. Add an exploratory trial format for A/B/C outputs with explicit case, condition, run/config identity and outcome states (including failure, missing and abstain).
6. Add an exploratory scorer with raw denominators and detection/false-positive/abstention metrics. It must label its results exploratory-only and must not emit a primary benchmark score.
7. Test adversarial promotion attempts, missing/duplicate cases, unknown conditions, missing trials, failed trials, abstentions and reproducibility.
8. Record all validation runs and artifacts in the AE-42 document and README.

### Revised continuation after AE-43 readiness audit

- **AE-43 — Exploratory trial integration:** remains blocked until qualifying raw A/B/C outputs exist. It will import and normalize actual immutable artifacts, then use the AE-42 scorer.
- **AE-44 — Controlled A/B/C trial-generation design:** design the paired execution contract, provenance envelope, condition-adapter boundaries, manual authorization policy, artifact layout, failure/retry semantics and acceptance tests. Design recorded; no condition runner or trial output is claimed.
- **G0 — Executor source audit:** identify the real deterministic baseline and graph-retrieval call paths before implementing adapters. This is the next implementation task.
- **G1–G6 — Trial execution/capture gates:** schemas and offline verification, A adapter, B adapter, C authorization/adapter, and paired experiment assembly. These are not yet implemented.

The AE-44 design is recorded in [AE-44 Controlled A/B/C Trial Generation Design](AE-44-Controlled-ABC-Trial-Generation-Design.md). Do not advance AE-43 scoring or later quality/robustness milestones until actual trial artifacts exist and pass provenance validation.

### Parallel architecture backlog (not to be silently displaced by AE-42)

- Audit Note 002 activation/snapshot/delta/cache/incremental/publication implementation against its iteration-15 acceptance contract.
- Close graph task/backend suitability with task-specific evidence; do not rank backends universally.
- Preserve M7.5 provenance/currentness and package-consumer boundaries.
- Continue provider/model qualification and evidence-supported investigation testing.
- Implement remediation decisions and exact-base patch verification only after finding/evidence gates.
- Implement formal solver portfolio with encoding/certificate/correspondence boundaries.
- Implement self-examination only behind a frozen trusted kernel and enforceable termination.
- Keep Future Supervisor deferred and separately governed.

## 9. Operating constraints

- Work only on `stage1/section-uuids`; do not create a new implementation branch.
- Do not modify `main`.
- Use GitHub Actions for repository validation; no local run is required from the user.
- Tests must examine structure, behavior, failure modes and negative controls, not only simple input/output.
- Do not wait for human reviewers to continue software implementation, but do not misrepresent machine references as gold adjudication.
- No production publication or automatic security remediation without explicit authority.
- Every claimed milestone completion must cite its actual successful workflow run and immutable revision.

## 10. Baseline caveats

This reconciliation is based on the project conversation record, uploaded Notes 001–006 (Note 002 supplied with this review), and the Stage1 records available at baseline revision. It is a roadmap/status index, not a fresh exhaustive source-code audit of every subsystem. Where implementation evidence is absent, the status is explicitly architectural or open rather than presumed complete.


## 11. AE-42 completion update

AE-42 was implemented and validated after this baseline was first committed.

- Successful workflow: [AE-32D run 46021888511](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46021888511).
- Validation revision: `31fdc1e19956769bf478b02674daa8646a448fae`.
- Artifact ID: `15208357689`; SHA-256: `37a9f64404c16a63f4498a7d63513d2627ea6434083465eed016447e1f0b472f`.
- Provisional registry validation and five exploratory-boundary tests passed, alongside the existing AE-32D verification stages.
- All six ground-truth labels remain pending; primary eligibility remains false. No actual A/B/C performance results were generated.

AE-42 is validated for its declared scope. Proceed to AE-43 exploratory integration only after identifying real retained or explicitly generated trial outputs. AE-43–AE-46 remain proposed and require repository roadmap reconciliation before formal numbering.

## 12. AE-43 readiness gate

AE-43 is the correct next workstream, but its input prerequisite is not met. The tracked AE-32D inventory has no actual A/B/C trial-output dataset. The existing AE-32C batch assessor measures protocol/evidence completion and explicitly leaves diagnostic accuracy not assessed; its provider baseline is not AE-32D condition A. The separate FEA provider benchmark evaluates document-generation runs, not the six repository-audit cases. Neither may be mechanically converted into AE-32D diagnostic outcomes.

The AE-43 readiness audit is recorded in [AE-43 Exploratory Trial Integration Readiness](AE-43-Exploratory-Trial-Integration-Readiness.md). Next: obtain a qualifying immutable A/B/C bundle through retained outputs or an explicitly authorized manual execution, then build an offline importer/normalizer. Do not auto-dispatch providers, fabricate trials, or infer defect labels from protocol completion.


## 13. AE-44 controlled trial-generation design

AE-44 defines a paired A/B/C execution contract but does not claim execution capability. It requires exact case/source/task/configuration identity; A/B/C differ only by their declared treatment; B/C bind graph snapshot and retrieval provenance; C additionally binds provider/model/prompt/tool revisions and hard budgets. Outcome normalization must consume an explicit structured decision, never infer a diagnosis from exit status, protocol completion, citation count, coverage or confidence.

The design requires manual A/B dispatch and a separate explicit authorization gate for C. No push, pull-request, schedule or default workflow event may invoke a provider. A/B must receive no provider secrets. Failed, timed-out, cancelled, missing and abstaining trials remain visible; retries receive new trial identities. Raw reports and diagnostics are immutable and digest-verified.

**Current status:** design only. No A/B/C condition was executed, no provider was called, and no cost was incurred. The next task is G0: source-level mapping of the actual deterministic-audit and graph-retrieval entry points. Do not invent command names or wire a workflow until those call paths are verified.


### G0 source-mapping update

The source-level mapping is recorded in [AE-44 G0 Executor Source Mapping](AE-44-G0-Executor-Source-Mapping.md). It confirms that AE-32A is a deterministic architecture/wiring inventory, AE-32B is a bounded evidence-tool interface (including graph queries), and AE-32C is the provider-backed investigator. None can be mechanically substituted for all three AE-32D conditions: A still lacks a case-level deterministic diagnostic executor; B still lacks a fixed deterministic retrieval policy and case-level decision output; C needs adaptation to the pinned AE-32D case/configuration and separate authorization/artifact contract.

**G0 status: partially complete.** Actual component entry points and semantic gaps are identified. The next step is to specify the deterministic A diagnostic contract and deterministic B retrieval policy. No A/B/C workflow, provider invocation, or trial record has been created.

# AE-32C M7.5.1 — Epistemic vocabulary and state contracts

**Status:** M7.5.1 initial contract, implemented as immutable Python value objects  
**Contract:** `ae32c/m7-5-epistemic-contracts/v1`  
**Branch:** `stage1/section-uuids`  
**M7.4 baseline:** `69a4afc673ab66a0e6c81ee487fa9fbdedc804d6`  
**Authority:** descriptive evidence contracts only; no decision-gate authority

## 1. Purpose and boundary

M7.5 addresses a specific audit-engine limitation: evidence can be faithfully stored while the engine remains unaware that relevant sources were never supplied, observations failed, extraction was partial, a completeness assumption was unjustified, validators share a failure dependency, or an old conclusion has become stale.

M7.5.1 establishes vocabulary and immutable record contracts before adding persistence, inference, defeater resolution or decision integration. It is deliberately narrower than a general epistemic logic.

This tranche does not:
- assert that all unknown unknowns can be discovered;
- select Belnap–Dunn/FDE, Bayesian networks, Dempster–Shafer, default logic or an argumentation solver as the universal reasoning formalism;
- turn a numeric confidence value into truth or authority;
- treat an empty graph query as a negative finding;
- allow an LLM, solver or backend to change a deterministic gate;
- claim that provenance alone establishes correctness or completeness.

## 2. Relationship to existing repository mechanisms

The repository already contains:
- `analysis/epistemic_state.py` and `core/epistemic_state_store.py`, which hold descriptive status, evidence-strength, literature-agreement and model-confidence fields for the earlier knowledge-graph pipeline;
- high-assurance proof/validation records and the resource-neutrality decisions ADR-072, ADR-075 and ADR-078;
- source-bound graph snapshots, LFS/submodule accounting, rule coverage and finding provenance in AE-32C.

M7.5.1 does not silently redefine or remove those existing contracts. The earlier epistemic-state helper is not sufficient as the new audit-engine assurance contract: it does not bind an assessment to an exact source snapshot, represent a scoped completeness claim, preserve assertion-level support and challenge records, or model a knowledge gap and its resolution evidence.

The new package is `audit_engine.semantic_audit.epistemic`. It is additive and currently has no persistence or runtime decision integration.

## 3. Vocabulary

### 3.1 Evidence assertion

An evidence assertion is a source-bound statement that either supports, challenges, or is neutral toward a proposition. Assertions are append-only observations at this layer. Two assertions with opposing polarity remain two records; they are not merged into a single truth value.

Each assertion identifies:
- assertion and proposition IDs;
- polarity (`SUPPORTS`, `CHALLENGES`, `NEUTRAL`);
- one or more evidence references;
- scope and method IDs;
- observation time;
- limitations and invalidation triggers.

The contract does not decide whether the assertion is authoritative, sufficient, independent, current or semantically correct. Those are later evaluation obligations.

### 3.2 Evidence reference

An evidence reference binds an evidence ID to a source snapshot, producer, method, observation time and optional artifact digest, source URI and independence group. An independence-group label is metadata, not proof of statistical or causal independence.

A SHA-256 digest establishes byte identity only under the relevant acquisition assumptions; it does not authenticate who supplied the bytes or establish their completeness.

### 3.3 Knowledge gap

A knowledge gap is an explicit record that a required or potentially relevant observation is absent, unavailable, unsupported, incomplete, stale, contradictory or otherwise insufficiently established.

Gap kinds in v1:
- `SOURCE_NOT_SUPPLIED`
- `SOURCE_UNAVAILABLE`
- `COLLECTION_NOT_ATTEMPTED`
- `COLLECTION_FAILED`
- `UNSUPPORTED_SOURCE`
- `PARTIAL_EXTRACTION`
- `SCOPE_EXCLUDED`
- `RESOURCE_LIMIT`
- `STALE_EVIDENCE`
- `CONFLICTING_EVIDENCE`
- `INDEPENDENCE_NOT_ESTABLISHED`
- `UNKNOWN_CAUSE`
- `OTHER`

Investigation states:
- `OPEN`
- `INVESTIGATING`
- `BLOCKED`
- `RESOLVED`
- `ACCEPTED_RESIDUAL`

A gap may be `RESOLVED` only when resolution evidence is attached. An `ACCEPTED_RESIDUAL` gap requires a recorded disposition and an identified authorizing authority. Budget exhaustion is not resolution. `UNKNOWN_CAUSE` is a valid cause classification; the producer must not invent an explanation to fill a mandatory field.

### 3.4 Completeness claim

Completeness is a claim relative to a declared subject, scope, source snapshot, enumeration method and version. It is not a property of a graph or repository in the abstract.

A completeness claim records:
- subject and scope IDs;
- exact source snapshot ID;
- enumeration method and version;
- covered and expected unit counts, where known;
- explicit exclusions, unsupported constructs and assumptions;
- evidence references and verification method;
- invalidation triggers.

`SUPPORTED_WITHIN_SCOPE` is admissible only when the expected denominator is known, covered count equals expected count, at least one evidence reference is present, a verification method is identified, and no unsupported construct remains inside the claimed scope. This status says nothing about sources or predicates outside that scope.

The counts are accounting inputs, not a confidence score. If the denominator is unknown, the claim cannot be promoted to `SUPPORTED_WITHIN_SCOPE`.

### 3.5 Assertion polarity is not proposition truth

M7.5.1 stores assertion polarity and provenance without selecting a universal truth calculus. A proposition may have several supporting and challenging assertions. Contradiction is preserved as data; its resolution, if any, belongs to a later declared inference policy.

This avoids prematurely committing all rules, SAT/SMT encodings, Lean theorems and LLM adapters to one many-valued semantics.

## 4. State and transition invariants

1. Missing input never becomes an assertion that the source or proposition is false.
2. Failed collection, unsupported extraction, resource exhaustion and budget expiry are operational observations, not semantic refutations.
3. A negative conclusion requires an applicable completeness claim for the relevant subject, predicate, scope and snapshot, plus a rule that explicitly permits closed-world inference.
4. Opposing evidence assertions are retained independently.
5. A gap cannot be resolved without resolution evidence; residual acceptance requires disposition and authority.
6. Completeness claims are snapshot-bound and invalidated when a declared dependency changes.
7. Independence labels do not establish independence; shared tools, parsers, specifications, datasets, operators and environments must be examined later.
8. Provenance authenticity, source integrity, extraction completeness, inference correctness and correspondence to intended repository semantics remain separate assurance claims.
9. No record in this package authorizes a repair, publication, runtime selection, solver promotion or production decision.
10. LLM output may propose an assertion or identify a candidate gap, but deterministic validation and authorization remain outside the model.

## 5. Implementation in M7.5.1

Implemented value objects:
- `EvidenceRef`
- `EvidenceAssertion`
- `KnowledgeGap`
- `CompletenessClaim`

Enums:
- `AssertionPolarity`
- `GapKind`
- `GapState`
- `CompletenessStatus`

The dataclasses are frozen and validate their local invariants at construction. They do not write to the graph, mutate existing evidence, persist records, infer proposition truth or perform state transitions.

## 6. Deferred work

| Milestone | Scope |
|---|---|
| M7.5.2 | Append-only knowledge-gap and evidence-assertion persistence; stable IDs, duplicate handling, history and bounded storage without silent deletion |
| M7.5.3 | Scope-bound completeness evaluation and negative-claim admissibility |
| M7.5.4 | Provenance dependency graph, freshness and deterministic invalidation |
| M7.5.5 | Assurance claims, argument links, rebutting/undercutting defeaters and response evidence |
| M7.5.6 | Independence/common-cause analysis and independent challenge mechanisms |
| M7.5.7 | Controlled consumption by existing audit rules and deterministic gates |
| M7.5.8 | Adversarial, mutation, failure-injection and lifecycle acceptance |

The existing 001/003/004/005/006 architecture notes remain design inputs:
- graph-native deterministic audit and typed semantic evidence;
- replaceable LLM adapter with no control-plane authority;
- remediation quantification only after hard feasibility constraints, with candidate-space limitations explicit;
- task-specific solver selection and separation of encoding, solver, source-realization and postcondition validity;
- frozen trusted kernel, enforced cancellation/budgets, well-founded termination arguments and separate safety versus improvement evidence.

## 7. Acceptance criteria for this tranche

- Invalid or empty identifiers are rejected.
- Artifact digests are validated as lowercase SHA-256 when supplied.
- Evidence references are required for assertions.
- Contradictory assertion records coexist without overwrite or collapse.
- Unknown cause is preserved as an explicit gap kind.
- A gap cannot be marked resolved without resolution evidence.
- Accepted residual gaps require disposition and authority.
- A completeness claim cannot be marked supported when its denominator is unknown, coverage differs from the denominator, evidence is absent, verification method is absent or unsupported constructs remain.
- No constructor performs persistence, I/O, network access, solver calls or decision-gate mutation.

**M7.5.1 status after implementation:** contract and pure value-object layer only. Runtime integration and production approval remain false.

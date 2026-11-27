# AE-33 — Formal Architecture-Scope Decision: Audit Engine and Future Supervisor

**Status:** Accepted architectural direction; documentation-only decision  
**Decision date:** 2026-11-27  
**Branch:** `stage1/section-uuids`  
**Baseline revision:** `fc3fa453755a9a029a4101a79027085a4f935d99`  
**Decision authority:** User-approved project direction recorded in the 2026-11-27 architecture discussion  
**Change class:** Scope and responsibility boundary; no application behavior change

## 1. Decision

The repository's current Audit Engine and the future Supervisor are separate systems with different objects of examination, semantic domains, evidence requirements, and acceptance authority.

1. **Audit Engine** examines the repository as functioning software. Its remit is repository code, architecture, dependencies, interfaces, workflows, tests, build/deployment behavior, persistence, provenance, and operational behavior.
2. **Supervisor** is a future system that examines the content produced or assembled by the repository's graph engine and computation machinery, including scientific and documentary meaning represented in LaTeX.
3. The two systems may selectively reuse infrastructure. They must not share an undifferentiated audit ontology, rule set, evidence standard, or acceptance authority.
4. The Audit Engine must not absorb content-level scientific or documentary evaluation merely because the relevant content is stored in this repository or represented in its semantic graph.
5. FEM content-generation and numerical-evidence campaigns are deferred until the user explicitly authorizes them and the document-generation machinery meets the readiness conditions in Section 8.

This decision is normative for future roadmap planning and implementation. It does not claim that a Supervisor currently exists.

## 2. System A — Audit Engine

### 2.1 Object of examination

The Audit Engine's object is the repository as software: source code and the observable behavior of the systems implemented by that source.

### 2.2 In-scope responsibilities

The Audit Engine may inspect and evaluate:

- source files, modules, packages, APIs, interfaces, and dependency relationships;
- graph-engine implementation, graph schema implementation, graph queries, and backend adapters;
- whether a selected adapter actually invokes its declared native library operations;
- computation-backend integration contracts, runtime selection, isolation, failure behavior, and resource controls;
- workflows, CI configuration, tests, build, packaging, deployment, and release mechanics;
- persistence, provenance, replay, freshness, invalidation, consistency, and recovery behavior;
- source retrieval, source identity, snapshot boundaries, path containment, and repository side effects;
- security boundaries, untrusted repository inputs, prompt-injection exposure, tool permissions, and network/process isolation;
- whether implemented software behavior satisfies declared software contracts, including the contracts of code that reads, constructs, transforms, or renders LaTeX.

The last item is a code audit: the Audit Engine can establish whether a LaTeX parser, document-model transformer, renderer, or related workflow behaves according to its software contract. It does not thereby establish whether the resulting document is scientifically correct.

### 2.3 Out-of-scope responsibilities

The Audit Engine does not adjudicate:

- scientific correctness or adequacy of FEM content;
- truth, validity, or completeness of scientific claims and propositions;
- whether an equation, derivation, boundary condition, or physical assumption is scientifically justified;
- whether a numerical result supports a scientific proposition;
- whether evidence is sufficient to substantiate a scientific claim;
- whether citations substantively support the claims to which they are attached;
- whether generated LaTeX faithfully expresses the intended scientific meaning;
- whether a scientific document is complete, coherent, or ready for scientific acceptance.

These are content-level judgments, not repository-software judgments.

## 3. System B — Future Supervisor

### 3.1 Object of examination

The Supervisor's object is the content produced, transformed, or assembled through the repository's machinery—not the repository's software implementation as such.

### 3.2 Intended responsibility domain

Subject to a future explicit design and authorization, the Supervisor may examine:

- LaTeX document structure and semantic consistency;
- claims, propositions, assumptions, and their supporting evidence;
- equations, derivations, references, and their declared relationships;
- numerical/computational results and whether they support the propositions that invoke them;
- correspondence between semantic graph representations, document-model objects, and rendered LaTeX;
- consistency of definitions, notation, units, boundary conditions, and stated model assumptions;
- documentary and scientific completeness against an explicitly declared content specification.

The Supervisor will require its own content ontology, rule catalog, evidence model, verification policies, and acceptance criteria. Those must be designed rather than inferred from the existence of a graph, solver, schema-valid LLM response, or successful renderer.

### 3.3 Independence

The Supervisor is not a new mode of the Audit Engine and is not an unrestricted extension of its rules. It may consume artifacts produced by the Audit Engine or shared infrastructure, but it must make its own content-level determinations under its own authority.

No Audit Engine PASS, graph-validity result, adapter-conformance result, solver status, provenance seal, or CI success may be interpreted as Supervisor acceptance unless a future, explicit cross-system contract defines and independently validates that interpretation.

## 4. Shared infrastructure, separate authority

Potentially reusable infrastructure includes:

- typed graph representation, graph storage, and graph-query primitives;
- source/evidence identity and provenance data structures;
- deterministic rule execution and bounded graph transformations;
- computation adapters and formal-solver interfaces;
- LLM provider adapters for narrowly scoped, non-authoritative tasks;
- validation, replay, reporting, and reproducibility mechanisms.

Reuse is conditional. Each system must define its own:

- domain ontology and vocabulary;
- rule semantics and rule ownership;
- evidence admissibility and sufficiency criteria;
- uncertainty, unknown, stale, and failure-state semantics;
- verification strength and independent-check requirements;
- acceptance, rejection, hold, and escalation policies;
- lifecycle, provenance, and invalidation rules.

A shared graph is a representation mechanism, not a shared source of truth across domains. A graph path is not proof of runtime feasibility or semantic entailment. A solver result is conditional on the correctness of its formal encoding. A schema-valid LLM response is not evidence merely because it parses.

## 5. G5 reassignment and interpretation

**G5 FEM numerical-evidence graph workload is assigned to the future Supervisor, not to the Audit Engine.**

The following boundary examples are binding:

| Question or operation | Responsible system |
|---|---|
| Does a graph backend adapter call the intended native library API? | Audit Engine |
| Are backend dependencies, version constraints, worker isolation, and error contracts correct? | Audit Engine |
| Does the backend preserve the graph representation and declared query semantics? | Audit Engine |
| Does a numerical result support a FEM proposition? | Supervisor |
| Is an equation or derivation scientifically justified? | Supervisor |
| Are numerical results, assumptions, units, and claims mutually consistent? | Supervisor |
| Does the document model preserve the intended semantic objects through rendering? | Supervisor for content correspondence; Audit Engine for the software transformation contract |
| Does the LaTeX renderer execute correctly and reproducibly? | Audit Engine |
| Is the rendered scientific document substantively correct and complete? | Supervisor |

G5 must not be used as a reason to expand the Audit Engine into scientific-content evaluation. If a future workload combines both domains, it must be split into separately attributable software and content claims.

The existing M7.4 task/backend suitability matrix and any historical G5 labels must be reinterpreted through this boundary before being used as current Audit Engine acceptance criteria. Historical results remain historical evidence; this decision does not retroactively change their meaning or pass/fail state.

## 6. Roadmap and change-control consequences

1. Future Audit Engine milestones must state the repository-software property being examined, the source/behavior boundary, evidence requirements, and the acceptance authority.
2. A task that requires judging scientific content must be excluded from the Audit Engine milestone or explicitly identified as a Supervisor dependency.
3. Shared-infrastructure changes must demonstrate a concrete software requirement and must not silently introduce Supervisor policy into Audit Engine code.
4. No generic cross-domain gate, universal ontology, or universal acceptance status is authorized by this decision.
5. The Audit Engine may test that document-processing code preserves declared data structures and transformations. It must not infer scientific correctness from those tests.
6. The future Supervisor must not be treated as implemented, operational, or validated until it has its own architecture, test strategy, content-level benchmark, and evidence-backed acceptance record.
7. Existing software-scope obligations—such as source snapshot consistency, adapter behavior, execution isolation, resource envelopes, and workflow reliability—remain eligible for Audit Engine work when they are still open on the current source revision.
8. The M7.5.30 stopping decision remains in force: no speculative package store, universal consumer gate, or downstream package integration without a demonstrated consumer contract.

## 7. Current work boundary

The current project continues as the Audit Engine. The next work must remain repository-code and repository-operation focused.

The latest accepted baseline at the time of this decision is M7.5.30 on `stage1/section-uuids`, commit `fc3fa453755a9a029a4101a79027085a4f935d99`. M7.5.30 found no demonstrated downstream production consumer for its transient cross-layer obligation package and explicitly rejected speculative lifecycle expansion.

Accordingly:

- do not start FEM scientific-content campaigns;
- do not implement the Supervisor as part of the Audit Engine roadmap;
- do not treat the old G5 FEM numerical-evidence workload as an Audit Engine gap;
- continue with evidence-backed software-audit obligations only;
- re-inspect the current branch before selecting a new implementation milestone, and do not reopen a completed area without a concrete regression, changed contract, or newly demonstrated consumer.

## 8. FEM deferral and future readiness conditions

Substantive FEM work is deferred. It may be reconsidered only after the user explicitly authorizes it and the relevant machinery has demonstrated, at minimum:

- reliable evidence identity and traceability;
- stable semantic document structures and explicit transformation contracts;
- validated computation interfaces and reproducible execution environments;
- reproducible LaTeX rendering;
- an inspectable chain from knowledge/evidence through proposition and document model to rendered LaTeX;
- independently testable correspondence between source semantic objects and rendered document objects;
- clear separation of software-conformance evidence from scientific-content evidence.

These are readiness conditions for reconsideration, not a declaration that they have already been satisfied.

## 9. Relationship to existing architecture records

This decision consolidates and constrains, rather than replaces, the existing architecture rationale and implementation records:

- [AE-32A — Architecture and Wiring Audit](AE-32A-architecture-and-wiring-audit.md): inventory of software implementation and wiring; explicitly not scientific-content evaluation.
- [AE-32C M7.5.30 — Cross-Layer Package Consumer and Lifecycle Audit](AE-32C-M7.5.30-Cross-Layer-Package-Consumer-and-Lifecycle-Audit.md): no speculative package consumer or lifecycle expansion without a real contract.
- [Graphify Branch Backend Status Assessment — 2026-11-26](Graphify-Branch-Backend-Status-Assessment-2026-11-26.md): backend implementation status and limitations; operation-scoped evidence, not scientific task suitability.
- [AE-32C — Graph Backend Compatibility and Utilization Roadmap](AE-32C-Graph-Backend-Compatibility-and-Utilization-Roadmap.md): historical backend milestones and open operational boundaries; must be read under the scope split in this decision.

Architectural rationale is also recorded in the project Wiki:

- [Semantics as an Architectural Foundation for the Scientific Reasoning Repository](https://github.com/snoopdock/Finite_element_analysis_project/wiki/Semantics-as-an-Architectural-Foundation-for-the-Scientific-Reasoning-Repository)
- [Semantic Graph Architecture Decision](https://github.com/snoopdock/Finite_element_analysis_project/wiki/Semantic-Graph-Architecture-Decision)
- [Neurosymbolic Code Auditing — Architectural Integration Notes for the Semantic Graph Engine](https://github.com/snoopdock/Finite_element_analysis_project/wiki/Neurosymbolic-Code-Auditing-%E2%80%94-Architectural-Integration-Notes-for-the-Semantic-Graph-Engine)

The Wiki records architectural intent and historical design reasoning. Current implementation claims must still be established from branch-pinned source, tests, and exact-run evidence.

## 10. Explicit non-claims

This decision does not claim that:

- the Supervisor has been designed or implemented;
- the current graph is complete, semantically authoritative, or suitable for all future domains;
- any computation backend is universally suitable or preferred;
- all repository-software obligations are closed;
- the current document-generation machinery is ready for FEM campaigns;
- scientific correctness can be inferred from software tests, graph topology, provenance, solver status, or successful rendering.

**Decision summary:** Audit Engine audits the repository as software. The future Supervisor audits the content produced through that software. Infrastructure may be reused; domain semantics, evidence standards, and acceptance authority remain separate.

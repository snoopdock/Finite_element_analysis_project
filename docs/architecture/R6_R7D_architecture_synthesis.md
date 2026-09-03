# R6–R7D Architecture Synthesis & Interface Audit

**Status:** Review checkpoint — R7D complete / frozen  
**Branch:** `stage1/section-uuids`  
**Scope:** R6 through R7D, with interfaces to the existing scientific reasoning pipeline  
**Implementation policy:** This document records the architecture and audit findings. It does not introduce runtime behavior or change scientific state.

## 1. Purpose

R6–R7D establishes a retrieval-attention subsystem that records retrieval conditions, deterministically interprets selected operational conditions as attention proposals, persists those proposals, and records controlled lifecycle decisions. The subsystem is intentionally separated from the scientific reasoning state.

The principal architectural distinction is:

```text
RetrievalEvent
    = historical acquisition fact

AttentionProposal
    = deterministic process interpretation of acquisition history

LifecycleEvent
    = explicit historical process decision about an attention proposal
```

These are different semantic objects and must not be collapsed into one state representation.

## 2. Frozen R6–R7D Stack

```text
Retrieval subsystem
      |
      v
R6  RetrievalEvent / retrieval history
      |
      v
R6.5  Retrieval-attention semantics
      |
      v
R7A  normalized retrieval context reconstruction
      |
      v
R7B  deterministic policy interpretation
      |
      v
R7B.5  canonical AttentionProposal
      |
      v
R7C  proposal persistence / replay / live composition
      |
      v
R7D  lifecycle event model / persistence / replay /
     integration / runtime boundary / authority decision
```

The R7C runtime connector explicitly composes R7A–R7C only and performs no network retrieval, LLM call, lifecycle transition, acquisition-action execution, or scientific-state mutation. `analysis/retrieval_attention_runtime.py` documents and implements this boundary through `generate_and_persist_retrieval_attention`.

## 3. Guarantees Established

### 3.1 Acquisition provenance

R6 gives the system a historical record of retrieval behavior. A retrieval event describes what happened at acquisition time, including operational outcomes such as provider failure, rate limiting, empty results, or successful retrieval.

This record is historical evidence about the operation of the retrieval subsystem. It is not itself scientific evidence for a proposition.

### 3.2 Deterministic attention interpretation

R7A reconstructs normalized context from historical retrieval events. R7B evaluates explicit policy against that context. R7B.5 freezes the canonical proposal representation and its deterministic identity.

The proposal is therefore a process-level interpretation:

```text
observed retrieval condition
        +
explicit policy
        +
provenance links
        ->
AttentionProposal
```

The proposal contract explicitly forbids promoting query/provider scope or retrieval events into scientific scope or evidence relations.

### 3.3 Proposal persistence and replay

R7C keeps the proposal history independently persisted and replayable. Deterministic proposal identity excludes persistence timestamps. Persistence metadata may be added without changing the deterministic interpretation.

### 3.4 Lifecycle provenance

R7D records process decisions separately from proposal persistence and retrieval history. Lifecycle history is append-only and replayable. Valid transitions are:

```text
null -> open
open -> addressed
open -> closed
addressed -> closed
```

Reopening and same-state transitions are forbidden. Lifecycle status is explicitly process metadata rather than evidence quality, truth, uncertainty, confidence, scientific relevance, or scientific importance.

### 3.5 Authority boundary

R7D.7 defines a lifecycle-management authority boundary. R7D.8 selects `controlled_process` as the current authority mode. No automated lifecycle authority, authorization engine, lifecycle endpoint, or automatic acquisition/action loop is currently introduced.

This preserves an important asymmetry:

```text
Retrieval subsystem     -> may record RetrievalEvents
R7B policy evaluator    -> may create AttentionProposals
Lifecycle authority     -> may record LifecycleEvents
```

No one of these roles implicitly inherits another role's authority.

## 4. Interface Audit: Scientific Reasoning Pipeline

The current architecture separates retrieval attention from the core scientific state. This is supported by the implementation and by the contracts.

The protected scientific domains include:

- propositions;
- evidence relations;
- epistemic state;
- evidence strength;
- truth status;
- ranking;
- convergence;
- writing content;
- knowledge base;
- sections.

The R7B.5 and R7D integration contracts explicitly prohibit direct mutation of these fields by retrieval attention/lifecycle handling.

### 4.1 Knowledge graph

`core/knowledge_graph.py` models concepts, propositions, and typed relationships with explicit identities, source IDs, contextual fields, and proposition status. Graph normalization also validates references. `core/graph_state.py` provides the graph-state adapter, including legacy-knowledge synchronization, candidate-link generation, explicit membership, proposition-history recording, and reference validation.

**Audit conclusion:** retrieval attention is not currently a graph relation or proposition. It should remain outside the scientific knowledge graph unless a future contract defines a specific scientific object whose meaning justifies graph membership.

### 4.2 Evidence state and evidence relations

`core/evidence_state.py` keeps source characterization and proposition-level evidence scope in dedicated state domains. The H6 literature fixture requires that source metadata remain distinct from retrieval provenance and that actual passage evidence be required for evidence relations.

**Audit conclusion:** a RetrievalEvent or AttentionProposal must not be treated as evidence support merely because it points to a source. A later successful acquisition can enable acquisition of scientific evidence, but the acquired passage/evidence must enter the scientific evidence pipeline through its own contract.

### 4.3 Epistemic state

`analysis/epistemic_state.py` defines statuses such as `established`, `supported`, `conditional`, `disputed`, `insufficient_evidence`, `superseded`, `unresolved`, and `unknown`, plus evidence strength, literature agreement, independent support, limitations, and optional model confidence.

**Audit conclusion:** retrieval-attention conditions are operational observations. They do not justify direct epistemic updates. For example, a provider failure cannot become `insufficient_evidence`, and a successful retrieval cannot become `supported`, without scientific evidence analysis.

### 4.4 Ranking

`research/ranking.py` computes deterministic ranking scores from lexical match, source quality, section relevance, and citation support. This ranking operates on evidence/source items.

**Audit conclusion:** retrieval-attention priority is semantically different from evidence ranking. An operationally problematic query/provider may deserve process attention without making the associated scientific source or proposition more or less scientifically relevant.

### 4.5 Convergence

`core/convergence.py` determines convergence from document-state stability, anomaly history, completeness, reading coverage, citation coverage, and optional lexical-support coverage.

**Audit conclusion:** retrieval attention is not currently an input to convergence, and there is no architectural justification for adding it implicitly. A retrieval problem may lead to a later retrieval action and new evidence, which can affect convergence indirectly through normal scientific/document pathways, but the attention signal itself should not adjust convergence.

### 4.6 Writer and OAA decisions

`core/writer_orchestration.py` records writer decisions and runs semantic review, correction planning, perspective analysis, and OAA adjustments. `core/decision_state.py` persists writer/OAA decision history. `analysis/oaa_loop.py` operates on document-structure anomalies.

**Audit conclusion:** retrieval attention should not become a hidden writer instruction. Any future use by writing would require an explicit planning/interface contract and a clear semantic statement that the input is a process signal rather than scientific judgment.

## 5. Existing Research-Planning Candidate

The repository already contains a separate concept named `ScientificAttention` in `analysis/scientific_attention.py`. It represents non-scalar attention signals:

```text
 evidence_gap
 disagreement
 contextual_complexity
 verification_need
 importance
 decision_consequence
```

It also exposes `attention_priority()` as a bounded scheduling score. `core/scientific_attention_state.py` persists these signals keyed by a section or proposition.

This is significant because a future research-planning interface does **not** necessarily need a new generic `InvestigationCandidate` object immediately. The repository already has a distinct scientific-attention vocabulary.

However, this existing concept is not the same as R7 retrieval attention:

```text
ScientificAttention
    = scientific/research scheduling signal

Retrieval AttentionProposal
    = retrieval-process condition requiring attention
```

They answer different questions:

```text
Retrieval attention:
    What went wrong or became operationally notable in acquisition?

Scientific attention:
    What scientific object may deserve additional intellectual work?
```

The audit therefore finds a **potential future interface**, not a present defect:

```text
Retrieval AttentionProposal
          |
          | explicit mapping only
          v
Scientific/research planning input
          |
          v
ScientificAttention / investigation scheduling
```

Such a mapping must be policy-defined and traceable. It must not be automatic merely because a proposal exists.

## 6. Capability Gap Analysis

### Gap A — Research-planning bridge

**Status:** architecturally plausible; not required for R7D closure.

A useful future capability is a planning interface that can say:

```text
Which acquisition/process issue deserves investigative effort next?
```

The bridge should create or update a process/planning object without modifying proposition truth, evidence strength, epistemic state, evidence ranking, or convergence directly.

The existing `ScientificAttention` model is a candidate consumer, but its precise semantics and provenance requirements need a dedicated design decision before integration.

### Gap B — Current lifecycle-state view

There is a deliberate representational nuance in the frozen R7C/R7D contracts: lifecycle transitions must not rewrite the persisted `lifecycle_status` field in an existing `AttentionProposal`. The lifecycle history separately records the authoritative trajectory.

This preserves immutable proposal provenance, but it means that a consumer asking for “the current lifecycle status” cannot safely interpret the proposal's stored `lifecycle_status` field as the latest status after a transition.

**Audit conclusion:** this is a **view-model/documentation gap**, not an implementation bug. The correct future solution is a derived/current lifecycle view or explicitly named historical-status field, not mutation of the frozen proposal record.

### Gap C — Evidence coverage semantics

The repository has retrieval coverage, citation coverage, lexical-support coverage, source characterization, and evidence-scope machinery, but these quantities do not automatically define a general scientific statement of “literature search completeness.”

**Audit conclusion:** do not introduce a single coverage score without a formal definition of the reference space, completeness criterion, scope, and uncertainty. This remains a research/design question.

### Gap D — Human/system review workflow

R7D.8 deliberately stops at `controlled_process`. A review queue, approval interface, actor authorization model, or automated lifecycle authority would be a separate workflow subsystem.

**Audit conclusion:** no implementation is currently justified by R7D itself. Such a workflow should be introduced only if an operational bottleneck is demonstrated.

## 7. Interface Matrix

| Component | Primary input | Primary output/state | Scientific-state mutation | Authority | Provenance |
|---|---|---|---|---|---|
| Retrieval | external acquisition request/result | RetrievalEvent / retrieval history | No scientific mutation | retrieval subsystem | event identity and retrieval metadata |
| R7A context | retrieval history | normalized retrieval context | No | none beyond normalization | supporting event IDs |
| R7B policy | R7A context + explicit policy | deterministic attention interpretation | No | attention interpretation only | policy version + context |
| R7B.5 proposal | R7B output | canonical AttentionProposal | No | no lifecycle authority | deterministic attention ID + supporting events |
| R7C persistence | proposal | proposal history | only retrieval-attention state | persistence adapter | canonical payload / IDs |
| R7D lifecycle | explicit authorized request | LifecycleEvent / lifecycle history | only lifecycle state | lifecycle-management layer | actor, reason, transition, timestamp |
| Knowledge graph | scientific concepts/propositions/relations | scientific graph state | Yes, within graph contracts | scientific graph components | source IDs + proposition/relationship IDs |
| Evidence state | source/proposition evidence information | evidence characterization/scope | Yes, scientific evidence domains | evidence components | source/proposition links |
| Epistemic state | scientific evidence/analysis | epistemic state | Yes | scientific reasoning components | proposition/evidence context |
| Ranking | query + evidence items | evidence ranking | No claim-truth mutation | ranking component | source metadata/citations |
| Convergence | document/evidence stability | convergence diagnostics | No direct scientific inference | convergence component | iteration/document evidence |
| Writer/OAA | knowledge base + document state | sections / decisions / adjustments | modifies writing/document state | writer/OAA components | section IDs, decision history |

## 8. Principal Interface Rules

The following rules should be treated as architectural invariants for future changes:

1. `RetrievalEvent != AttentionProposal != LifecycleEvent`.
2. Retrieval attention is operational process metadata, not scientific evidence.
3. Lifecycle status is process state, not epistemic state.
4. A recommendation is not an execution command.
5. Acquisition success/failure does not itself imply a lifecycle transition.
6. Referencing a source does not create an evidence relation.
7. Retrieval attention must not directly mutate proposition, evidence, epistemic, ranking, convergence, or writer semantics.
8. New acquisition attempts create new RetrievalEvents rather than rewriting old events.
9. Historical lifecycle events are authoritative for replay.
10. Any future bridge into scientific/research planning must be an explicit interface with its own semantics and provenance.
11. A planning priority must not be conflated with the existing evidence-ranking score.
12. A later automated lifecycle authority requires a superseding architecture decision record.

## 9. Traceability Audit

The current repository contains meaningful architectural traceability, but it is distributed rather than represented in one component registry.

The README connects major architectural mechanisms to external literature and internal framework documents, including:

- Parnas (1972) — modular decomposition;
- Meyer (1988) — object-oriented construction;
- Dörfler (1996) — adaptive marking / resource allocation analogy;
- Zilberstein & Russell (1996) — bounded computation allocation;
- Kephart & Chess (2003) — autonomic closed-loop control;
- Ashby (1956) — context-aware/context-free evaluation motivation;
- Simon (1962) — decomposition of complex tasks;
- Jaccard (1901) — similarity measurement;
- Wiener (1948) and Åström & Murray (2008) — feedback/hysteresis concepts;
- formal-method references for SAT/SMT/CP-SAT/Lean.

The H6 FEM literature fixture additionally records concrete scientific-source roles and explicitly tests the separation of source identity, retrieval provenance, proposition support, and evidence relations.

**Traceability finding:** the architectural evidence is present, but there is no single normalized registry mapping each R6–R7D component to its motivation, reference, contract, implementation, and audit. Creating such a registry is useful documentation work, but it is not required for runtime correctness.

A desirable future documentation table is:

```text
component
  -> design motivation
  -> normative contract
  -> implementation module
  -> audit script
  -> motivating paper/framework
  -> repository decision record (when applicable)
```

## 10. Decision at This Checkpoint

R7D remains:

```text
COMPLETE / FROZEN
```

The architectural audit finds no immediate scientific-pipeline defect requiring R7D modification.

The most credible future extension is a **research-planning interface** between operational retrieval attention and scientific/research scheduling. The repository already contains `ScientificAttention`, so the next design task should first determine whether that existing abstraction is the correct consumer before introducing another planning object.

The current lifecycle-status representation should be treated as a known view-model/documentation issue. It should not be repaired by mutating historical proposals.

No code changes to the scientific reasoning pipeline are justified by this audit alone.

## 11. Next Architectural Work

The recommended next review sequence is:

```text
R6–R7D synthesis
      |
      v
Define meaning of research/investigation priority
      |
      v
Audit existing ScientificAttention and planning paths
      |
      v
Decide whether an explicit bridge is needed
      |
      +---- no -> retain separation
      |
      +---- yes -> write contract/decision first
```

Only after a concrete interface requirement is established should implementation begin.

## 12. Repository References

Primary frozen artifacts reviewed for this synthesis:

- `specs/contracts/retrieval_attention_contract.yaml`
- `specs/contracts/retrieval_attention_context_contract.yaml`
- `specs/contracts/retrieval_attention_policy_contract.yaml`
- `specs/contracts/retrieval_attention_proposal_contract.yaml`
- `specs/contracts/retrieval_attention_persistence_contract.yaml`
- `specs/contracts/retrieval_attention_pipeline_contract.yaml`
- `specs/contracts/retrieval_attention_replay_contract.yaml`
- `specs/contracts/retrieval_attention_runtime_contract.yaml`
- `specs/contracts/retrieval_attention_runtime_isolation_contract.yaml`
- `specs/contracts/retrieval_attention_lifecycle_contract.yaml`
- `specs/contracts/retrieval_attention_lifecycle_persistence_contract.yaml`
- `specs/contracts/retrieval_attention_lifecycle_integration_contract.yaml`
- `specs/contracts/retrieval_attention_lifecycle_runtime_boundary_contract.yaml`
- `specs/decisions/R7D.8_lifecycle_authority_decision.yaml`
- `analysis/retrieval_attention_pipeline.py`
- `analysis/retrieval_attention_runtime.py`
- `analysis/retrieval_attention_lifecycle.py`
- `analysis/retrieval_attention_lifecycle_replay.py`
- `core/retrieval_attention_persistence.py`
- `core/retrieval_attention_lifecycle_persistence.py`
- `core/state_manager.py`
- `core/knowledge_graph.py`
- `core/graph_state.py`
- `core/evidence_state.py`
- `analysis/epistemic_state.py`
- `analysis/scientific_attention.py`
- `core/scientific_attention_state.py`
- `research/ranking.py`
- `core/convergence.py`
- `core/writer_orchestration.py`
- `core/decision_state.py`
- `analysis/oaa_loop.py`
- `audits/fixtures/h6_fem_literature_manifest.yaml`
- `README.md`


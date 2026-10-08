
# Graph Neural Networks Meet Neural-Symbolic Computing — Review and Impact on G3

## Source
Luis C. Lamb, Artur d'Avila Garcez, Marco Gori, Marcelo O. R. Prates, Pedro H. C. Avelar, Moshe Y. Vardi. **Graph Neural Networks Meet Neural-Symbolic Computing: A Survey and Perspective.** arXiv:2003.00330v7, 2021.

## Why this paper matters to this repository
The paper surveys the relationship between graph neural networks and neural-symbolic computing. Its value to the repository is architectural rather than an instruction to add a GNN immediately. It shows multiple possible couplings between learned and symbolic systems and explicitly identifies the tension between effective learning and sound reasoning.

For this project that supports a conservative design: learned systems may help propose, rank, or encode relational hypotheses, while deterministic semantic contracts and verification remain authoritative.

## Relevant concepts

### Relational inductive bias
Graph representations provide an inductive bias suited to relational structure. Message passing and attention allow learned representations to incorporate information from graph neighborhoods.

Potential future repository uses include:

- ranking candidate relations;
- semantic-similarity search;
- anomaly prioritization;
- learned retrieval over large semantic neighborhoods;
- candidate missing-edge discovery.

None of those operations establishes semantic truth by itself.

### Hybrid neural-symbolic architectures
The paper's neural-symbolic taxonomy demonstrates that neural and symbolic components need not be collapsed into one opaque system. Hybrid architectures can divide responsibilities.

G3 adopts the corresponding repository principle:

```text
learned/LLM inference
        -> CandidateKnowledge
        -> explicit verification
        -> future canonical promotion
```

rather than:

```text
model output -> canonical fact
```

### Sound reasoning versus learned reasoning
The paper's discussion of the tension between learning and sound reasoning directly influenced the G3 decision to keep the canonical semantic graph and verification layer deterministic and inspectable.

## Impact on G3.1
The paper influenced three G3.1 decisions:

1. **Candidate knowledge isolation.** Future learned relationships are represented as candidates, not canonical edges.
2. **Explicit verification boundary.** A candidate or graph observation must pass a verifier before stronger epistemic status is granted.
3. **Versioned artifacts instead of hidden model state.** Rules and receipts remain external, inspectable, and executable by non-neural components.

## Impact on later graph work

### G3.2
Graph snapshots and verified audit memory will provide the stable labeled history required before learned graph models can be evaluated responsibly.

### G3.3
Audit orchestration may eventually use learned ranking as one signal for where to spend verification budget, but the orchestrator must retain deterministic fallbacks and provenance.

### G4+
A learned advisory backend can be considered only after the repository has:

- stable graph vocabularies;
- reproducible snapshots;
- validated findings;
- evaluation datasets;
- explicit calibration and provenance requirements.

## What was deliberately not adopted
G3 does not currently add embeddings, GNN training, neural theorem proving, or automatic relation acceptance. The paper motivates those as future research directions, not as prerequisites for trustworthy graph auditing.

## Architectural invariant derived from the review
**Probabilistic relational inference may generate candidates; it cannot redefine canonical semantic authority without explicit verification.**

# AE-26 — Language-independent semantic vocabulary and contract evolution

## Purpose

AE-26 moves the Audit Engine from typed graph admission toward an explicit
semantic layer. It defines a finite vocabulary for the relations already
admitted by AE-24, produces deterministic semantic projections, and compares
two admitted contracts to expose structural and meaning-level changes.

The implementation is independent of Python syntax. Future adapters for Rust,
C++, CI workflows, API schemas, scientific pipelines, or other artifact
sources can produce equivalent AE-24 facts and obtain the same semantic
projection.

## Identity and evidence

* AE-24 remains the admission boundary. Source hashes establish byte
  consistency, not external authenticity or truth.
* Occurrence IDs and source IDs remain provenance identities.
* Semantic fingerprints collapse duplicate occurrences carrying the same
  normalized semantic relation, while the evidence projection retains every
  occurrence.
* Origin (`declared`, `observed`, `candidate`) remains semantically relevant.
* Candidate/neural assertions are never promoted by AE-26.

## Contract evolution

`diff_contracts()` classifies relationship additions/removals, entity-kind
changes, and interface meaning changes. A change report describes admitted
evidence; it does not prove a deployed runtime change.

The comparison does not infer arbitrary natural-language equivalence,
ontology entailment, behavioral causality, or intent from names.

## Limitations

* No LLM inference or neural training.
* No OWL-DL entailment.
* No automatic graph mutation or remediation.
* A source-bound relation can still be wrong if extraction is wrong.
* Semantic equality is defined by this versioned vocabulary.
* Entity identity is local to the contract namespace.
* Full downstream invalidation is future work; AE-25 remains the conservative
  dependency-impact mechanism.

## Security and budgets

AE-24 enforces source and graph budgets. AE-26 adds a 12,000-change budget.
CLI input is canonical JSON plus bounded regular files; symlinks and unsafe
source names are rejected. Source programs are never executed.

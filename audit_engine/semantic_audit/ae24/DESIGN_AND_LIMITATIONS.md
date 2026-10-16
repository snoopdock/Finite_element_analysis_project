# AE-24 — Semantic contracts and graph admission

This module uses the existing backend-independent `SemanticGraph` and AE-13 graph validation. It introduces versioned **relationships** and their typed endpoint semantics, not a new graph database. Input may describe components from Python, Rust, Go, CI workflows, services, or other sources; no source language is parsed by this module.

## Source and authority

* `admit()` checks every supplied evidence byte sequence against its pinned SHA-256. This proves *byte consistency*, **not external authentication, truthful source extraction, or runtime behavior**.
* Every assertion has a source occurrence ID, source witness ID, and `declared`, `observed`, or `candidate` origin. `candidate` represents an unverified neural or other proposal and **must not** be used as authoritative input to symbolic invariant conclusions.
* Graph nodes are entities; graph edges are **occurrences**, preserving parallel edges with distinct IDs. Different verifications may reuse one occurrence. No artificial one-to-one restriction.
* An explicit coverage claim only attests that the *source declaration* says coverage is complete. It does not independently prove that the real-world system was completely examined.
* The `SemanticGraph` remains in-memory mutable. `verify_admission()` must replay against exact source bytes before a protected downstream decision. No authoritative graph write, permission grant, or verified finding is produced.
* Relations deliberately have a narrow endpoint vocabulary, required interpretation, and finite resource budgets. Unrecognized semantics fail closed; an adapter must not silently coerce an unrelated relationship into a supported predicate.

## Future extensions

AE-25 adds deterministic, witness-carrying structural reasoning and conservative incompleteness. Later versions may support ontological translations with loss reports, non-Python adapters, authenticated source providers, and bounded neural candidate retrieval. No OWL DL or model inference is claimed here.

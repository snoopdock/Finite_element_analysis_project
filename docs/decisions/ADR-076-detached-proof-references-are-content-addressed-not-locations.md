# ADR-076 — Detached Proof References Are Content-Addressed, Not Locations

**Status:** Accepted  
**Milestone:** G3.4.5

## Context

G3.4.3/G3.4.4 allowed an external CNF solver to return proof-carrying UNSAT evidence, but the proof lived inside the bounded JSON solver response. Real DRAT-family proofs can be much larger than a reasonable control-plane response and should not be materialized as an untrusted nested Python object.

Allowing the solver to return an arbitrary path, URL, import path, or command would violate the repository's core auditor-security rule: **evidence is data, not execution or retrieval authority**.

## Decision

A detached proof is identified only by a strict `ProofArtifactReference` containing:

- trusted `store_id` selector;
- exact artifact SHA-256;
- exact byte size;
- proof format;
- exact CNF digest;
- fixed artifact/media format identifiers.

The reference contains no path, URL, URI, command, executable, or import location. `store_id` resolves only through a registry populated by trusted application code. The initial implementation provides a local content-addressed store whose physical filename is derived solely from SHA-256 under a trusted root.

The exact open file is byte-counted and SHA-256 verified before it is rewound for parsing. Artifact integrity is a prerequisite to proof checking but is not itself logical evidence.

## Consequences

- Solver output cannot authorize arbitrary repository file access or network retrieval.
- Artifact transport/storage can evolve independently from logical proof languages.
- Future remote/object stores must implement the same trusted-store contract; adding a URI to the solver response is not an acceptable shortcut.
- Content identity can be retained in verification witnesses and long-term audit artifacts without embedding the proof bytes.

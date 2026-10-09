# ADR-077 — Streaming Proof Checking Preserves the Existing Logical Boundary

**Status:** Accepted  
**Milestone:** G3.4.5

## Context

Detached artifacts solve control-plane size problems only if proof checking also avoids loading the complete certificate into memory. However, RUP/RAT semantics require an active clause database, so "streaming" must not be misrepresented as constant-memory logical verification.

## Decision

The initial detached artifact format is `semantic_cnf_proof_jsonl/v1`. The first line is a strict header binding artifact format, proof format, and CNF digest. Each subsequent line is one proof step.

Repository-owned streaming checking:

1. verifies artifact size and SHA-256 using the exact open file;
2. rewinds that verified handle;
3. parses one bounded UTF-8 JSON object per line;
4. checks each RUP/DRAT step immediately;
5. never accumulates the proof-step sequence;
6. retains only the active formula/proof state required by RUP/RAT semantics;
7. requires the final proof step to add the empty clause.

The supported logical rules remain exactly the repository-owned RUP and structured DRAT rules established in G3.4.3/G3.4.4. Streaming does not create a new proof authority.

## Consequences

- Peak memory no longer scales with the serialized proof-step list itself.
- Active clause-state memory can still grow with the proof and remains explicitly bounded.
- RUP and DRAT can use detached artifacts without changing their epistemic meaning.
- Native textual DRAT/LRAT parsing remains future work and must have its own strict parser contract.

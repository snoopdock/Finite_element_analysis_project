# ADR-066 — Registered Executable Witness Authority

## Status
Accepted for G3.4.1.

## Decision
Executable witnesses may invoke only deterministic, side-effect-free, network-free callables pre-registered by trusted application code. Audit artifacts may select a registered harness by ID and version but cannot supply source code, import paths, shell commands, or executable paths.

## Rationale
Evidence must not become instructions. This preserves the neurosymbolic-auditing security boundary while creating a real executable-witness path suitable for future repository-owned reproduction harnesses.

## Privacy and provenance
Serialized execution witnesses retain content digests and harness identity/version rather than raw input/output payloads.

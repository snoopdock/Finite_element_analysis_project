
# ADR-039: Verification Receipts as Immutable Audit Artifacts

## Status
Accepted for G3.1.0.

## Context
An audit conclusion is not reproducible if the system records only a message such as "verified". A reviewer must be able to recover the obligation, verifier identity/version, evidence, graph snapshot, and semantic interpretation context.

## Decision
Every completed verification SHALL be sealed into an immutable `VerificationReceipt` containing at least:

- deterministic receipt identity;
- attempt and obligation identities;
- source analysis identity;
- verifier ID and version;
- verification decision;
- evidence state and evidence IDs;
- semantic graph fingerprint;
- semantic-context fingerprint.

Receipt identity is deterministic for identical verification content. Receipt staleness is evaluated against both graph fingerprint and semantic-context fingerprint.

## Consequences
Findings can cite stable machine-readable evidence. Audit history can survive across commits without treating outdated conclusions as current. Future CI and long-term memory layers can reuse receipts instead of reconstructing reasoning from transcripts.

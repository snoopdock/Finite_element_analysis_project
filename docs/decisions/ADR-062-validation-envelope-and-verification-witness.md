# ADR-062: Validation Envelope and Verification Witness

## Status
Accepted

## Decision
Every controlled high-assurance result carries a `ValidationEnvelope` declaring checked scope, assumptions, excluded scope, completeness, tool identity/version, and subject digest. Validated results require reproducible witness artifacts under the default policy.

`EXHAUSTIVE_WITHIN_SCOPE` is intentionally local: it does not assert that excluded runtime behavior, dynamic code, external systems, or unstated assumptions were checked.

## Consequences
Audit reports can explain exactly what a strong verifier established, what it did not establish, and which witness can be independently inspected.

# ADR-024: Artifact Metadata and Versioning

## Status
Accepted for G2.5 Step 20

## Decision
Introduce ArtifactMetadata to provide persistent identity and version information for provenance artifacts.

Metadata includes:
- schema version
- generator identity
- semantic graph version
- creation timestamp
- execution context

Architecture:

BackendExecutionResult
        |
        v
Provenance Artifact Envelope
        |
        +-- Metadata
        +-- Provenance
        +-- Transformations
        +-- Loss Assessment

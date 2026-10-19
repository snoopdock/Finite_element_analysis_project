# AE-32C Patch 1 — Evidence Integrity and Security Boundary

## Purpose

Patch 1 hardens the accepted AE-32B evidence interface before any live LLM orchestration is connected. It does not implement the investigation loop and does not execute repository code.

## Changes

- Every tool response is recursively sanitized into a detached JSON-compatible structure before it is returned.
- Secret redaction runs before snippet truncation, including search results and decision-history snippets.
- Non-finite and unsupported values are normalized to explicit markers, then every response passes strict JSON serialization; oversized responses fail closed without returning partial evidence.
- Structured decision-memory records are normalized before graph insertion. Dates become ISO-8601 strings, non-finite numbers become explicit markers with incomplete-coverage diagnostics, and cyclic/unsupported structures are quarantined.
- Duplicate record identities are reported instead of silently merging a second physical record into the first graph node.
- Evidence-index completeness is reported separately from the source manifest's scan status.
- Snapshot file reads use no-follow directory-relative opens on supported POSIX systems, with size/hash checks and a documented portable fallback.
- Cloudflare HTTP errors no longer include upstream response bodies. Provider diagnostics use a small redaction helper and bounded text.
- Provenance explicitly labels caller-supplied source and runner revisions as asserted, not independently Git-verified.

## Safety and scope

No shell execution, target-code execution, network access from the evidence tools, repository modification, patch application, commits or pushes are introduced. Provider error tests use mocked responses only. The regular regression profile does not require live credentials.

## Known limitations

- Pattern-based redaction cannot guarantee removal of arbitrary unknown secrets. The implementation therefore also omits raw upstream HTTP error bodies and should continue to minimize sensitive input at source.
- The portable non-POSIX snapshot-reader fallback cannot provide the same directory-descriptor race resistance as the POSIX `O_NOFOLLOW` path; it still performs path, containment, size and hash checks.
- Graph traversal computation budgets, source-line indexing unification, workflow parsing improvements and the interactive investigation loop are assigned to later sequential patches.
- This patch was prepared without running the repository or its tests locally, as requested. Validation status must be established from the user's GitHub Actions logs.

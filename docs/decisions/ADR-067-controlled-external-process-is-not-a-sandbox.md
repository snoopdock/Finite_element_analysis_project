# ADR-067 — Controlled External Process Is Not an OS Sandbox

## Status
Accepted for G3.4.2.

## Context
G3.4.1 intentionally prohibited arbitrary subprocess execution. G3.4.2 needs a path for future external SAT/SMT engines without falsely equating `subprocess` with secure sandboxing.

A Python process wrapper can fix the executable, verify its digest, disable shell interpretation, bound JSON input/output, use an ephemeral working directory, minimize inherited environment, and enforce a timeout. It cannot, by itself, prove that an arbitrary binary has no network access or cannot reach filesystem locations outside that working directory.

## Decision
The first external process boundary is classified as `controlled_external`, never `sandboxed_subprocess`.

Execution requires all of the following:

- an absolute executable path registered by trusted application code;
- SHA-256 verification of the executable immediately before every run;
- fixed registered arguments, never request-provided commands;
- `shell=False`;
- bounded JSON stdin/stdout/stderr;
- timeout and process-tree termination;
- ephemeral working directory and minimal environment;
- explicit acknowledgement that network isolation is not enforced;
- explicit acknowledgement that filesystem isolation outside the working directory is not enforced;
- separate high-assurance policy permission for the `controlled_external` containment mode and side-effecting adapters.

## Consequences
A successful controlled-external process run proves only that the registered executable image produced a protocol-valid response under the recorded execution envelope. It does not prove that the binary was sandboxed, side-effect free, or semantically correct.

A future OS-level sandbox broker may satisfy a stronger containment mode, but it must be a separate implementation with independently testable isolation claims.

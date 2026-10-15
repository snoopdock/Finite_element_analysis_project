# AE-10 — Scientific Claim–Evidence Traceability and Quantitative Consistency

## Scope and falsifiable interpretation

AE-10 is a bounded, **read-only** scientific-evidence auditor. Its independently replayable decisions concern exact JSON measurements, explicitly authored claim statements, and the existence of declared support edges. It does **not** infer scientific truth from citations or determine the correctness of a physical model, a finite-element simulation, a literature review, or a statistical analysis. The code does not call language models, read external webpages, convert units, or execute scientific sources.

The author supplies a strict JSON specification with `schema: ae10/scientific-spec/v1`, one or more source evidence artifacts, and claims with source-bound statement files and explicit numerical assertions. Each artifact and statement is bound to SHA-256 of the **actual source bytes**. A source hash mismatch yields `inconclusive`, not a clean result.

## Graph and verification contract

AE-10 constructs real G3 `SemanticGraph` entities (`ScientificClaim` and `EvidenceArtifact`) and source-located, digest-bound `SUPPORTED_BY` relationships. It invokes the repository's existing `scientific.claim_requires_support_relationship` policy via `SemanticGraphAnalysisService`, `DomainRuleExecutor`, `RequiredRelationshipVerifier`, and `VerificationService` for **each** claim; all obligations and receipts are included in the detached report. A finding for a missing `SUPPORTED_BY` edge means only that the supplied graph is missing the required declared relation.

## Exact numerical contracts

Evidence artifacts must be UTF-8 JSON. A numerical pointer addresses an object containing **exactly** `value` and `unit`; `value` is a decimal string or integer. The specification declares `op` (`eq`, `ge`, `le`, `between`), expected value(s), explicit unit string and nonnegative absolute tolerance. All arithmetic uses Python `Decimal` with bounded exponents and precision. There is no implicit unit conversion, arithmetic derivation from raw simulations, uncertainty propagation, or equivalence checking of two formulas. Unsupported values, missing pointers, invalid JSON, unit disagreement, or unavailable source files yield `unassessed` and prevent a clean verdict. A numerical disagreement under a complete scope is `inconsistent`.

The cleanest possible result is `consistent_within_declared_checks`, meaning only that **all declared numerical checks matched** and every claim has a declared support relationship and source-bound statement. This is deliberately narrower than scientific verification or publication approval.

## External validity and reproducibility

Synthetic evidence fixtures in `tests/fixtures/ae10` provide a reproducible positive control, boundary cases and violations. They are neither a calibrated physical FEM model nor a representative sample of real research. There are no precision/recall estimates. Independent verification requires access to the unchanged spec, the exact local evidence files, and the installed scientific policy. A top-level checksum alone is insufficient: the verifier rebuilds the graph and re-executes the scientific rule from those inputs.

## Safe publication

Published generations are content-addressed, written atomically and guarded by a process lock. The `LATEST.json` pointer reflects the **last attempted audit**, and a failed attempt invalidates prior apparent success. Symlinks in source paths or output paths are rejected, including nested directory symlinks. Publication is separate from the authoritative evidence and source root, never modifies them, and runs only when invoked manually.

A Python process reading untrusted concurrently modified files does not by itself constitute a hardened kernel sandbox or a cryptographically authenticated author identity. AE-10 is designed for trusted CI/scientific workspaces. Programmatic validation does not replace peer review or numerical verification.

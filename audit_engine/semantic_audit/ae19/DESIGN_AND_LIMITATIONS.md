# AE-19/G9.21 — Historical GitHub validation-log outcome concordance

## Exact scope

AE-19 introduces an independently labeled, source-byte-pinned **historical run-outcome** comparison using two user-uploaded real G9.20 GitHub Actions log archives (initial failed run and corrected passing run). It is an operational evidence-admission and concordance benchmark, **not** a root-cause classifier, general programming-defect benchmark, or external certification.

The casebook contains the exact downloaded text for four selected GitHub step logs per run (declared pytest execution, detached evidence verification, immutable bundle publication, and catalog verification). Its manifest records the SHA-256 of each original user-supplied archive; the original complete ZIPs are **not** packaged. Checksums protect the supplied data against accidental or unauthorized changes but do **not** attest GitHub as its producer.

The manually authored labels are separate from the parser, with explicit declared provenance. AE-19 compares each parsed outcome with the manually reviewed reference statuses. All source inputs are data, not executable instructions.

## Existing components reused

- AE-01 canonical evidence hashing and atomic publication.
- AE-16 `build_report` to inspect a reconstructed, explicitly unauthenticated declaration of required targeted and regression steps.
- The existing SemanticGraph through AE-16, rather than building a second verification engine.
- No source/test/script from the history corpus is executed.

## Confirmed historical nuance

The **failed** G9.20 validation run still successfully published a verified *failure-evidence* bundle and verified its catalog. Evidence publication and test acceptance are intentionally modeled as separate dimensions. Nested expected-failure tests inside the central validation engine are outside the actual pytest-execution step and must not be treated as the outer run result.

## What success means

A GitHub pass for G9.21 establishes that (a) the parser agrees with the *two* manually reviewed user-supplied historical references, (b) admission/replay checks remain in force, and (c) AE-16 preserves incomplete status on the failed run. It says **nothing** about statistical real-world defect detection performance beyond this bounded sample.

The original two uploaded archives are not included, so their manifest SHA-256s remain provenance descriptors rather than independently reproduced original-archive digests within this package. If independent authenticated provenance is required, obtain GitHub API run records and original run artifacts with verifiable commit/step identities under separate authorization.

## Deferred

Independent developer-reviewed causal diagnosis, multi-repository samples, unknown logging dialects, branch/commit authenticated workflow traces, Python failure semantics and full charter C01–C15 effectiveness remain unverified. The report contains zero verified findings or causes.

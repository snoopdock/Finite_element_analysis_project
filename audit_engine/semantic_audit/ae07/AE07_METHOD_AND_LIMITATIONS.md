# AE-07: independently replayed assurance portfolio

## Evidence contract

AE-07 accepts 1–16 explicit AE-06 publications. Before aggregating anything, it invokes the AE-06 detached publication verifier, which independently reconstructs each AE-06 assessment from sealed AE-01, AE-04 and AE-05 evidence. It reopens the AE-06 publication after verification and matches the assessment digest, then independently reads the exact current AE-01 generation and verifies its correspondence with AE-06. The AE-07 publication verifier rederives the **complete portfolio**, compares canonical bytes and also verifies the SARIF projection. SHA-256 is used for accidental or adversarial byte changes; it does **not** authenticate a malicious publisher with full write access to all authoritative sources.

## Gate precedence

- `blocked_verified_policy_violations`: a currently verified architecture finding exists in any included source generation.
- `inconclusive_incomparable_source_or_policy`: the included current generations, versioned policy configurations or selected source path scopes do not agree, and no verified violation took precedence.
- `inconclusive_required_coverage`: an included scan or remediation assessment is incomplete/unassessable.
- `human_review_required`: independently verified bounded-absence candidates require human disposition.
- `bounded_evidence_ready_for_human_review`: no preceding blocker within this **explicitly enumerated** evidence set. Not a release authorization, compliance certification, or clean repository verdict.

All outcomes carry `release_authorized=false`. Priorities P0/P1/P2 are deterministic review categories, not probabilities of a defect. Individual module-level evidence is preserved in the review-task register. Identical tasks and verified finding identities are deduplicated, and `open_finding_occurrences` deliberately records how often a finding appears across included assessments.

## Publication and interchange

AE-07 stores immutable, deterministic `portfolio.json`, `results.sarif` and `SEAL.json` under a digest-named generation. `LATEST.json` is invalidated at the start of every publication attempt and points to an existing completed generation only after integrity checking. Every output root and source root is checked for path overlap and symlink components. A failed publication does not reactivate stale success. SARIF 2.1.0 results include **only current independently verified architecture findings**, with their repository-relative source file, source SHA-256, line, occurrence ID, and rule ID; missing coverage and human closure tasks remain in the native portfolio instead of being mislabeled as code violations.

## Reproducibility, threat model and limits

The independent verifier checks exact source-bound generations and native upstream verification contracts, not arbitrary runtime Python semantics or unrestricted scientific correctness. Accepted evidence can be historical; the verifier does not re-run an old source checkout unless the upstream verification contract explicitly requires it. AE-07 outputs are not cryptographically signed, reviewer identity is not authenticated, and it does not grant deployment authorization. Source repository contents and test workspaces are trusted inputs and should be executed only in appropriately isolated CI. Multiple partial portfolios never become a whole-repository compliance certification. SARIF is a transport format, not proof of correctness.

There is deliberately **no automatic GitHub workflow** and no autonomous modification of audited source files. CLI JSON paths refer to trusted local evidence publications and are not fetched from external URLs. A missing or malformed input is an error, not an empty portfolio.

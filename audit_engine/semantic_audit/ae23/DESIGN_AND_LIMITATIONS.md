# AE-23 — Offline Git-tree-bound external evaluation contract

## Motivation

AE-21 and AE-22 correctly decline upstream-byte-authentication claims. G9.25 adds an **offline intake and scoring contract** for genuinely supplied Git bug/fix revisions, instead of laundering curated examples into real-world detection results. BugsInPy is an appropriate candidate for *future* ingest because it identifies faulty and fixed repository revisions and associated tests. **No BugsInPy revisions have been downloaded or independently reproduced in this patch.**

## Scientific claims: deliberately separated

| Claim | AE-23 establishes | Still required |
|---|---|---|
| Source byte checksum | Exact SHA-256 of bytes from Git blob | Independent trusted anchor for expected digest |
| Commit/tree containment | Git commit contains the declared blob at exact path | Upstream provider identity and independent commit authenticity |
| Defect label | At most two distinct self-reported reviewers agree | Independent adjudication and behavioral reproduction |
| Holdout | Identical source bytes cannot occur in development and holdout | Historical/test contamination analysis, genuinely blind selection |
| Static signal | AE-15 bounded possibly-unbound observation | No inference of actual runtime path or proof of programming defect |
| Accuracy | Descriptive counts on *self-reported reviewer-agreed* pairs | Independently reproduced, source-authenticated, representative defects |

**Trust distinction:** A locally supplied Git repository can be fabricated or rewritten together with `LOCK.json`. Hash agreement proves consistency, not external origin. Two distinct reviewer IDs cannot prove those reviewers are independent. The independent replay gate compares against current supplied Git objects, not against GitHub's authenticated history.

## Stage model

1. An operator independently acquires external repositories and documents their original URL, exact bug/fix commits, blob OIDs, source SHA-256, applicable defect family, and source paths. This patch never downloads or checks out repositories and does not execute them.
2. `predict`: the auditor reads only canonical `LOCK.json` plus local Git source objects; checks all declared bytes/identities; and computes AE-15 observations **before** it is given any reviewer-label document.
3. `score`: accepts a canonical predictions document and canonical `REVIEWS.json`; score is **not replay-verified** merely because both JSON documents are canonical. Refusing unreviewed cases is not the same as assuming they are clean.
4. `verify`: independently reopens the local Git objects, regenerates predictions, scores the canonical review file, and compares the entire report with the submitted assessment. In a real independent study, reviewers must be selected and their identities verified outside this repository.

`LOCK.json` must use `ae23/external_case_lock/v1` with precise fields checked by `validate_lock()`. Its `protocol` is exactly:

```json
{"execution":"static_only","review_policy":"two_distinct_reviewers_required_for_adjudicated_subset","source_authority":"git_tree_integrity_only"}
```

Each case has `case_id`, `repository`, `family`, `split` (`development` or `holdout`), `scope` (`bounded_static` or `unsupported_semantics`), `signal_variable` (identifier or null), and `faulty` / `correct` records (`commit`, `path`, `git_blob_oid`, `sha256`). `repositories` maps a declared ID to a `claimed_upstream_url` string. Neither URLs nor labels are authenticated by this mechanism.

`REVIEWS.json` uses `ae23/reviewer_labels/v1` with `lock_sha256` and a `reviews` array. Each review has `case_id`, `reviewer_id`, `faulty`, `correct`, `rationale`, and `prediction_blinded`. Independent review is **asserted, not authenticated**. Only exactly two distinct, self-attested, agreeing, nominally blinded reviews permit provisional scoring. All other cases remain visible as unadjudicated. An upstream behavior oracle has not been executed.

## Security and correctness invariants

- No `eval`, `exec`, direct Python imports from source, `git checkout`, git fetch, network requests, dynamic shell invocation or automatic repository updates.
- Local Git commands are constrained to read-only object inspection and bounded by time/output size. This is **not** an OS sandbox for malicious Git metadata.
- Reject noncanonical JSON, symlinked inputs, nonregular Git blob modes, path traversal, changed bytes, unexpected identities, duplicate cases, and identical bytes leaked across train/holdout.
- No missing static signal ever becomes a verified clean finding. All unadjudicated, unknown and unsupported cases remain in the all-sample denominator.
- Replaying a submitted report against the current supplied Git objects is mandatory before downstream publication. A score-only result is explicitly not provenance-verified.

## Dataset sampling and future requirements

A credible BugsInPy exercise should: pre-register a selection protocol across projects and defect families; use pinned original faulty and corrected full commit IDs; independently verify the upstream repo owner and commit objects; reproduce buggy and fixed outcomes under isolated locked toolchains; perform blind adjudication with independent reviewers; lock the holdout split before analyzer development; and report false positives, misses, abstentions and inconclusive outcomes. Running this patch's local toy Git repository tests does **not** accomplish any of those additional scientific steps.

# AE-05: Evidence-Bound Human Review and Decision Memory

## Purpose and evidence boundary

AE-05 does not recalculate source code graphs itself or create an alternative verifier. It loads **AE-04 sealed campaigns** using AE-04 independent publication verification. That verification derives evidence from sealed AE-01 source generations, AE-02/2.1 impact comparisons, and (when present) replays AE-03 mutation outcomes. Review obligations bind exactly to the **campaign SHA-256** and exact source-occurrence/finding witnesses. A changed campaign, invalid AE-04 `LATEST`, mutated workspace, or changed generation invalidates the journal's current authority.

## State machine

A deterministic review packet contains every AE-04 source-task obligation plus an unavoidable **campaign gate** obligation, including for no-change scans. P0 policy violations, P1 full-scope rechecks, and all nonpassing or incomplete campaigns forbid `acknowledge`. Permitted actions are `acknowledge`, `requires_action`, and `dispute`. The last recorded action controls the review workflow for an obligation, but cannot alter the underlying evidence or reclassify any architecture policy result. All events require a nonempty actor label, an explanation, an explicit evidence reference selected from the campaign, and a monotonically chained event hash.

Journal outcomes: `pending_human_review`, `review_recorded_with_open_actions`, `review_recorded_not_a_policy_pass`, or `bounded_review_recorded`. **Only** a previously independently verified AE-04 `bounded_architecture_policy_pass` plus complete acknowledged review obligations can produce `bounded_review_recorded`, and it is *not* a claim about global software correctness. A human cannot waive a P0 defect or missing policy coverage into compliance; genuine fixes require a new sealed source audit and campaign.

## Durable publication

Review state is projected into the existing G3 `AuditLongTermMemory` as `ae05_review_event` records bound to the campaign snapshot. AE-05 adds deterministic ordered event chaining, which G3 memory alone does not supply. Publication uses output-root and symlink guards, an exclusive filesystem lock over read-modify-write, separate immutable content-addressed generations, atomic fsync-backed member writes and a failure-invalidating `LATEST` marker. Detached verification checks every layer (AE-04 campaign, event chain, G3 memory reconstitution, record seal, published artifact membership). Interrupted latest attempts never silently expose a prior successful review as current.

## Caveats

- Hash chains and SHA-256 publication seals provide **integrity relative to trusted anchors**, not identity authentication, nonrepudiation, or defense against an actor able to replace the complete evidence store. Actor names are unauthenticated labels. A signature or trusted remote transparency log is out of scope.
- Reviews are **not** autonomous approval, code changes, scientific correctness proofs, or permission to merge/deploy. The only release-like gate is a bounded audit-review bookkeeping state.
- The AE-04 source generation ordering is caller-supplied. No authenticated Git ancestry is inferred from historical archive IDs.
- Mutation replay runs trusted tests. Workspace copying is not a security sandbox. Use isolated CI and explicit `--replay-mutation` + `--mutation-root` to verify campaigns containing AE-03 outcomes.
- Execution exit 0 on `verify` means evidence validation, not policy pass. On `init`/`record`, 3 is review required and 4 is invalid input/evidence; exit 0 on a bounded review is only scoped.
- The `LATEST` pointer is the sole current outcome. Prior content-addressed generations remain available for forensic interpretation but cannot override a failed or incomplete latest run.

## Reproducibility

```
python -m audit_engine.semantic_audit.ae05 init --campaign-output CAMPAIGN --before-output AE01_BEFORE --after-output AE01_AFTER --output REVIEW
python -m audit_engine.semantic_audit.ae05 record --campaign-output CAMPAIGN --before-output AE01_BEFORE --after-output AE01_AFTER --output REVIEW --obligation-id ID --action requires_action --actor REVIEWER --note "Needs new verified source audit"
python -m audit_engine.semantic_audit.ae05 verify --campaign-output CAMPAIGN --before-output AE01_BEFORE --after-output AE01_AFTER --output REVIEW
```

The mandatory manual-only GitHub dispatcher profile `validation/profiles/G9.6.yaml` includes AE-05 and previous AE-04/G3 acceptance controls. No changes to `main` or automatic workflow triggers are required.

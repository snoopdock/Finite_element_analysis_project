# AE-29 — Iterative Repository Audit and Controlled Self-Correction Protocol

## Purpose

AE-29 turns the previously separated audit, neural interpretation, symbolic
reasoning, and verification components into a bounded control loop for
repository maintenance.

The intended flow is:

```text
repository snapshot
      ↓
repository audit findings
      ↓
AE-28 neural investigation handoff
      ↓
repair proposal
      ↓
isolated candidate snapshot
      ↓
independent verification
      ↓
post-repair audit
      ↓
decision record
      ↓
next bounded iteration
```

AE-29 is about **repository auditing and controlled correction**. It does not
generate scientific content, perform scientific writing, or establish
scientific truth.

## Authority model

The authority levels are deliberately separated:

```text
repository bytes
    ↓
audit observation
    ↓
LLM/neural interpretation
    ↓
repair candidate
    ↓
independent verification
    ↓
post-repair audit
    ↓
accepted controller state
```

An LLM remains a proposal generator. It cannot:

- mark a finding as verified;
- authorize a repair;
- mutate the authoritative checkout;
- modify validation controls;
- modify decision memory as part of a repair;
- turn historical memory into evidence.

## Repository snapshots

`RepositorySnapshot` is a detached bounded mapping of safe relative paths to
bytes. Its digest is computed from the canonical path/digest/size manifest.
Insertion order therefore cannot change snapshot identity.

A snapshot is not a live filesystem view.

## Audit findings

An AE-29 finding is bound to:

- the repository snapshot digest;
- the auditor identity and version;
- the auditor run digest;
- exact evidence file digests;
- a deterministic finding fingerprint.

Changing an evidence file invalidates the finding.

## Neural investigation handoff

AE-28 produces the model interpretation. AE-29 receives a compact handoff
containing:

- the verified interpretation digest;
- the request digest;
- the current repository snapshot digest;
- candidate identities;
- a fixed candidate-only authority declaration.

The handoff is therefore a bridge between AE-28 and the repository correction
loop. It does not duplicate or replace AE-28's exact replay verification.

## Repair proposals

A repair is a data object, not an executable command.

The only operations in v1 are:

- `write_file`;
- `delete_file`.

Every operation is bound to the exact pre-repair file digest. The repair is also bound to the exact finding fingerprints it claims to correct. Writes contain a content digest and base64 representation. Operations are canonicalized.

The following control paths are protected from AE-29 repair proposals:

- `.github/`;
- `validation/`;
- `validation-engine/`;
- `decision_memory/`.

This prevents a repair from rewriting the validation gate, workflow
authorization, or historical memory in the same correction step.

## Verification gate

A repair cannot change the controller's current state until an independent
verification result is supplied.

A `passed` verification must contain only passed checks.

The verification result is itself a sealed, content-addressed record, but its
`repository_truth_verified` flag remains `false`: cryptographic consistency
does not turn a verifier receipt into an unrestricted truth claim.

## Post-repair audit gate

Passing tests is not enough.

After a repair passes independent verification, the candidate snapshot must
receive a fresh audit. The targeted open finding(s) must no longer remain open.

If a targeted finding persists, the repair is rejected and the previous state
remains current.

If the targeted findings are resolved while unrelated findings remain, the
repair is accepted and the session remains active.

## Decision memory

Decision records contain:

- the input and output snapshot digests;
- finding context;
- repair identity;
- verification identity;
- decision and reason;
- bounded lesson codes.

Memory retrieval uses deterministic exact-key matching. It can report
historical patterns, but:

```text
memory hint ≠ evidence
memory hint ≠ verifier
memory hint ≠ authorization
memory hint ≠ policy change
```

The purpose is to create a safe substrate for later evaluation of whether
recorded decisions can improve planning.

## Iteration limits

The loop is hard bounded to eight iterations in v1. This is a safety
constraint, not a performance recommendation.

The controller cannot continue past its declared budget.

## Filesystem materialization

An accepted snapshot can be materialized into a **new staging directory**.
AE-29 never overwrites an existing directory and never writes into the
authoritative checkout.

A later workflow may decide whether a staged state should become a Git
change. That authorization is outside AE-29 v1.

## What AE-29 deliberately does not do

- invoke a live LLM;
- construct the production LLM prompt;
- execute arbitrary commands returned by an LLM;
- automatically commit to Git;
- modify the authoritative checkout;
- modify validation workflows;
- rewrite decision memory;
- infer scientific or real-world truth.

The production prompt and live provider integration are deliberately deferred
until the interfaces have been evaluated through AE-30.

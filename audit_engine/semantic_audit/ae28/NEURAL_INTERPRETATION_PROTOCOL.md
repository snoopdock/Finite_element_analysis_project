# AE-28 — Neural/LLM Interpretation Protocol v1

## Purpose

AE-28 is the first layer that can consume an actual neural/LLM result as an
input to the Audit Engine. It is intentionally **provider-neutral** and
**prompt-neutral**.

The model is external to the repository runtime in this milestone:

```text
repository state
      |
      v
AE-28 request envelope
      |
      |  external adapter / LLM invocation
      v
raw model output + normalized response
      |
      v
AE-28 provenance and binding checks
      |
      v
AE-27 candidate-only proposal
      |
      v
AE-25 symbolic consequences
```

AE-28 does not call a provider, access a network, execute source code, or
mutate the authoritative graph.

## Request

A request records:

- exact AE-24 contract digest;
- exact admitted graph fingerprint;
- exact AE-26 semantic fingerprint;
- exact AE-26 hypothesis fingerprint;
- semantic vocabulary digest;
- authoritative context occurrence IDs;
- a task/prompt digest;
- an input artifact manifest.

The task/prompt itself is intentionally not prescribed by AE-28. This keeps
prompt formulation independent from the audit-state contract. Prompt design
and runtime LLM orchestration are deferred until after AE-30.

Only `declared` and `observed` context occurrences are admitted as authoritative
model context.

## Model response

A normalized response contains:

- request digest;
- proposal identity;
- model identity;
- model trace;
- candidate assertions;
- explicit evidence links;
- response digest.

The raw model output is supplied separately as bounded bytes. AE-28 records
its SHA-256 but does not infer truth from the digest.

The normalized response is canonical JSON. An external adapter may translate
provider-specific text/JSON into this normalized form before admission.

## Authority

The model may propose candidate relationships.

The model cannot:

- mark a candidate verified;
- mark a candidate authoritative;
- promote a candidate;
- mutate the SemanticGraph;
- create evidence merely by asserting confidence.

AE-27 remains the next authority gate.

## Determinism

Candidate assertions and evidence links are canonicalized by stable identities
before the AE-27 proposal is created. Thus equivalent model responses whose
only difference is list ordering produce the same proposal digest.

The raw model-output digest can still differ when the provider returned
different bytes. Exact model-output provenance and semantic proposal identity
are therefore intentionally distinct.

## Replay

Exact replay requires:

```text
current contract bytes
+ current source evidence
+ original request
+ original raw model output bytes
+ original normalized response
```

AE-28 reconstructs the proposal and interpretation and compares the complete
result.

A changed repository state, context, task digest, raw output, model trace,
candidate set, evidence links, or proposal digest prevents successful replay.

## Security boundary

AE-28 rejects:

- noncanonical envelopes;
- unknown fields;
- stale requests;
- missing/invalid digests;
- model/trace identity disagreement;
- model context mismatch;
- candidate origin violations;
- invalid AE-27 relationships;
- candidate-as-evidence relationships;
- oversized raw output;
- automatic-authority fields.

Validation errors are classified at the narrowest AE-28 contract boundary:
outer-response violations report an envelope error, model-trace violations
report a model-trace error, and model-metadata violations report a model-
metadata error. A structurally valid response that reaches AE-27 is reported
separately as an AE-27 proposal-rejection error. This distinction is intended
for deterministic automated auditing and later controlled repair.

No network, shell, `eval`, `exec`, source import, or repository mutation is
part of this layer.

## Deferred runtime question

The exact LLM input prompt, prompt template, retrieval formatting, system
instructions, tool-selection strategy, and provider integration are **not
defined here**. AE-28 records a task/prompt digest so that those future choices
can be bound and audited without making them part of the semantic core.

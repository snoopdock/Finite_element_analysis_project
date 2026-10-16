# AE-26 semantic model — G9.28 corrective release

## 1. Scope

AE-26 defines a language-independent semantic layer above AE-24 contract
admission and AE-25 symbolic reasoning.

The corrective release changes the semantic vocabulary schema from:

`ae26/semantic-vocabulary/v1`

to:

`ae26/semantic-vocabulary/v2`

and the evolution report schema from:

`ae26/semantic-contract-diff/v1`

to:

`ae26/semantic-contract-diff/v2`

The schema change is intentional: the meaning of semantic identity has been
strengthened and the previous v1 projection was not sufficiently complete or
internally consistent for further neurosymbolic development.

## 2. Three identities

AE-26 explicitly separates:

1. **Entity identity** — the component, artifact, action, or check.
2. **Occurrence identity** — the individual source assertion (`id`) that
   witnesses an observation.
3. **Semantic identity** — the canonical meaning of the relationship.

An occurrence ID and evidence `source_id` are never inputs to a semantic
relationship's `semantic_id`.

Therefore:

```text
p1: producer PRODUCES artifact
p2: producer PRODUCES artifact
```

with identical normalized meaning are one semantic fact with two provenance
occurrences.

## 3. Semantic relationship record

Every admitted relationship is normalized to:

```text
vocabulary_digest
subject
predicate
object
subject_kind
object_kind
origin
meaning
binding
```

The semantic ID is the SHA-256 digest of that canonical record.

The semantic fingerprint is the SHA-256 digest of the complete canonical
authoritative semantic state:

```text
schema version
vocabulary digest
entity identities and kinds
admitted semantic relationships
semantic policies
semantic coverage state
```

Contract hashes, graph fingerprints, source digests, occurrence IDs, and
evidence source IDs remain available for provenance but do not contaminate
semantic identity.

## 4. Interface meaning and producer binding

`PRODUCES` and `CONSUMES` may carry:

- `format`
- `schema_id`
- `meaning_id`

A `CONSUMES` assertion may additionally select:

- `producer`
- `producer_occurrence`

The occurrence selector is **not** copied into semantic identity.

Instead, AE-26 resolves it to a semantic producer contract:

```text
CONSUMES
  binding:
    producer = Component-X
    resolution = resolved
    producer_contract = {
      format,
      schema_id,
      meaning_id
    }
```

This prevents the earlier inconsistency in which AE-25 could reason differently
about two producer contract versions while AE-26 considered the consumer
semantically unchanged.

If the producer contract cannot be resolved, the binding records an explicit
state such as:

- `unresolved`
- `ambiguous`
- `candidate_only`

No occurrence ID is exposed as semantic meaning.

## 5. Authoritative facts versus hypotheses

AE-24 permits `candidate` assertions for future neural or investigative use.
AE-26 now separates them explicitly.

### Authoritative semantic projection

Contains only:

- `declared`
- `observed`

These determine `semantic_fingerprint`.

### Hypothesis projection

Contains:

- `candidate`

These determine `hypothesis_fingerprint`.

Candidate assertions remain visible in the occurrence/evidence projection and
can be retrieved by future proposal systems, but adding or changing a
candidate cannot alter the authoritative semantic fingerprint.

This is not a truth claim. `declared` and `observed` remain source-submitted
states, not externally authenticated facts.

## 6. Semantic evolution

The diff engine is derived from the same canonical representation used by
snapshot generation.

It reports:

- relationship added/removed;
- interface meaning changed;
- interface binding changed;
- entity added/removed;
- entity semantic-kind changed;
- policy added/removed;
- coverage added/removed;
- coverage completeness changed;
- hypothesis added/removed.

The diff does not use a dictionary keyed only by
`(subject, predicate, object)`. Parallel interface variants therefore cannot
overwrite each other.

All set and pairing operations are canonically ordered, making results
independent of input assertion order.

## 7. Evolution status

Possible statuses are:

- `no_semantic_change_in_admitted_projection`
- `semantic_change_detected`
- `hypothesis_change_detected`
- `semantic_and_hypothesis_change_detected`

A hypothesis-only change therefore remains visible without falsely reporting
an authoritative semantic change.

## 8. Vocabulary versioning

The semantic fingerprint includes a `vocabulary_digest` derived from the
supported relation vocabulary and concept types.

A future change to semantic relation definitions must therefore either:

1. produce a different vocabulary digest under the same schema only when the
   change is explicitly accepted as compatible, or
2. increment the semantic schema version when the meaning is incompatible.

This prevents silent semantic-model drift.

## 9. Verification

`verify_snapshot()` independently replays AE-24 admission and AE-26
normalization.

`verify_projection()` independently replays a serialized semantic projection.

`verify_diff()` independently reconstructs the complete evolution report.

Rehashing a modified report is insufficient because verification compares the
complete replayed object.

## 10. Limits

AE-26 does not establish:

- source authenticity;
- runtime causality;
- deployed behavior;
- external truth;
- OWL-DL entailment;
- neural correctness.

The semantic layer is a deterministic interpretation of source-bound
AE-24 assertions under the versioned vocabulary defined here.

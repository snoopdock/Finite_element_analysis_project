# AE-26 semantic model

## 1. Three identities

The model keeps three distinct identities:

1. **Entity identity** — the component, artifact, action, or check being discussed.
2. **Occurrence identity** — the specific source assertion that witnesses a relation.
3. **Semantic identity** — the normalized relation and its meaning, independent of
   which adapter or observation produced it.

This distinction is essential for many-to-many evidence. Repeating an
observation must not create a new semantic fact, while deleting the occurrence
must remain visible to provenance/audit layers.

## 2. Relation vocabulary

| Relation | Domain → range | Character |
|---|---|---|
| `PRODUCES` | Component → Artifact | interface |
| `CONSUMES` | Component → Artifact | interface |
| `PERFORMS` | Component → Action | observed behavior |
| `FORBIDS` | Component → Action | constraint |
| `DEPENDS_ON` | Component → Component | dependency |
| `REQUIRES_CHECK` | Component → Check | obligation |
| `HAS_CHECK` | Component → Check | verification observation |

Interface relations may carry `format`, `schema_id`, and `meaning_id`.
`meaning_id` is deliberately an explicit identifier: syntactic compatibility
does not imply semantic compatibility.

## 3. Language neutrality

The semantic layer does not consume Python ASTs, Rust HIRs, C++ ASTs, or
workflow-specific syntax. Those artifacts belong to adapters that produce
admitted relations.

Equivalent admitted relations should therefore produce equivalent semantic
fingerprints even when their source languages differ.

## 4. Evolution

A semantic diff separates:

* relation additions/removals;
* entity semantic-kind changes;
* interface meaning changes;
* provenance changes such as declared → observed.

The diff is evidence of a change in the admitted semantic projection. It is
not proof of a deployed runtime change.

## 5. Non-monotonic evidence

`candidate` relationships are preserved as hypotheses but are not silently
converted into `declared` or `observed` facts. Future neural systems must use
AE-27's proposal gateway and explicit adjudication path.

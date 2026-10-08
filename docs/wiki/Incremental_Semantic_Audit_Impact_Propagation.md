# Incremental Semantic Audit Impact Propagation

## Why Incrementality Matters

An autonomous scientific repository should not rediscover and re-verify every fact after every small edit. At the same time, reuse is only trustworthy when the system can explain why previous evidence remains applicable.

G3.2.1 addresses this through explicit dependency footprints.

## Direct Versus Inherited Impact

A direct impact originates in graph evolution. Examples include removal of evidence or modification of an entity used by an analysis.

An inherited impact is transmitted through audit lineage:

```text
analysis requires recheck
        ↓
receipt requires recheck
        ↓
finding requires reevaluation
```

This is dependency propagation, not causal proof that the finding became false.

## Locality

Structural and dependency analyses are bounded neighborhood analyses. Their existing source entities, discovered entities, depth and relation filters allow some changes to be proven irrelevant.

Path analysis remains more conservative around its known path/frontier because a new relation can alter path existence or shortest-path selection.

Unknown/global analyses remain conservative by design.

## Relation Filtering

If a dependency analysis explicitly examines only `DEPENDS_ON`, adding a `DOCUMENTS` edge inside the same neighborhood does not force a dependency recheck. This prevents vocabulary-unrelated edits from expanding the audit workload.

## Safety Rule

Locality is used only when the analysis contract provides enough information to justify it. Lack of dependency information causes conservative recheck, never silent reuse.

# Branch architecture comparison

- Base: main at fe7027ba8395857ed396c23c422138d22ffbe496
- Compared branch: stage1/section-uuids at c17382c74b6cb0d85afc9457cc46a73150aeb07b
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 4930 | 17562 |
| Edges | 7691 | 44670 |

## Identity-based graph delta

- Common nodes: 2438
- Nodes only in main: 2492
- Nodes only in stage1/section-uuids: 15124
- Common relationships: 4707
- Relationships only in main: 2984
- Relationships only in stage1/section-uuids: 39963

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 251
- Commits unique to stage1/section-uuids: 952
- Files changed from merge base on main: 139
- Files changed from merge base on stage1/section-uuids: 1652

See git-lineage.json for complete file inventories and the symmetric commit list.

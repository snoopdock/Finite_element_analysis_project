# Branch architecture comparison

- Base: main at 0b6a3ed68da2e42509493504c88851c06d64bedd
- Compared branch: stage1/section-uuids at 7771d637cd613bf5cfc8c847108cd0c6eb28c98f
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5017 | 17902 |
| Edges | 7790 | 45680 |

## Identity-based graph delta

- Common nodes: 2499
- Nodes only in main: 2518
- Nodes only in stage1/section-uuids: 15403
- Common relationships: 4781
- Relationships only in main: 3009
- Relationships only in stage1/section-uuids: 40899

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 285
- Commits unique to stage1/section-uuids: 1131
- Files changed from merge base on main: 155
- Files changed from merge base on stage1/section-uuids: 1697

See git-lineage.json for complete file inventories and the symmetric commit list.

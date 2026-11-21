# Branch architecture comparison

- Base: main at 6476e7dbae7edd98c8e483974e56668c84037371
- Compared branch: stage1/section-uuids at 1ed0471832b660e8c29a946e4655e1ed981106bf
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 4930 | 17765 |
| Edges | 7691 | 45281 |

## Identity-based graph delta

- Common nodes: 2438
- Nodes only in main: 2492
- Nodes only in stage1/section-uuids: 15327
- Common relationships: 4707
- Relationships only in main: 2984
- Relationships only in stage1/section-uuids: 40574

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 256
- Commits unique to stage1/section-uuids: 970
- Files changed from merge base on main: 153
- Files changed from merge base on stage1/section-uuids: 1676

See git-lineage.json for complete file inventories and the symmetric commit list.

# Branch architecture comparison

- Base: main at 5fb0b5de6357e5746d71a1d9f8cdc985aa6599b0
- Compared branch: stage1/section-uuids at f55f10d5438b297b423f7e5d456f7eff6969d8ad
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 4930 | 17681 |
| Edges | 7691 | 44971 |

## Identity-based graph delta

- Common nodes: 2438
- Nodes only in main: 2492
- Nodes only in stage1/section-uuids: 15243
- Common relationships: 4707
- Relationships only in main: 2984
- Relationships only in stage1/section-uuids: 40264

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 255
- Commits unique to stage1/section-uuids: 957
- Files changed from merge base on main: 153
- Files changed from merge base on stage1/section-uuids: 1662

See git-lineage.json for complete file inventories and the symmetric commit list.

# Branch architecture comparison

- Base: main at 1178c312e8e5237e2aad702c53a0fd99a0f5bfb2
- Compared branch: stage1/section-uuids at 2efb8b44e69a0f3a4512f8164668c41af4127d75
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5888 | 18720 |
| Edges | 9901 | 47744 |

## Identity-based graph delta

- Common nodes: 3184
- Nodes only in main: 2704
- Nodes only in stage1/section-uuids: 15536
- Common relationships: 6618
- Relationships only in main: 3283
- Relationships only in stage1/section-uuids: 41126

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 332
- Commits unique to stage1/section-uuids: 1420
- Files changed from merge base on main: 208
- Files changed from merge base on stage1/section-uuids: 1756

See git-lineage.json for complete file inventories and the symmetric commit list.

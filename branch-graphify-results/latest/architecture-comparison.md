# Branch architecture comparison

- Base: main at 192c86b74d83f31345f8714fbe28c793cac13ec7
- Compared branch: stage1/section-uuids at 2efb8b44e69a0f3a4512f8164668c41af4127d75
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5865 | 18720 |
| Edges | 9805 | 47744 |

## Identity-based graph delta

- Common nodes: 3187
- Nodes only in main: 2678
- Nodes only in stage1/section-uuids: 15533
- Common relationships: 6621
- Relationships only in main: 3184
- Relationships only in stage1/section-uuids: 41123

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 328
- Commits unique to stage1/section-uuids: 1420
- Files changed from merge base on main: 207
- Files changed from merge base on stage1/section-uuids: 1756

See git-lineage.json for complete file inventories and the symmetric commit list.

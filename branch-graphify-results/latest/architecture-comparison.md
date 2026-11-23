# Branch architecture comparison

- Base: main at ededbe2e8fdc0d2bcd3736cf9b90a17f48c945ef
- Compared branch: stage1/section-uuids at e6a985d44cc97521f730fc717f35fd4a0d9bf4cd
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5288 | 17987 |
| Edges | 8101 | 46018 |

## Identity-based graph delta

- Common nodes: 2499
- Nodes only in main: 2789
- Nodes only in stage1/section-uuids: 15488
- Common relationships: 4781
- Relationships only in main: 3320
- Relationships only in stage1/section-uuids: 41237

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 326
- Commits unique to stage1/section-uuids: 1203
- Files changed from merge base on main: 158
- Files changed from merge base on stage1/section-uuids: 1706

See git-lineage.json for complete file inventories and the symmetric commit list.

# Branch architecture comparison

- Base: main at d0c88b3f7a1d65e46908f94fe293b863805b4c94
- Compared branch: stage1/section-uuids at f3ca30397a5c303746d8a4cb7c1c6da3dd3d7c9e
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5017 | 17902 |
| Edges | 7790 | 45677 |

## Identity-based graph delta

- Common nodes: 2499
- Nodes only in main: 2518
- Nodes only in stage1/section-uuids: 15403
- Common relationships: 4781
- Relationships only in main: 3009
- Relationships only in stage1/section-uuids: 40896

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 283
- Commits unique to stage1/section-uuids: 1122
- Files changed from merge base on main: 155
- Files changed from merge base on stage1/section-uuids: 1697

See git-lineage.json for complete file inventories and the symmetric commit list.

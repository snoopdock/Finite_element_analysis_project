# Branch architecture comparison

- Base: main at 21c13b0b7c951bbacbd63a1fd2546c450f4fc8c7
- Compared branch: stage1/section-uuids at c1f97a9402d0d98490eb6ad7efff5f1ae0179c6a
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5017 | 17902 |
| Edges | 7790 | 45681 |

## Identity-based graph delta

- Common nodes: 2499
- Nodes only in main: 2518
- Nodes only in stage1/section-uuids: 15403
- Common relationships: 4781
- Relationships only in main: 3009
- Relationships only in stage1/section-uuids: 40900

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 287
- Commits unique to stage1/section-uuids: 1147
- Files changed from merge base on main: 155
- Files changed from merge base on stage1/section-uuids: 1698

See git-lineage.json for complete file inventories and the symmetric commit list.

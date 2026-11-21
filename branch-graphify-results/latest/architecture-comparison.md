# Branch architecture comparison

- Base: main at 952c3e2a713abe34bca3259b20354897352f2271
- Compared branch: stage1/section-uuids at 6d198138dcc3c5e7bd87de64d9b7d9594b785509
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5021 | 17798 |
| Edges | 7795 | 45489 |

## Identity-based graph delta

- Common nodes: 2438
- Nodes only in main: 2583
- Nodes only in stage1/section-uuids: 15360
- Common relationships: 4707
- Relationships only in main: 3088
- Relationships only in stage1/section-uuids: 40782

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 277
- Commits unique to stage1/section-uuids: 1103
- Files changed from merge base on main: 155
- Files changed from merge base on stage1/section-uuids: 1695

See git-lineage.json for complete file inventories and the symmetric commit list.

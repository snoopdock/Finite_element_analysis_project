# Branch architecture comparison

- Base: main at 75bf9cc4aa608fcbb8854363906d57f8b28dc2f7
- Compared branch: stage1/section-uuids at c02eaaae23187a05152aca94b1c529b12df9b34f
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 4956 | 17788 |
| Edges | 7716 | 45464 |

## Identity-based graph delta

- Common nodes: 2438
- Nodes only in main: 2518
- Nodes only in stage1/section-uuids: 15350
- Common relationships: 4707
- Relationships only in main: 3009
- Relationships only in stage1/section-uuids: 40757

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 273
- Commits unique to stage1/section-uuids: 1100
- Files changed from merge base on main: 155
- Files changed from merge base on stage1/section-uuids: 1693

See git-lineage.json for complete file inventories and the symmetric commit list.

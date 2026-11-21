# Branch architecture comparison

- Base: main at d2b15b166611d62d638887318edc289ff8a7f73e
- Compared branch: stage1/section-uuids at bfaa7a8d627237b12fff3b1f5f90ce6bece9a250
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5017 | 17933 |
| Edges | 7790 | 45796 |

## Identity-based graph delta

- Common nodes: 2499
- Nodes only in main: 2518
- Nodes only in stage1/section-uuids: 15434
- Common relationships: 4781
- Relationships only in main: 3009
- Relationships only in stage1/section-uuids: 41015

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 291
- Commits unique to stage1/section-uuids: 1167
- Files changed from merge base on main: 156
- Files changed from merge base on stage1/section-uuids: 1701

See git-lineage.json for complete file inventories and the symmetric commit list.

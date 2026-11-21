# Branch architecture comparison

- Base: main at aeed218ce297efa93d45ccb0c955ac3e93fc4d19
- Compared branch: stage1/section-uuids at 342c9d55b1dc49ccf93759d0dce203723485ef17
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

- Commits unique to main: 294
- Commits unique to stage1/section-uuids: 1168
- Files changed from merge base on main: 156
- Files changed from merge base on stage1/section-uuids: 1701

See git-lineage.json for complete file inventories and the symmetric commit list.

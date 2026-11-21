# Branch architecture comparison

- Base: main at 9e7dcd0a377cce723311e30614a0de2a1ec04628
- Compared branch: stage1/section-uuids at bb325a89466ecfca875c50284cd186c0e417f96b
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5217 | 17987 |
| Edges | 8027 | 46018 |

## Identity-based graph delta

- Common nodes: 2499
- Nodes only in main: 2718
- Nodes only in stage1/section-uuids: 15488
- Common relationships: 4781
- Relationships only in main: 3246
- Relationships only in stage1/section-uuids: 41237

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 319
- Commits unique to stage1/section-uuids: 1188
- Files changed from merge base on main: 158
- Files changed from merge base on stage1/section-uuids: 1705

See git-lineage.json for complete file inventories and the symmetric commit list.

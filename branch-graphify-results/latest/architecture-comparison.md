# Branch architecture comparison

- Base: main at b7e05d92f040952bae210961eaa38d383ac2f65f
- Compared branch: stage1/section-uuids at 8db792e79c7e87fe9667af72f5b0eb7f4240d132
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

- Commits unique to main: 315
- Commits unique to stage1/section-uuids: 1184
- Files changed from merge base on main: 158
- Files changed from merge base on stage1/section-uuids: 1705

See git-lineage.json for complete file inventories and the symmetric commit list.

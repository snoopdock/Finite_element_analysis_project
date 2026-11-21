# Branch architecture comparison

- Base: main at 64fa7e662ffa5359fe4430b9273aa4a1bf6691f5
- Compared branch: stage1/section-uuids at ab942db734ea4e51492ff1c0c3e1a219ee821056
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5217 | 17960 |
| Edges | 8027 | 45925 |

## Identity-based graph delta

- Common nodes: 2499
- Nodes only in main: 2718
- Nodes only in stage1/section-uuids: 15461
- Common relationships: 4781
- Relationships only in main: 3246
- Relationships only in stage1/section-uuids: 41144

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 313
- Commits unique to stage1/section-uuids: 1173
- Files changed from merge base on main: 157
- Files changed from merge base on stage1/section-uuids: 1703

See git-lineage.json for complete file inventories and the symmetric commit list.

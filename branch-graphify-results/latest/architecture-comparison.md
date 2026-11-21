# Branch architecture comparison

- Base: main at dfabd1a6df326ad2f0f7598253cdb47f4552441c
- Compared branch: stage1/section-uuids at 9adc99b9511d0281b18be76d60865dcf13bb16b0
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 4989 | 17847 |
| Edges | 7762 | 45535 |

## Identity-based graph delta

- Common nodes: 2497
- Nodes only in main: 2492
- Nodes only in stage1/section-uuids: 15350
- Common relationships: 4778
- Relationships only in main: 2984
- Relationships only in stage1/section-uuids: 40757

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 259
- Commits unique to stage1/section-uuids: 1091
- Files changed from merge base on main: 154
- Files changed from merge base on stage1/section-uuids: 1690

See git-lineage.json for complete file inventories and the symmetric commit list.

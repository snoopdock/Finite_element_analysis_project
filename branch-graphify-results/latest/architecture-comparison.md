# Branch architecture comparison

- Base: main at 2a916109dd64a7761faeeeee5a5af28bb26becaa
- Compared branch: stage1/section-uuids at e9300e94818f1e4b2caa2c76f3945bc2c23f4d2b
- Merge base: 2713797451965a14b2512cdf497f2619d844749f

## Graphify code-structure counts

| Metric | Base branch | Comparison branch |
|---|---:|---:|
| Nodes | 5017 | 17837 |
| Edges | 7790 | 45597 |

## Identity-based graph delta

- Common nodes: 2438
- Nodes only in main: 2579
- Nodes only in stage1/section-uuids: 15399
- Common relationships: 4707
- Relationships only in main: 3083
- Relationships only in stage1/section-uuids: 40890

Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.

## Git divergence

- Commits unique to main: 280
- Commits unique to stage1/section-uuids: 1111
- Files changed from merge base on main: 155
- Files changed from merge base on stage1/section-uuids: 1697

See git-lineage.json for complete file inventories and the symmetric commit list.

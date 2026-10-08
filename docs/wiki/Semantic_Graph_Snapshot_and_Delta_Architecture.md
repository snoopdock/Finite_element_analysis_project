# Semantic Graph Snapshot and Delta Architecture

A semantic graph snapshot freezes four things together:

1. graph content;
2. semantic context;
3. graph fingerprint;
4. lineage metadata.

This is necessary because identical graph topology can mean different things under different vocabularies or projection contracts.

The delta layer distinguishes node addition/removal/modification, edge addition/removal, and semantic-context drift. Edge modifications are intentionally represented as removal plus addition because G2's canonical graph allows parallel edges but does not assign an independent occurrence identity to each edge.

This design makes graph regression reproducible without changing the G2 semantic core.

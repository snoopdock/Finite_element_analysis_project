# SciPy Sparse Projection Design Notes

## Purpose

This document explains how a future SciPy backend should interact with
the Universal Semantic Graph.

## Core Principle

The graph is semantic.

The matrix is computational.

They serve different purposes.

---

## Example

SemanticGraph:

```
Claim_A

SUPPORTED_BY

Paper_B
```

Possible numerical projection:

```
        Paper_B

Claim_A    1
```

The matrix preserves connectivity.

It does not automatically preserve:

- meaning of SUPPORTED_BY
- evidence confidence
- source location
- extractor identity

---

## Required Adapter Components

Future SciPyAdapter should provide:

```
export()

capabilities()

identity_mapping()

loss_report()
```

from the common adapter contract.

---

## Recommended Internal Artifacts

A future implementation should maintain:

```
semantic_to_index.json

index_to_semantic.json

relation_mapping.json

metadata_sidecar.json
```

---

## FEM / Scientific Compatibility

This design allows later numerical workflows:

SemanticGraph
        |
        v
Scientific relationship extraction
        |
        v
SciPy numerical representation

without forcing numerical libraries to understand semantic concepts.

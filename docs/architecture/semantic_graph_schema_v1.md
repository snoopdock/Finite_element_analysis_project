# Semantic Graph Schema v1

## Status

Draft for G1.5 architecture freeze

## Purpose

This document defines the stable semantic contract for the Semantic Graph Core.

The semantic graph is the source of truth for representing meaning inside the audit engine.

The graph is intentionally independent from:

- NetworkX
- igraph
- graph-tool
- RDF
- OWL
- formal verification systems

Those are future interpretation and computation layers.

The semantic graph stores:

- entities
- relationships
- attributes
- metadata


---

# 1. Core Model

The graph model is:

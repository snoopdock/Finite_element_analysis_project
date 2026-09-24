
# ADR — Renderer Boundary

## Status

Accepted

## Context

The repository needs deterministic scientific document generation.

## Decision

Keep renderer responsible only for representation transformation.

## Reasoning

Separating semantics from rendering improves maintainability and future backend support.

## Consequence

Renderer changes should not affect document meaning.

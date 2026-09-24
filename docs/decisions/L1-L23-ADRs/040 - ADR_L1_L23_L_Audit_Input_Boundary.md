
# ADR — Audit Input Boundary

## Status

Accepted

## Context

The audit engine is under development and should not affect LaTeX pipeline stability.

## Decision

Create a stable audit input contract after validation.

## Reasoning

This allows independent development of audit capabilities.

## Consequence

The audit engine becomes a consumer of evidence rather than a generation dependency.

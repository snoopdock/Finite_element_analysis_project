
# ADR — Test Coverage Strategy

## Status

Accepted

## Context

The repository contains significant functionality, but architectural guarantees need stronger verification.

## Decision

Prioritize boundary and contract tests.

## Reasoning

Boundary tests protect architecture better than tests tied to internal implementation details.

## Consequence

Future refactoring becomes safer because behavior is defined by contracts.

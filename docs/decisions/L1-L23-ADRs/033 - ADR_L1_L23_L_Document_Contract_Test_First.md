
# ADR — Document Contract Test First

## Status

Accepted

## Context

The repository contains multiple architectural boundaries.

## Decision

Start verification from the document boundary.

## Reasoning

Every downstream layer depends on document stability.

## Consequence

Later LaTeX and rendering tests can assume a reliable semantic input.


# ADR — Validation and Audit Boundary

## Status

Accepted

## Context

The audit engine is a work in progress and should not destabilize LaTeX generation.

## Decision

Keep audit consumption downstream of validation.

## Reasoning

This allows LaTeX architecture to mature independently.

## Consequence

Future audit features consume stable reports instead of coupling to generation code.

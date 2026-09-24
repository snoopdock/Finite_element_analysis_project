# ADR --- Document to LaTeX IR Boundary

## Status

Accepted

## Context

The repository already separates document structures and rendering
structures.

## Decision

Formalize the conversion boundary through tests and contracts.

## Reasoning

This preserves scientific meaning independently from rendering
technology.

## Consequence

Future renderers can consume the same semantic representation.

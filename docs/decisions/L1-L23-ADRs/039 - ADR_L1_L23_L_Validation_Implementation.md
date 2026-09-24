
# ADR — Validation Implementation

## Status

Accepted

## Context

The generation pipeline requires structured evidence before audit integration.

## Decision

Implement validation as an independent downstream layer.

## Reasoning

This keeps generation deterministic and allows audit capabilities to evolve separately.

## Consequence

Validation becomes the contract between generated artifacts and future audit systems.

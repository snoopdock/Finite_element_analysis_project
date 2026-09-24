
# ADR — Actual Test Mapping

## Status

Accepted

## Context

The architecture contains multiple transformations.

## Decision

Map tests to architectural responsibilities before adding new tests.

## Reasoning

This avoids random coverage growth and focuses effort on system guarantees.

## Consequence

New tests will be driven by missing contracts.

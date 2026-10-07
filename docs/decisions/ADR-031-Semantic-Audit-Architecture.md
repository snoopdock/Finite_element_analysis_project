# ADR-031 --- Semantic Audit Architecture

## Status

Accepted

## Context

Traditional validation detects syntax and execution problems but cannot
reliably detect semantic drift.

The repository requires auditing of:

-   LLM-generated code;
-   generated LaTeX;
-   evolving architectural artifacts.

## Decision

Semantic auditing SHALL operate using:

    Semantic Graph

    +

    Vocabulary

    +

    Contracts

    +

    Provenance

    +

    Rules

## Architecture

    Artifact

    ↓

    Extractor

    ↓

    Semantic Model

    ↓

    Rules

    ↓

    Audit Finding

## Audit Finding Contains

-   rule identifier;
-   affected objects;
-   severity;
-   explanation;
-   provenance chain.

## Scope

The semantic audit engine does not replace:

-   compilers;
-   tests;
-   linters.

It evaluates whether artifacts preserve intended meaning.

## Future Extensions

-   autonomous repair;
-   semantic diff;
-   reasoning explanations;
-   scientific claim validation.

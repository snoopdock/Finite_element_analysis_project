# ADR-056: Cumulative Budget Ledger Across Adaptive Rounds

## Status
Accepted

## Decision
The initial orchestration budget is the hard session-wide ceiling. Every continuation round derives its available cost and run budget by subtracting cumulative consumption; replanning cannot reset either budget.

## Consequences
A sequence of individually valid continuation plans cannot collectively exceed the original resource envelope. Cost remains an operational policy unit and does not represent confidence, correctness, or scientific importance.

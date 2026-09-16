# ADR-018: Backend Pipeline Orchestrator

## Status
Accepted for G2.5 Step 14

## Purpose
Coordinate backend selection, creation, execution context, and result handling.

## Architecture

Request
 |
 v
BackendPipeline
 |
 +--> Selection Policy
 +--> Backend Factory
 +--> Execution Context
 +--> Adapter
 +--> Execution Result

## Non-goals

The pipeline does not replace:
- capability registry
- selection policy
- factory
- backend implementations

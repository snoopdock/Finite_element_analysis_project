# ADR-020: Backend Provenance and Transformation Tracking

## Status

Accepted for G2.5 Step 16


## Context

The Semantic Graph backend architecture now provides:

- capability discovery
- backend selection
- backend factory
- execution context
- execution result contract
- pipeline orchestration

BackendExecutionResult currently contains:

- metadata
- provenance
- transformations
- loss report

These fields are currently simple containers.


## Decision

Introduce explicit provenance and transformation records.

New concepts:

- ProvenanceRecord
- TransformationRecord
- LossAssessment


Architecture:

```
Semantic Graph

      |

      v

Backend Pipeline

      |

      v

Transformation Record

      |

      v

Backend Execution Result

      |

      +--> Provenance
      +--> Transformations
      +--> Loss Assessment
```


## Benefits

- reproducible execution history
- explainable graph transformations
- audit trail support
- future LLM reasoning trace compatibility


## Non-goals

This step does not:

- implement semantic reasoning
- implement RDF provenance standards
- replace external provenance systems

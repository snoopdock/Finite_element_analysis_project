# AE-29 — Bounded Iterative Repository Audit and Controlled Self-Correction

**Validation profile:** G9.31  
**Status:** implementation milestone; acceptance requires GitHub targeted and full regression validation.

## Scope

AE-29 adds the first bounded repository-correction loop to the Audit Engine.
It is specifically concerned with:

- repository audit findings;
- AE-28 LLM/neural investigation handoff;
- repair proposals;
- isolated candidate repository states;
- independent repair verification;
- post-repair auditing;
- immutable decision records;
- deterministic decision-memory retrieval.

It does **not** move the project toward scientific writing or scientific
content generation.

## Control loop

```text
Audit repository
      │
      ▼
Open finding
      │
      ▼
AE-28 investigation handoff
      │
      ▼
Repair proposal
      │
      ▼
Isolated candidate state
      │
      ▼
Independent verification
      │
      ├── fail/inconclusive ──► reject/defer
      │
      ▼
Post-repair audit
      │
      ├── finding persists ──► reject
      │
      ▼
Accept candidate state
      │
      ▼
Record decision + lesson
      │
      ▼
Bounded next iteration
```

## Why the post-audit gate exists

A passing syntax/test check alone cannot establish that the original audit
finding was resolved. AE-29 therefore requires a new audit against the
candidate state before accepting the repair.

## Decision memory

Decision records provide a historical substrate for future planning. They are
explicitly non-authoritative. The current implementation does not let memory
authorize repairs or modify validation policy.

## Authoritative mutation

No ordinary AE-29 operation mutates the authoritative checkout. Accepted
states may be materialized into a new staging directory for an external Git
workflow to review.

## Next milestone

AE-30 independently evaluates whether the complete audit → investigate →
repair → verify → re-audit loop is reliable enough to support stronger
automation.

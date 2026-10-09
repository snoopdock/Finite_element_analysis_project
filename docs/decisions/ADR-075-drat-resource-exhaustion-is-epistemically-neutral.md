# ADR-075 — DRAT Resource Exhaustion Is Epistemically Neutral

## Status
Accepted — G3.4.4.

## Decision
The DRAT checker enforces explicit limits for steps, proof literals, clause width, active formula size, and RAT resolvents per step. Reaching a limit means only that the repository-owned checker did not accept the proof under the configured validation envelope.

It does not establish SAT, refute UNSAT, or create a finding. The external UNSAT observation may remain `OBSERVED/PARTIAL`, and an independent alternative validation path may still establish a verdict.

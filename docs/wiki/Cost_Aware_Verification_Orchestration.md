# Cost-Aware Verification Orchestration

## Principle

The repository separates three questions that are easy to conflate:

1. **Can this verifier test the obligation?** — semantic verifier capability.
2. **How expensive or operationally constrained is it?** — orchestration profile.
3. **What did this execution establish?** — immutable verification receipt.

These questions are deliberately represented by different objects.

## Verifier profiles

A profile records operational metadata without modifying verifier semantic identity:

```yaml
verifier_id: required-relationship
verifier_version: 1.0.0
method: graph_constraint
cost_units: 2
maximum_evidence_state: validated
execution_mode: in_process_read_only
deterministic: true
side_effect_free: true
```

## Budgets

A budget is a hard execution envelope:

```yaml
total_cost_units: 20
max_verifier_runs: 8
allowed_execution_modes:
  - in_process_read_only
```

External or sandboxed execution is not implicitly permitted.

## Planning

Planning is deterministic and versioned. The default strategy chooses the minimum-cost sufficient primary verifier while preserving requested-verifier restrictions and evidence requirements. Primary coverage is reserved before optional fallback work.

## Execution

The executor follows the plan exactly. It stops when a terminal receipt meets the requested evidence state. It records failures and budget consumption but does not create findings or persist memory.

## Interpretation boundary

Operational priority is queue order, not scientific importance. Cost is resource policy, not confidence. Maximum evidence state is capability, not a guaranteed outcome.

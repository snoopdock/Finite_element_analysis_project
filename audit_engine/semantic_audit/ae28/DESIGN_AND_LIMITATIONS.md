# AE-28 — Neural/LLM Semantic Interpretation

## Scope

AE-28 turns an externally produced LLM/neural interpretation into a
source-bound, replayable AE-27 proposal.

It is an **input boundary**, not an autonomous LLM service.

The intended future operating mode is:

```text
LLM output
    |
    v
provider-specific parser/adapter
    |
    v
AE-28 normalized response
    |
    v
AE-27 proposal gateway
    |
    v
AE-25 symbolic reasoning
```

## Why the model is not invoked here

Keeping invocation outside the semantic core provides:

1. deterministic CI using recorded model responses;
2. provider independence;
3. exact replay of the response bytes;
4. explicit separation between model execution and semantic admission;
5. no hidden network or credential dependency in validation.

This milestone therefore establishes the contract needed by a future runtime
adapter without prematurely choosing a provider or prompt.

## Repository-audit relevance

AE-28 is designed for repository auditing. A future adapter may provide
candidate relationships about:

- modules and symbols;
- imports and dependencies;
- configuration relationships;
- declared architectural constraints;
- test/implementation mismatches;
- potential repair targets.

The model's interpretation remains a candidate observation until AE-27,
AE-25, evidence, and the existing review/admission mechanisms establish a
stronger status.

## Recorded decision and improvement boundary

AE-28 records model provenance and task identity, but it does not learn,
rewrite its own rules, or update repository code. Those behaviors belong to
the controlled iterative layer planned for AE-29.

In particular, a model response cannot write to `decision_memory/` merely by
claiming that a decision should be remembered.

## Limitations

- A digest proves consistency with supplied bytes, not provider authenticity.
- A normalized response is not proof that the provider generated the claimed
  semantic interpretation unless the surrounding adapter establishes that
  provenance.
- Model confidence is not a truth probability in the audit engine.
- Natural-language equivalence is not inferred.
- Prompt quality is not evaluated by AE-28.
- Runtime provider authentication is not performed.
- No automatic source modification is performed.
- No candidate is promoted to authoritative graph state.

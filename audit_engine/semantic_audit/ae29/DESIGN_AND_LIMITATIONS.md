# AE-29 — Design and Limitations

## Design objective

AE-29 is the first bounded control-loop layer for an LLM-assisted repository
audit engine. It connects repository findings to an AE-28 interpretation,
repair candidate, independent verification, post-repair audit, and decision
memory.

It is intentionally **not** an autonomous coding agent.

## Safety boundary

The authoritative checkout is outside the AE-29 mutation domain.

The controller works with detached repository snapshots. A successful repair
produces a new in-memory candidate state. The state can be materialized only
as a new staging directory.

This means a defect in a model response, repair proposal, or controller cannot
silently rewrite the branch being audited.

## Guardrail protection

Repair proposals cannot modify:

- `.github/`;
- `validation/`;
- `validation-engine/`;
- `decision_memory/`.

This protects the mechanism that decides whether a repair is acceptable and
the history from which future planning may learn.

The project can later define a reviewed mechanism for changing these areas,
but it must not be an ordinary self-correction operation.

## Verification is external

AE-29 accepts a structured verification receipt. The verifier may eventually
be the central GitHub validation system, an isolated test runner, a static
analyzer, or another registered verifier.

AE-29 does not equate a string such as `"passed"` with truth. The receipt is
bound to exact before/after snapshot and repair digests, and the post-audit
gate is mandatory.

## No self-referential learning

Historical decision memory is non-authoritative. A previous successful repair
cannot authorize a new repair.

AE-29 exposes historical patterns only as deterministic planning hints. Any
future learning algorithm must remain separately evaluated.

## LLM scope

AE-29 does not define the final production prompt. It consumes an AE-28
verified handoff. The eventual prompt should be designed after AE-30
evaluation of:

- useful repository context;
- finding context;
- semantic context;
- previous decisions;
- expected structured output;
- abstention behavior;
- adversarial input handling.

## Known limitations

1. v1 does not execute a live LLM.
2. v1 does not automatically commit or push a repair.
3. v1 uses explicit file replacement/deletion rather than a patch-language
   interpreter.
4. The external verifier is not intrinsically trusted merely because its
   receipt is well-formed.
5. Decision memory retrieval is deterministic and intentionally simple.
6. Finding identity across large refactors depends on the finding's declared
   fingerprint policy.
7. Repository snapshots are bounded and therefore require the caller to
   choose the audited file set.

These limitations are deliberate gates for later AE-30 evaluation.

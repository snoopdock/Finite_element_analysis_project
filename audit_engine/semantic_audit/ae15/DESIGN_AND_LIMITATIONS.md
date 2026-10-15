# AE-15 / G9.17 — Source-Bound Bounded Python May-Flow

## Status and authority

AE-15 consumes **exact AE-01 source-inventory bytes** and the **AE-14 lexical model**. It produces *typed source observations*, never proof of execution, program correctness, root cause, rule conformance, or a G3 verification receipt. AE-01's verified architecture-rule engine and the canonical `SemanticGraph` remain unchanged. The new `audit_flow_repository` creates a separately identified source-replayable observation generation, whose `evidence_status` is always `unverified_observation`.

## Supported intraprocedural relationships

- Per lexical module, class and function definition occurrence: separate synthetic `entry` and `exit`, statement/test/iteration/join points, branch (`true`/`false`) and possible fallthrough, early return and raise escape, `break`/`continue` and conservative loop backedges.
- Loop CFG deliberately includes a possible zero-iteration or finished-loop edge, without claiming the loop termination condition is feasible for a particular input.
- Local `Name` loads/stores, parameter entry definitions, the distinction between an annotation-only declaration and assignment, pre-write reads of augmented assignments, deletion kills, and fixed-point **may-reaching-definitions** propagation.
- A separate *must-be-defined* name analysis over modeled paths to distinguish definitely bound names from `possibly_unbound` names. This is not proof that values have a particular runtime type, target or value.
- Nested functions and classes have distinct lexical occurrence keys; analyses never join their definitions into the caller scope. Imports, `global`, `nonlocal`, closures and unknown external bindings are not falsely inferred as locally reaching definitions.
- `ControlPoint`, `VariableUse`, and `Definition` entities plus source-bound `MAY_FLOW_TO`, `MAY_REACH`, `DEFINES_AT`, `USES_AT`, `HAS_FLOW_SCOPE` relations on the pre-existing universal `SemanticGraph`. No `EXECUTED_CALL`, `RESOLVED_CALLEE` or runtime `CALLS` edges are generated.

## Explicitly incomplete semantics

- `try`, `try*`, `finally`, `except`, `with`, `async with`, `match`, `await`, generator/yield, async iteration and coroutine scheduling are not fully modeled. Unsupported compound statements are represented by a visible opaque node plus a **partial** marker. Their bodies are not represented as verified ordinary paths.
- Executed calls can raise or change global/heap state; conditional expression evaluation, evaluation order, alias/points-to behavior, comprehensions/lambdas and dynamic dispatch are not modeled as feasible execution. The expression-level cases we know to be especially misleading (short-circuiting, assignment expressions, `exec`, `eval`, namespace reflection and star imports) make relevant scopes **partial**.
- A `MAY_FLOW_TO` relationship is a potential transition. A `MAY_REACH` relationship is syntactic/structural possibility within its stated subset. Neither relation should be interpreted as a guaranteed execution, valid call stack, semantic reachability under input constraints, or absence of unmodeled flows.
- A complete-looking bounded subset has `assurance=bounded_may_flow_only`. **This must never be interpreted as a clean or compliant program finding.** Any scope gaps yield `assurance=partial` globally.

## Source and publication integrity

- Inventory membership, Python encoding, exact SHA-256 hashes and safe relative paths are rechecked. Duplicate included paths, changed bytes, missing included files, unsafe source/output locations and budget exhaustion fail rather than returning a success result.
- Publications use AE-01's safe atomic file writes, lock-backed last-attempt marker and content-addressed generation naming. An independently replayed verifier compares exact sealed manifest, graph and semantic facts with the current source bytes. Publishing or verifying makes no authority claim beyond **source-replayed observations only**.
- The source tree is treated as untrusted data and is never imported or executed.
- Per-scope maximum points: 3,000; total maximum points: 30,000; fixed-point maximum iterations: 5,000, all configurable. Limits fail closed with `FlowLimitExceeded`; no partial over-budget graph is returned or published.
- AE-15 report files are distinct from AE-01's rule/finding output and cannot be passed to the AE-01 protected finding verifier as if they were G3 receipts.

## Verification and future work

- G9.17 tests independently check correct and incorrect control-flow cases, source change/tamper, identity, deterministic replay, no source execution, ZIP path/member admission and earlier AE-14/AE-13 protections.
- Higher-level exact exception flow, control dependence, interprocedural alias/effect summaries, runtime observations, and source-grounded causal experiments remain **future milestones** and must preserve this distinction between hypotheses and verified findings.

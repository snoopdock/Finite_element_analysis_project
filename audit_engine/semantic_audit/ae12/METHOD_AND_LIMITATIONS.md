# AE-12 — General Python failure-mode observation and source-bound runtime correlation

## Purpose and scientific claim

AE-12 is a **source-bound programming hazard auditor**, not an automatic proof of defect or a formal verifier of arbitrary program behavior. It retains AE-01 source identity and semantic dependency graph verification, uses the G3 graph-analysis engine to produce observed module relationships, and optionally replays AE-09 runtime-log correlation. A source pattern and a traceback mentioning the same module do **not** establish a root cause.

The development priority is code and programming failures. AE-10 scientific-claim checking and AE-11 FEM invariants remain separate opt-in features and are **not** dependencies of AE-12 or G9.13.

## Explicit bounded patterns (v1)

| Rule | Observed syntax | Reason for review, not definitive defect |
|---|---|---|
| `mutable_default` | list/dict/set literal or zero-argument constructor as a function default | mutable shared defaults can create cross-call state; constructors might be shadowed |
| `swallowed_exception` | a handler that consists only of `pass` (optional docstring ignored) | deliberate suppression may hide failures; intentional handling is possible |
| `bare_except` | `except:` | catches `BaseException` subclasses including interruption signals; sometimes deliberate |
| `finally_return` | direct `return` statement inside `finally` | overrides pending return or exception; dynamic reachability not established |
| `duplicate_dict_key` | two identical hashable literal keys within one dict | later literal overwrites prior literal under Python key equality; intentional overrides possible |
| `assert_call` | an assertion predicate containing a function call | optimized Python (`-O`) removes evaluation; may be harmless in tests |
| `subprocess_shell` | `subprocess.run/Popen/check_call/check_output(..., shell=True)` syntax | shell execution requires careful input handling; aliasing and taint not proven |

None of these automatically yields a verified policy violation, vulnerability, or scientific-content judgment. False negatives remain possible where equivalent behavior is expressed through different syntax, aliases, decorators, metaprogramming, or runtime monkeypatches.

## Verification protocol

1. Load a *sealed*, independently verified AE-01 generation. Reject changed source bytes or symlinked source paths.
2. Validate the exact byte identity of the explicit, versioned `ae12/policy/v1` configuration.
3. Scan every selected, included Python file using the encoding recorded in AE-01. Emit deterministic occurrence identities and source spans. Missing or omitted files produce an inconclusive result.
4. Use the existing G3 dependency analysis engine for each affected module within the declared query budget. Do not silently truncate results.
5. If supplied, replay AE-09's untrusted runtime correlation without saving raw logs or exception messages in the AE-12 report. Only co-observation is recorded.
6. Canonically hash the report; independently regenerate it from unchanged evidence before publishing or accepting it.
7. Publish a complete generation transactionally, with immutable historical files and a fail-closed `LATEST.json` pointer; reject corruption and interrupted success publication.

## Assurance states

- `bounded_observations`: selected files and selected patterns were examined without omitted mandatory scope. This is **not** a clean-code verdict.
- `inconclusive`: source or policy assurance incomplete, selected file missing, coverage budget reached, or optional runtime correlation insufficient.
- An execution failure raises an exception and publication records a failed latest attempt; past artifacts remain historical rather than current successful evidence.

## Independent oracles and limits

The G9.13 controlled corpus contains executable Python programs demonstrating shared mutable defaults, exception swallowing, `finally` override and literal duplicate keys. Expected behavior is checked with ordinary Python execution independent of AE-12's AST matching. Separate permitted controls and deliberate artifact tampering test specificity and fail-closed behavior. Fixture counts do not constitute empirical precision/recall for all Python programs; the required external broad validation corpus is a future improvement.

No arbitrary source code is executed by the audit engine itself. Optional subprocess execution is restricted to the test fixtures. AE-12 is not a security sandbox or static taint engine. Import dependencies are static possibilities, not execution observations. Reviewer authorization, runtime root-cause proof, type inference, dynamic dispatch, scientific content assessment and autonomous remediation are excluded.

# ADR-069 — External Solver Protocol Binding and Inactive-by-Default Registration

## Status
Accepted for G3.4.2.

## Decision
The external solver protocol is strict and identity-bound. A response must echo:

- protocol version;
- high-assurance request ID;
- normalized semantic input digest;
- registered solver ID;
- registered solver version;
- one of `sat`, `unsat`, or `unknown`.

Unknown response fields are rejected. The expected verification answer is not sent to the solver.

The `controlled-external-cnf` orchestration profile is policy metadata only. The adapter is not part of the default high-assurance adapter registry. To become executable it must be constructed with a trusted fixed-command runner, explicitly registered, explicitly activated, allowed by the high-assurance policy, allowed by orchestration containment policy, and given the required external-process risk acknowledgement.

## Consequences
Installation or profile presence is not activation. Solver process output is data, not execution authority or evidence-state authority. Existing `formal/sat`, `formal/smt`, `formal/cpsat`, `formal/lean`, and `formal/router.py` remain inactive.

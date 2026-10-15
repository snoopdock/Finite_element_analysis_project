# Audit Engine — Code-first development boundary (post-G9.12)

AE-01 source inventory and architecture policy → AE-02/02.1 evolution/reverification → AE-03 test-oracle analysis → AE-04–07 assurance/review lifecycle → AE-08 independent evaluation → AE-09 runtime failure correlation → **AE-12 general programming failure-mode auditing**.

**Code-first acceptance work remaining:**

1. Failure investigation: distinguish observed exception class and call stack from a causally established failing instruction; introduce controlled reproductions and historical incident links.
2. Runtime observation: apply span correlation to sanctioned runtime traces and successful-but-anomalous executions, with explicit privacy policies.
3. Implementation review: extend independent oracles and bounded rule semantics; add verified rule applicability, interprocedural candidates, alias treatment, and reviewed severity.
4. Test effectiveness: carry AE-03 mutation evidence into specific failure-mode findings with a documented mutation selection rationale.
5. Repository-wide auditing: independently label representative real-world code; measure precision, recall, inter-review agreement, false-clean results, and audit cost with denominators.

**Separation of concerns:** AE-10 scientific claim/data auditing and AE-11 FEM numerical checks are frozen opt-in domain capabilities for this development phase. They must not define the correctness or readiness of code-audit functionality, and G9.13 neither runs nor depends on those modules.

Exit criterion for code-first phase: an independently sampled/annotated code audit corpus and real failures reproduce high-value findings with source- and runtime-bound witnesses; negative controls, incompleteness, performance and cost are reported honestly. Passing the GitHub dispatcher alone is not sufficient proof of real-world fault detection.

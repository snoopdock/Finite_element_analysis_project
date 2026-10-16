# AE-25 — Semantic graph reasoning and constraints

Extends G7's philosophy of bounded, witness-carrying structural inference, using the canonical `SemanticGraph` with AE-24 source-bound contract admission and AE-13 graph integrity validation. **Does not change or relabel G7's existing scientific domain rules** or create another graph backend. Unlike G7's scientific-only predicates, these four new rules are language-neutral software architecture invariants. The verifier independently reconstructs the report from exact input contract and source evidence bytes.

## Rules

* R1: exactly specified artifact interface compatibility across producers and consumers (format, schema version, semantic meaning). Ambiguous producers or versioned producer occurrences, missing producers and unspecified interface properties are **incomplete**, not violations or verified clean.
* R2: one component has a declared `FORBIDS` relation and an observed `PERFORMS` occurrence for the same action. This is a witnessed **structural contradiction of supplied assertions**, not independently verified execution or causality.
* R3: a declared `REQUIRES_CHECK` exists, an *observed* `HAS_CHECK` does not, and a source-bound completeness claim explicitly says `HAS_CHECK` was fully enumerated. Without completeness, absence is unknown. Even declared completeness is not independently authenticated completeness.
* R4: a directed cycle exists in the admitted `DEPENDS_ON` subgraph, only when an explicitly source-bound `acyclic_dependencies` policy is supplied. Cycles with no such policy are not violations.

## Nonclaims

* Valid structural graph does not establish correct source extraction, behavioral runtime coverage or verified software compliance.
* No neural inference, OWL DL entailment, automatic remediation, or live LLM access.
* Graph impact is conservative potential dependency propagation, not proof of a runtime effect.
* Candidate neural relationships are quarantined and can only generate an incomplete/hypothesis signal.
* Issues are structural observations, NOT G3 independently verified findings. Explicit conversion through admitted G3 obligations and independent evidence is future work.
* The cycle function guarantees detection of encountered DFS backedges, not an exhaustive list of every simple cycle; its budget fails closed on overflow.

## Security and resource bounds

Exact evidence bytes; canonical deterministic source-bound reports; 2,000 entities, 12,000 edge occurrences, 2,000 source witnesses, 12MB contract and 2MB per source, 25,000 graph visits. The caller remains responsible for independent authentication and secure evidence acquisition. No source bytes are executed.

# AE-27 — Controlled neurosymbolic proposal gateway (v2)

## Purpose

AE-27 is the first explicit interface between a future neural/LLM component
and the symbolic Audit Engine. It is a **gateway**, not a live model runtime.

A model adapter submits candidate semantic relationships together with the
authoritative graph context it used. The gateway binds the proposal to the
exact AE-24 contract and the AE-26 semantic state, preserves many-to-many
evidence links, and asks AE-25 a counterfactual question about the candidate
set.

## State binding

Every proposal is bound to:

* the exact AE-24 contract digest;
* the exact admitted graph fingerprint;
* the AE-26 authoritative semantic fingerprint;
* the AE-26 hypothesis fingerprint;
* explicit context occurrence IDs;
* a model-adapter metadata record;
* a required context-binding digest.

The context-binding digest is derived from the graph fingerprint, authoritative
semantic fingerprint, and sorted context occurrence IDs.

Context occurrences must be `declared` or `observed`. Existing `candidate`
occurrences can remain visible in the base graph but cannot be claimed as
authoritative model context.

## Candidate boundary

Candidate assertions are validated through AE-24 in an isolated copy. They
remain `origin=candidate` and are never inserted into the authoritative graph.

The proposal digest identifies the exact proposal representation. It is not a
semantic-truth claim and does not convert model output into evidence.

## Evidence relations

Evidence links are bipartite and many-to-many:

`candidate occurrence --supports/contradicts--> evidence occurrence`

One evidence occurrence may participate in several candidate links, and review
events may cite evidence independently of model-selected links. Candidate
occurrences cannot be used as independent evidence.

## Joint symbolic probing

AE-27 evaluates the complete candidate set in one isolated counterfactual
copy. Every candidate is temporarily represented as an `observed` probe
occurrence only inside that copy.

This joint probe catches interactions that independent one-candidate probes
could miss, including collective conflicts such as a candidate prohibition
combined with a candidate observed action.

Per-candidate results are attributed only from AE-25 witnesses that contain
that candidate's probe occurrence. Existing unrelated conflicts/unknowns do
not contaminate a candidate result.

## Review/adjudication

Review events may cover multiple candidates. Review order is normalized for
the review-set digest, while the original review events remain the auditable
input.

A reviewed candidate with supporting evidence and no symbolic conflict can
receive `supported_candidate_requires_explicit_admission`. This is **not**
automatic graph promotion.

The gateway always reports:

* model output independently verified: false;
* runtime truth verified: false;
* automatic graph mutation permitted: false;
* candidate promoted to authoritative fact: false;
* reviewer independence established: false.

## Replay and CLI

Proposal validation, joint symbolic probing, adjudication, and exact
adjudication replay are available through the AE-27 CLI. Canonical JSON
objects and lists are accepted for their respective inputs.

`verify-adjudication` replays the complete contract, evidence, proposal, and
review set and rejects any altered result.

## Limitations

* No LLM is invoked by AE-27.
* Neural confidence is not treated as probability of truth.
* No external provider authentication is performed.
* Hashes establish consistency with supplied bytes, not external authenticity.
* Symbolic non-conflict is not proof of truth.
* Human review is not independent scientific ground truth.
* Reviewer IDs do not establish independence.
* Counterfactual probing is bounded by AE-25 resource limits.
* Natural-language equivalence and ontology entailment are not inferred.
* Authoritative admission remains a separate source/evidence-controlled step.

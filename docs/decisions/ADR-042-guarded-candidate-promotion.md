# ADR-042: Guarded Candidate-to-Canonical Promotion

## Status

Accepted for G3.1.1.

## Decision

Candidate semantic knowledge may enter a caller-supplied canonical graph only
through an explicit promotion policy and a confirmed verification receipt that
is bound to the candidate relation.

Promotion never creates endpoint identities and never treats an LLM/GNN
candidate as authoritative merely because it was proposed.

## Required checks

1. candidate remains in `PROPOSED` state;
2. receipt and obligation identities match;
3. verification decision is `CONFIRMED`;
4. evidence state meets the promotion policy;
5. verifier is allowed by policy when restricted;
6. obligation explicitly binds the candidate relation;
7. canonical endpoint nodes already exist;
8. duplicate canonical relationship insertion is prevented;
9. promoted edge records candidate, policy, receipt, verifier and evidence
   provenance.

## Consequence

Learned or heuristic systems may contribute candidate relations later without
being granted canonical semantic authority.

# AE-27 neurosymbolic protocol v2

## Intended future loop

```text
Natural-language / code / artifact adapter
                |
                v
       neural candidate proposal
                |
                v
     AE-27 context + state gate
                |
        +-------+-------+
        |               |
        v               v
 evidence links    AE-25 joint symbolic probe
        |               |
        +-------+-------+
                |
                v
        human / external review
                |
                v
     explicit admission request
                |
                v
 AE-24 authoritative source-bound graph
```

AE-27 implements the middle of this loop. It does not provide the neural model
itself and does not perform automatic promotion.

## Proposal state binding

A proposal records:

* the exact AE-24 contract digest;
* the exact SemanticGraph fingerprint;
* the AE-26 semantic fingerprint;
* the AE-26 hypothesis fingerprint;
* explicit context occurrence IDs;
* model-adapter metadata;
* a required digest of the authoritative context binding.

The context occurrence list is restricted to `declared` and `observed`
assertions. Candidate hypotheses are not admissible as authoritative model
context.

## Evidence relations

Evidence links are bipartite and many-to-many:

`candidate occurrence --supports/contradicts--> evidence occurrence`

The relation is explicit. It is not inferred from graph proximity, ordering,
or model confidence. Candidate evidence cannot serve as independent evidence.

## Joint symbolic probe

The complete candidate set is inserted into a private counterfactual copy with
temporary `observed` probe occurrence IDs. AE-25 then evaluates the combined
state.

This is important because two individually non-conflicting candidates can
jointly create a structural conflict. Candidate-level attribution is based on
the probe occurrences present in AE-25 witnesses.

## Authority

The neural model proposes. The symbolic engine tests consequences. Reviewers
adjudicate. The source/evidence admission layer authorizes authoritative graph
facts.

No layer is allowed to self-certify its own output.

## Replay

The proposal has an exact representation digest. Adjudication has an exact
source-replay verifier. The review-set digest is order-independent because
review events are an identified set for adjudication purposes.

No source program is executed and no authoritative graph mutation occurs.

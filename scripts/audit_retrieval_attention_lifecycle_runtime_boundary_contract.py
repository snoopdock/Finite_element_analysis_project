#!/usr/bin/env python3
"""Offline R7D.7 contract audit for lifecycle runtime authority boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_lifecycle_runtime_boundary_contract.yaml"
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _contains_all(values: list[Any], required: list[Any], label: str) -> None:
    for item in required:
        check(item in values, f"{label} is missing required value: {item!r}")


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "R7D.7 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_lifecycle_runtime_boundary_contract",
        "Unexpected R7D.7 contract name.",
    )

    dependencies = contract["dependencies"]
    check(
        dependencies["lifecycle_contract"]["name"]
        == "retrieval_attention_lifecycle_contract",
        "R7D.7 must depend on the R7D.1 lifecycle contract.",
    )
    check(
        dependencies["proposal_contract"]["name"]
        == "retrieval_attention_proposal_contract",
        "R7D.7 must depend on the proposal contract.",
    )

    artifacts = contract["core_separation"]["artifacts"]
    check("retrieval_event" in artifacts, "RetrievalEvent role is missing.")
    check("attention_proposal" in artifacts, "AttentionProposal role is missing.")
    check("lifecycle_event" in artifacts, "LifecycleEvent role is missing.")
    invariants = contract["core_separation"]["invariants"]
    _contains_all(
        invariants,
        [
            "RetrievalEvent is not a LifecycleEvent.",
            "AttentionProposal is not a LifecycleEvent.",
            "Creation of a RetrievalEvent does not itself create a LifecycleEvent.",
            "Creation of a RetrievalEvent does not itself imply any lifecycle transition.",
            "An AttentionProposal recommendation does not itself create a LifecycleEvent.",
            "Execution of a recommended acquisition action does not itself create a LifecycleEvent.",
        ],
        "core-separation invariant",
    )

    authority = contract["lifecycle_authority"]
    check(
        authority["owner"] == "lifecycle_management_layer",
        "Lifecycle authority owner must be lifecycle_management_layer.",
    )
    authority_rules = authority["authority_rules"]
    _contains_all(
        authority_rules,
        [
            "Only the lifecycle authority may cause a lifecycle transition to be recorded as a LifecycleEvent.",
            "The lifecycle authority must validate the requested from/to state against the R7D lifecycle contract before recording an event.",
            "The lifecycle authority must not reinterpret a retrieval fact as a lifecycle transition without an explicit lifecycle decision.",
            "No subsystem receives lifecycle authority merely by producing, consuming, or persisting a RetrievalEvent.",
        ],
        "authority rule",
    )

    initiation = contract["transition_initiation"]
    _contains_all(
        initiation["required_request_semantics"],
        ["attention_id", "previous_status", "new_status", "transition_reason", "actor_identity"],
        "transition request field",
    )
    _contains_all(
        initiation["request_rules"],
        [
            "The requested from/to pair must be an allowed R7D transition.",
            "The request must identify the attention proposal being transitioned.",
            "The request must state an operational or process-level reason.",
            "The request must identify the actor responsible for initiating or recording the lifecycle decision.",
            "A request that lacks lifecycle authority must not be converted into a LifecycleEvent.",
            "A rejected request must not mutate lifecycle history.",
        ],
        "transition request rule",
    )
    check(
        "Proposal creation alone does not require a lifecycle event unless the lifecycle authority elects to record one."
        in initiation["initial_open_rule"],
        "Initial-open semantics must keep proposal creation and lifecycle-event recording distinct.",
    )

    actor = contract["actor_identity"]
    _contains_all(
        actor["categories"],
        ["human", "system_component", "authorized_agent"],
        "actor category",
    )
    check(
        "This contract defines identity categories but does not by itself grant transition permission to any category."
        in actor["semantics"],
        "Actor categories must not implicitly grant permission.",
    )
    check(
        "must consult an explicit authorization policy rather than infer permission from actor category alone"
        in actor["authorization_boundary"],
        "Authorization must remain an explicit future policy boundary.",
    )

    transition_rules = contract["transition_specific_rules"]
    open_addressed = transition_rules["open_to_addressed"]
    _contains_all(
        open_addressed["requires"],
        [
            "explicit lifecycle transition request",
            "lifecycle authority processing",
            "operational or process-level transition_reason",
        ],
        "open-to-addressed precondition",
    )
    check(
        "A new RetrievalEvent may provide supporting operational evidence for the transition decision, but the RetrievalEvent itself never performs or implies open-to-addressed."
        == open_addressed["retrieval_event_rule"],
        "Open-to-addressed must not be implied by RetrievalEvent creation.",
    )
    _contains_all(
        transition_rules["open_to_closed"]["requires"],
        [
            "explicit lifecycle transition request",
            "lifecycle authority processing",
            "governing process policy determining that no further action is currently required",
        ],
        "open-to-closed precondition",
    )
    _contains_all(
        transition_rules["addressed_to_closed"]["requires"],
        [
            "explicit lifecycle transition request",
            "lifecycle authority processing",
            "governing process policy determining that the proposal no longer requires lifecycle tracking",
        ],
        "addressed-to-closed precondition",
    )

    retrieval = contract["retrieval_boundary"]["rules"]
    _contains_all(
        retrieval,
        [
            "Retrieval subsystem may create RetrievalEvents as acquisition facts.",
            "Retrieval subsystem must not create LifecycleEvents as a side effect of recording RetrievalEvents.",
            "Retrieval success does not imply addressed.",
            "Retrieval failure does not imply open, addressed, or closed.",
            "Repeated retrieval attempts do not automatically reopen, address, or close a proposal.",
            "A retrieval action may supply input to a later lifecycle decision without becoming the lifecycle decision itself.",
        ],
        "retrieval boundary rule",
    )

    attention = contract["attention_boundary"]["rules"]
    _contains_all(
        attention,
        [
            "R7B evaluation may create an AttentionProposal with lifecycle_status open according to the proposal contract.",
            "R7B evaluation must not autonomously advance lifecycle_status to addressed or closed.",
            "recommended_acquisition_action is advisory metadata and is not a lifecycle transition request.",
            "Attention evaluation must not execute the recommended action as a lifecycle side effect.",
        ],
        "attention boundary rule",
    )

    execution = contract["execution_boundary"]["rules"]
    _contains_all(
        execution,
        [
            "Executing an acquisition action and recording a lifecycle transition are separate operations.",
            "Successful execution of a recommended action does not automatically create an addressed LifecycleEvent.",
            "Runtime action completion may be submitted as input to a later explicit lifecycle decision.",
            "Lifecycle transition recording must not execute a new acquisition action implicitly.",
            "Persistence of a LifecycleEvent must not trigger acquisition, recommendation evaluation, or scientific inference.",
            "Replay of lifecycle history must remain historical reconstruction and must not emit new LifecycleEvents.",
        ],
        "execution boundary rule",
    )

    asynchronous = contract["asynchronous_semantics"]
    check(
        "Lifecycle transitions are recorded events and may occur asynchronously relative to retrieval acquisition and action execution."
        == asynchronous["rule"],
        "Asynchronous lifecycle semantics are missing or changed.",
    )
    _contains_all(
        asynchronous["requirements"],
        [
            "Acquisition and lifecycle decision processing may be temporally decoupled.",
            "Event ordering must use recorded lifecycle-event provenance and existing replay semantics rather than assuming runtime call order is the historical order.",
            "An asynchronous delay between acquisition and lifecycle recording does not by itself invalidate either event.",
            "Consumers must not infer a transition solely from temporal proximity between a RetrievalEvent and LifecycleEvent.",
        ],
        "asynchronous requirement",
    )

    lifetime = contract["proposal_lifetime"]
    check(
        "An attention proposal may remain open indefinitely unless a future explicit lifecycle policy introduces an expiration or other bounded-lifetime rule."
        == lifetime["rule"],
        "Proposal lifetime must permit indefinite open state.",
    )
    _contains_all(
        lifetime["requirements"],
        [
            "No timeout, expiry, or automatic close is introduced by R7D.7.",
            "Absence of new retrieval activity does not automatically close an open proposal.",
            "A future expiration policy, if introduced, must explicitly authorize its own lifecycle transition mechanism.",
        ],
        "proposal lifetime requirement",
    )

    reopening = contract["reopening_boundary"]
    _contains_all(
        reopening["requirements"],
        [
            "A later materially distinct operational condition must produce a new attention proposal with a new attention_id.",
            "A later RetrievalEvent must not reopen a closed proposal by side effect.",
            "A later recommended action must not reopen a closed proposal by side effect.",
        ],
        "reopening boundary requirement",
    )

    recording = contract["recording_authority"]["lifecycle_event_recording"]
    _contains_all(
        recording["required_preconditions"],
        [
            "lifecycle authority owns the transition decision",
            "requested transition is allowed by the lifecycle contract",
            "actor identity is recorded",
            "transition reason is recorded",
        ],
        "recording precondition",
    )
    check(
        "Invalid, unauthorized, ambiguous, or policy-incompatible transition requests must fail explicitly and must not overwrite, repair, synthesize, or reinterpret historical lifecycle events."
        == contract["recording_authority"]["failure_behavior"],
        "Recording failure behavior must preserve append-only history.",
    )

    scientific = contract["scientific_isolation"]["must_not_modify"]
    _contains_all(
        scientific,
        [
            "retrieval_history",
            "retrieval_report",
            "propositions",
            "evidence_relations",
            "epistemic_state",
            "evidence_strength",
            "truth_status",
            "ranking",
            "convergence",
            "writing_content",
        ],
        "scientific isolation field",
    )
    scientific_rules = contract["scientific_isolation"]["rules"]
    _contains_all(
        scientific_rules,
        [
            "Lifecycle runtime authority is process authority, not scientific authority.",
            "A lifecycle decision must not promote operational events into evidence relations.",
            "Lifecycle runtime handling must not modify scientific graph state or generated scientific text.",
        ],
        "scientific isolation rule",
    )

    scope = contract["scope"]
    check(
        "runtime lifecycle adapter implementation" in scope["excluded"],
        "R7D.7 must exclude runtime adapter implementation.",
    )
    check(
        "actor authorization policy implementation" in scope["excluded"],
        "R7D.7 must exclude actor authorization policy implementation.",
    )
    check(
        "automatic action execution" in scope["excluded"],
        "R7D.7 must exclude automatic action execution.",
    )

    print("R7D.7 retrieval attention lifecycle runtime boundary contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

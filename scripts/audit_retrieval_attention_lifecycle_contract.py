#!/usr/bin/env python3
"""Audit the R7D.1 retrieval-attention lifecycle contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_lifecycle_contract.yaml"
)

EXPECTED_STATES = {"open", "addressed", "closed"}
EXPECTED_ALLOWED_TRANSITIONS = {
    ("open", "addressed"),
    ("open", "closed"),
    ("addressed", "closed"),
}
EXPECTED_FORBIDDEN_TRANSITIONS = {
    ("closed", "open"),
    ("closed", "addressed"),
    ("addressed", "open"),
    ("open", "open"),
    ("addressed", "addressed"),
    ("closed", "closed"),
}
REQUIRED_EVENT_FIELDS = {
    "lifecycle_event_id",
    "attention_id",
    "previous_status",
    "new_status",
    "transition_reason",
    "created_at",
    "actor",
}
FORBIDDEN_SCIENTIFIC_FIELDS = {
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
}
FORBIDDEN_INTERPRETATIONS = {
    "scientific_absence",
    "evidence_quality",
    "truth_assessment",
    "epistemic_confidence",
    "scientific_relevance",
    "scientific_importance",
    "ranking_adjustment",
    "convergence_adjustment",
    "writer_instruction",
}
EXPECTED_PROHIBITED_DIRECT_TRANSITIONS = {
    "lifecycle_event_to_scientific_state",
    "lifecycle_event_to_retrieval_history_mutation",
    "lifecycle_event_to_automatic_action_execution",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _pairs(entries: list[dict]) -> set[tuple[str, str]]:
    return {(entry["from"], entry["to"]) for entry in entries}


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "R7D.1 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_lifecycle_contract",
        "Unexpected R7D.1 contract name.",
    )

    dependencies = contract["dependencies"]
    check(
        dependencies["proposal_contract"]["name"]
        == "retrieval_attention_proposal_contract",
        "R7D.1 must depend on the proposal contract.",
    )
    check(
        dependencies["proposal_contract"]["version"] == 1,
        "Unexpected proposal contract version.",
    )
    check(
        dependencies["provenance_contract"]["name"]
        == "retrieval_attention_provenance_contract",
        "R7D.1 must extend the existing provenance/lifecycle contract.",
    )
    check(
        dependencies["provenance_contract"]["version"] == 1,
        "Unexpected provenance contract version.",
    )
    composition_rule = str(dependencies["composition_rule"])
    check(
        "R7D extends the lifecycle boundary already established by R6.5B and R7B.5"
        in composition_rule,
        "R7D.1 must extend the existing lifecycle semantics rather than create a parallel model.",
    )
    check(
        "does not introduce a second proposal representation" in composition_rule,
        "R7D.1 must not introduce a duplicate proposal representation.",
    )

    lifecycle_model = contract["lifecycle_model"]
    proposal_role = str(lifecycle_model["proposal_role"]["meaning"])
    check(
        "canonical R7B process interpretation" in proposal_role,
        "AttentionProposal must remain the canonical R7B interpretation.",
    )
    check(
        "is not rewritten by later lifecycle activity" in proposal_role,
        "Lifecycle activity must not rewrite the original proposal.",
    )

    event_stream_role = str(lifecycle_model["event_stream_role"]["meaning"])
    check(
        "append-only lifecycle events" in event_stream_role,
        "Lifecycle changes must be represented as append-only events.",
    )
    check(
        "historical retrieval facts" in event_stream_role,
        "Lifecycle events must remain separate from historical retrieval facts.",
    )

    states = lifecycle_model["state_vocabulary"]
    check(set(states) == EXPECTED_STATES, "Lifecycle vocabulary must be open/addressed/closed.")
    check(
        "does_not_mean" in states["open"]
        and set(states["open"]["does_not_mean"]) >= {"scientific uncertainty", "evidence weakness"},
        "Open-state scientific interpretation boundary is incomplete.",
    )
    check(
        set(states["addressed"]["does_not_mean"])
        >= {"problem solved", "provider fixed", "scientific issue resolved"},
        "Addressed-state semantics are incomplete.",
    )
    check(
        set(states["closed"]["does_not_mean"])
        >= {
            "historical condition never existed",
            "provider permanently recovered",
            "scientific truth established",
            "scientific issue resolved",
        },
        "Closed-state semantics are incomplete.",
    )

    initialization = contract["initialization"]
    initialization_rule = str(initialization["rule"])
    check(
        "begins with lifecycle_status open" in initialization_rule,
        "New proposals must begin open.",
    )
    check(
        "previous_status is null and new_status is open" in initialization_rule,
        "Initial lifecycle creation semantics must allow null-to-open.",
    )
    initialization_requirements = "\n".join(str(item) for item in initialization["requirements"])
    check(
        "existing attention_id" in initialization_requirements,
        "Initial lifecycle creation must reference the existing attention_id.",
    )
    check(
        "must not alter retrieval-history events" in initialization_requirements,
        "Initial lifecycle creation must not mutate retrieval history.",
    )

    event_contract = contract["lifecycle_event"]
    check(
        set(event_contract["required_fields"]) == REQUIRED_EVENT_FIELDS,
        "Lifecycle event required fields are incomplete or unexpected.",
    )
    event_rules = "\n".join(str(rule) for rule in event_contract["rules"])
    check("process metadata only" in event_rules, "Lifecycle events must remain process metadata.")
    check("must not create a duplicate proposal representation" in event_rules,
          "Lifecycle events must not create duplicate proposal objects.")
    check("must not rewrite the original AttentionProposal interpretation" in event_rules,
          "Lifecycle events must not rewrite the original proposal interpretation.")
    check("append-only historical records" in event_rules,
          "Lifecycle events must remain append-only historical records.")
    check("does not redefine R7B deterministic proposal identity" in event_rules,
          "Lifecycle timestamps must remain outside deterministic proposal identity.")

    allowed = _pairs(contract["allowed_transitions"])
    forbidden = _pairs(contract["forbidden_transitions"])
    check(
        allowed == EXPECTED_ALLOWED_TRANSITIONS,
        "Allowed lifecycle transitions are incomplete or unexpected.",
    )
    check(
        forbidden == EXPECTED_FORBIDDEN_TRANSITIONS,
        "Forbidden lifecycle transitions are incomplete or unexpected.",
    )
    check(not (allowed & forbidden), "A lifecycle transition cannot be both allowed and forbidden.")

    forbidden_reasons = "\n".join(
        str(entry["reason"]) for entry in contract["forbidden_transitions"]
    )
    check(
        "new attention proposal" in forbidden_reasons,
        "Closed-state recurrence must be represented by a new attention proposal.",
    )
    check(
        "new acquisition response" in forbidden_reasons,
        "A closed proposal must not be reused for a new acquisition response.",
    )

    transition_rules = "\n".join(str(rule) for rule in contract["transition_rules"]["rules"])
    check(
        "must never rewrite, delete, replace, or reinterpret" in transition_rules,
        "Lifecycle transitions must preserve retrieval history.",
    )
    check(
        "Policy changes may affect future lifecycle decisions" in transition_rules,
        "Lifecycle history must be protected from retroactive policy rewriting.",
    )
    check(
        "process metadata" in transition_rules,
        "Lifecycle status must remain process metadata.",
    )

    provenance = contract["provenance"]
    check(
        provenance["required_trace"] == [
            "lifecycle_event_id",
            "attention_id",
            "previous_status",
            "new_status",
            "created_at",
            "actor",
        ],
        "Lifecycle provenance trace is incomplete or reordered.",
    )
    provenance_rules = "\n".join(str(rule) for rule in provenance["rules"])
    check(
        "without network retrieval or an LLM call" in provenance_rules,
        "Lifecycle provenance must be reproducible offline.",
    )
    check(
        "distinct from retrieval-event provenance" in provenance_rules,
        "Lifecycle provenance must remain distinct from retrieval provenance.",
    )

    isolation = contract["scientific_isolation"]
    protected = set(isolation["must_not_modify"])
    check(
        FORBIDDEN_SCIENTIFIC_FIELDS <= protected,
        "Scientific/process isolation boundary is incomplete.",
    )
    forbidden_interpretations = set(isolation["forbidden_interpretations"])
    check(
        FORBIDDEN_INTERPRETATIONS <= forbidden_interpretations,
        "Scientific interpretation boundary is incomplete.",
    )
    isolation_rules = "\n".join(str(rule) for rule in isolation["rules"])
    check(
        "must not be treated as evidence" in isolation_rules,
        "Lifecycle status must not become evidence.",
    )
    check(
        "must not change the scientific graph" in isolation_rules,
        "Lifecycle events must not change the scientific graph.",
    )

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited_direct_transitions"])
        == EXPECTED_PROHIBITED_DIRECT_TRANSITIONS,
        "Lifecycle execution boundary is incomplete or unexpected.",
    )
    action_boundary = str(execution["action_boundary"])
    check(
        "must produce new retrieval-history events" in action_boundary,
        "Later acquisition actions must return through new retrieval history.",
    )
    check(
        "modifying historical retrieval events" in action_boundary,
        "Lifecycle/action execution must not mutate historical retrieval events.",
    )

    reproducibility = contract["reproducibility"]
    reproducibility_rules = "\n".join(str(rule) for rule in reproducibility["rules"])
    check(
        "must not require mutable scientific state" in reproducibility_rules,
        "Lifecycle replay must not depend on mutable scientific state.",
    )
    check(
        "recorded lifecycle events rather than recomputing historical transitions" in reproducibility_rules,
        "Lifecycle replay must use recorded lifecycle events.",
    )
    check(
        "must not retroactively rewrite previously recorded lifecycle events" in reproducibility_rules,
        "Policy changes must not rewrite lifecycle history.",
    )

    scope = contract["scope"]
    check(
        {
            "lifecycle state vocabulary",
            "lifecycle event semantics",
            "initial open-state recording",
            "allowed transitions",
            "forbidden transitions",
            "lifecycle provenance",
            "scientific isolation",
            "action boundary",
        }
        <= set(scope["included"]),
        "R7D.1 included scope is incomplete.",
    )
    check(
        {
            "lifecycle event implementation",
            "lifecycle persistence implementation",
            "lifecycle replay implementation",
            "runtime integration",
            "automatic action execution",
            "evidence assessment",
            "epistemic inference",
            "ranking changes",
            "convergence changes",
            "writer decisions",
        }
        <= set(scope["excluded"]),
        "R7D.1 exclusions are incomplete.",
    )

    print("R7D.1 retrieval attention lifecycle contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

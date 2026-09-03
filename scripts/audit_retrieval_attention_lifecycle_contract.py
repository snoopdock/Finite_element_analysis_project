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
PROTECTED_STATE = {
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
        "R7D.1 must depend on the R7B.5 proposal contract.",
    )
    check(
        dependencies["proposal_contract"]["version"] == 1,
        "Unexpected proposal contract version.",
    )
    check(
        dependencies["provenance_contract"]["name"]
        == "retrieval_attention_provenance_contract",
        "R7D.1 must extend the existing R6.5B provenance contract.",
    )
    check(
        dependencies["provenance_contract"]["version"] == 1,
        "Unexpected provenance contract version.",
    )
    composition_rule = dependencies["composition_rule"]
    check(
        "extends the lifecycle boundary already established by R6.5B and R7B.5"
        in composition_rule,
        "R7D.1 must extend existing lifecycle semantics rather than create a parallel state model.",
    )

    model = contract["lifecycle_model"]
    states = model["state_vocabulary"]
    check(set(states) == EXPECTED_STATES, "Lifecycle vocabulary must be exactly open/addressed/closed.")

    open_meaning = states["open"]["meaning"]
    addressed_meaning = states["addressed"]["meaning"]
    closed_meaning = states["closed"]["meaning"]
    check("process tracking" in open_meaning, "Open state must represent process tracking.")
    check("retrieval/process response" in addressed_meaning, "Addressed state must represent a process response.")
    check("Lifecycle tracking" in closed_meaning, "Closed state must represent lifecycle tracking ending.")

    check(
        {
            "scientific uncertainty",
            "evidence weakness",
            "scientific importance",
        }
        <= set(states["open"]["does_not_mean"]),
        "Open state must remain separate from scientific interpretation.",
    )
    check(
        {
            "problem solved",
            "provider fixed",
            "scientific issue resolved",
            "evidence strengthened",
        }
        <= set(states["addressed"]["does_not_mean"]),
        "Addressed state must not imply resolution or evidence improvement.",
    )
    check(
        {
            "historical condition never existed",
            "provider permanently recovered",
            "scientific truth established",
            "scientific issue resolved",
        }
        <= set(states["closed"]["does_not_mean"]),
        "Closed state must not imply historical erasure or scientific resolution.",
    )

    initialization = contract["initialization"]
    check(
        "lifecycle_status open" in initialization["rule"],
        "New R7B proposals must initialize with open lifecycle status.",
    )
    requirements = set(initialization["requirements"])
    check(
        "The initial open state must reference the existing attention_id." in requirements,
        "Initial lifecycle state must reference the existing attention proposal.",
    )
    check(
        "Initial lifecycle creation must not alter the proposal's deterministic R7B core fields." in requirements,
        "Lifecycle creation must not modify the deterministic proposal core.",
    )
    check(
        "Initial lifecycle creation must not alter retrieval-history events." in requirements,
        "Lifecycle creation must preserve retrieval history.",
    )

    event = contract["lifecycle_event"]
    check(
        set(event["required_fields"]) == REQUIRED_EVENT_FIELDS,
        "Lifecycle event required fields are incomplete or unexpected.",
    )
    event_rules = "\n".join(str(rule) for rule in event["rules"])
    check("process metadata only" in event_rules, "Lifecycle events must remain process metadata.")
    check("append-only" in event_rules, "Lifecycle events must be append-only.")
    check("must not rewrite the original AttentionProposal interpretation" in event_rules,
          "Lifecycle events must not rewrite proposal interpretation.")

    allowed = _pairs(contract["allowed_transitions"])
    forbidden = _pairs(contract["forbidden_transitions"])
    check(allowed == EXPECTED_ALLOWED_TRANSITIONS, "Allowed lifecycle transitions are incomplete or unexpected.")
    check(forbidden == EXPECTED_FORBIDDEN_TRANSITIONS, "Forbidden lifecycle transitions are incomplete or unexpected.")
    check(not (allowed & forbidden), "A lifecycle transition cannot be both allowed and forbidden.")

    forbidden_reasons = "\n".join(
        str(entry["reason"]) for entry in contract["forbidden_transitions"]
    )
    check("new attention proposal" in forbidden_reasons,
          "Closed-state recurrence must be represented by a new attention proposal.")
    check("new acquisition response" in forbidden_reasons,
          "A closed proposal must not be reused for a new acquisition response.")

    transition_rules = "\n".join(str(rule) for rule in contract["transition_rules"]["rules"])
    check("must not rewrite, delete, replace, or reinterpret" in transition_rules,
          "Lifecycle transitions must preserve retrieval history.")
    check("Policy changes may affect future lifecycle decisions" in transition_rules,
          "Lifecycle history must be protected from retroactive policy rewriting.")
    check("process metadata" in transition_rules,
          "Lifecycle status must remain process metadata.")

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
    check("network retrieval" in provenance_rules, "Lifecycle provenance must be replayable offline.")
    check("LLM call" in provenance_rules, "Lifecycle provenance must not require an LLM call.")
    check("scientific support relation" in provenance_rules,
          "Lifecycle provenance must remain separate from scientific support relations.")

    isolation = contract["scientific_isolation"]
    check(
        PROTECTED_STATE <= set(isolation["must_not_modify"]),
        "Scientific/process isolation boundary is incomplete.",
    )
    check(
        FORBIDDEN_INTERPRETATIONS <= set(isolation["forbidden_interpretations"]),
        "Scientific interpretation boundary is incomplete.",
    )
    isolation_rules = "\n".join(str(rule) for rule in isolation["rules"])
    check("not a scientific state" in isolation_rules, "Lifecycle status must not become scientific state.")
    check("must not change the scientific graph" in isolation_rules,
          "Lifecycle events must not change the scientific graph.")

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited_direct_transitions"])
        == {
            "lifecycle_event_to_scientific_state",
            "lifecycle_event_to_retrieval_history_mutation",
            "lifecycle_event_to_automatic_action_execution",
        },
        "Lifecycle execution boundary is incomplete or unexpected.",
    )
    check(
        "new retrieval-history events" in execution["action_boundary"],
        "Later acquisition actions must create new retrieval-history events.",
    )

    reproducibility_rules = "\n".join(str(rule) for rule in contract["reproducibility"]["rules"])
    check("recorded lifecycle events" in reproducibility_rules,
          "Lifecycle replay must use recorded events rather than recomputing history.")
    check("must not retroactively rewrite" in reproducibility_rules,
          "Policy evolution must not rewrite historical lifecycle events.")

    scope = contract["scope"]
    included = set(scope["included"])
    excluded = set(scope["excluded"])
    check("lifecycle event semantics" in included, "Lifecycle event semantics must be in scope.")
    check("lifecycle persistence implementation" in excluded, "Persistence implementation must remain out of R7D.1.")
    check("runtime integration" in excluded, "Runtime integration must remain out of R7D.1.")
    check("automatic action execution" in excluded, "Automatic action execution must remain out of R7D.1.")
    check("evidence assessment" in excluded, "Scientific evidence assessment must remain out of R7D.1.")

    print("R7D.1 retrieval attention lifecycle contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

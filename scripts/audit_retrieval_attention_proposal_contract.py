#!/usr/bin/env python3
"""Audit the R7B.5 attention-proposal boundary contract and implementation shape."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from analysis.retrieval_attention_policy import evaluate_retrieval_attention


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_proposal_contract.yaml"
)

ALLOWED_CONDITIONS = {
    "provider_unavailable",
    "provider_partially_available",
    "query_returned_empty_result",
    "repeated_query_provider_non_success",
    "repeated_query_provider_empty_result",
}
ALLOWED_ACTIONS = {
    "retry_provider",
    "retry_query",
    "reformulate_query",
    "expand_query_scope",
    "use_alternate_provider",
    "defer_until_provider_recovery",
}
REQUIRED_FIELDS = {
    "attention_id",
    "policy_version",
    "query_scope",
    "provider",
    "attention_reason",
    "observed_condition",
    "lifecycle_status",
    "supporting_event_ids",
    "recommended_acquisition_action",
}
FORBIDDEN_SCIENTIFIC_FIELDS = {
    "confidence",
    "truth_status",
    "epistemic_status",
    "support_strength",
    "scientific_relevance",
    "scientific_importance",
    "evidence_strength",
    "ranking_score",
    "convergence_status",
    "writer_decision",
    "proposition",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _observation(event_id: str, cycle: int, status: str, records: int) -> dict:
    return {
        "event_id": event_id,
        "cycle": cycle,
        "retrieved_at": f"2026-09-03T00:{cycle:02d}:00+00:00",
        "provider_status": status,
        "attempts": 1,
        "returned_records": records,
        "acquisition_assessment": {
            "status": "not_defined_yet",
            "operational_status": status,
        },
    }


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "R7B.5 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_proposal_contract",
        "Unexpected R7B.5 contract name.",
    )

    dependency = contract["dependency"]
    check(
        dependency["attention_policy_contract"]["name"]
        == "retrieval_attention_policy_contract",
        "R7B.5 must depend on the R7B policy contract.",
    )
    check(
        dependency["attention_policy_contract"]["version"] == 1,
        "Unexpected R7B policy contract version.",
    )
    check(
        dependency["attention_provenance_contract"]["name"]
        == "retrieval_attention_provenance_contract",
        "R7B.5 must depend on the R6.5B provenance contract.",
    )
    check(
        "canonical attention-proposal representation"
        in dependency["composition_rule"],
        "R7B.5 must freeze the existing R7B representation rather than create a duplicate interpretation object.",
    )

    canonical = contract["canonical_representation"]
    check(
        set(canonical["required_fields"]) == REQUIRED_FIELDS,
        "Canonical proposal required fields are incomplete or unexpected.",
    )
    rules = "\n".join(str(rule) for rule in canonical["rules"])
    check(
        "R7B attention output is the canonical proposal" in rules,
        "R7B output must remain the canonical proposal representation.",
    )
    check(
        "lifecycle_status must be open" in rules,
        "New R7B proposals must start open.",
    )

    identity = contract["identity"]
    identity_rules = "\n".join(
        str(rule)
        for rule in identity["attention_id"]["rules"]
    )
    check(
        "must not depend on mutable scientific state" in identity_rules,
        "Attention identity must not depend on mutable scientific state.",
    )
    check(
        "must not depend on wall-clock time" in identity_rules,
        "Attention identity must remain deterministic.",
    )
    check(
        "same attention_id" in identity_rules,
        "Attention identity determinism rule is missing.",
    )

    observation_basis = contract["observation_basis"]
    check(
        observation_basis["required_trace"]
        == ["query_scope", "provider", "observed_condition", "supporting_event_ids"],
        "Proposal observation basis is incomplete or reordered.",
    )
    basis_rules = "\n".join(str(rule) for rule in observation_basis["rules"])
    check(
        "Supporting event IDs are the primary provenance link" in basis_rules,
        "Supporting event IDs must remain the primary provenance link.",
    )
    check(
        "does not create evidence relations" in basis_rules,
        "Proposal provenance must not create scientific evidence relations.",
    )

    lifecycle = contract["lifecycle_boundary"]
    check(
        set(lifecycle["statuses"]) == {"open", "addressed", "closed"},
        "R7B.5 lifecycle vocabulary must remain open/addressed/closed.",
    )
    check(
        lifecycle["generation_rule"]
        == "R7B creates proposals only with lifecycle_status open.",
        "R7B generation lifecycle rule is incorrect.",
    )
    check(
        lifecycle["transition_owner"]
        == "Future lifecycle-management logic, not the R7B evaluator.",
        "Lifecycle transition ownership must remain outside R7B.",
    )
    lifecycle_rules = "\n".join(str(rule) for rule in lifecycle["rules"])
    check("must not rewrite, delete, or replace" in lifecycle_rules, "Lifecycle must not mutate retrieval history.")
    check("Addressed does not assert" in lifecycle_rules, "Addressed must remain process metadata.")
    check("Closed does not assert" in lifecycle_rules, "Closed must not imply permanent/scientific resolution.")

    recommendation = contract["recommendation_boundary"]
    check(
        set(recommendation["allowed_actions"]) == ALLOWED_ACTIONS,
        "R7B.5 recommendation vocabulary must match R6.5/R7B.",
    )
    recommendation_rules = "\n".join(str(rule) for rule in recommendation["rules"])
    check("not an execution command" in recommendation_rules, "Recommendation must not be an execution command.")
    check("must not execute" in recommendation_rules, "R7B execution boundary is missing.")
    check("new retrieval-history events" in recommendation_rules, "Later execution must create new history events.")

    persistence = contract["persistence_boundary"]
    deterministic_fields = set(persistence["deterministic_core"]["fields"])
    check(
        deterministic_fields == REQUIRED_FIELDS,
        "Deterministic proposal core fields must match canonical fields.",
    )
    timestamp_rules = "\n".join(
        str(rule)
        for rule in persistence["deterministic_core"]["rules"]
    )
    check(
        "wall-clock timestamps" in timestamp_rules,
        "Deterministic core must explicitly exclude wall-clock timestamp dependence.",
    )
    envelope = persistence["persistence_envelope"]
    check(
        envelope["future_fields"] == ["generated_at"],
        "Persistence envelope must reserve generated_at without changing the deterministic core.",
    )

    isolation = contract["scientific_isolation"]
    protected = set(isolation["must_not_modify"])
    check(
        {
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
        <= protected,
        "Scientific/process isolation boundary is incomplete.",
    )
    forbidden_interpretations = set(isolation["forbidden_interpretations"])
    check(
        {
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
        <= forbidden_interpretations,
        "Scientific interpretation boundary is incomplete.",
    )

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited_direct_transitions"])
        == {
            "proposal_to_scientific_state",
            "proposal_to_historical_event_mutation",
            "proposal_to_automatic_action_execution",
        },
        "Proposal execution boundary is incomplete or unexpected.",
    )
    check(
        "new retrieval-history event" in execution["required_closed_loop"],
        "Closed-loop execution rule must return through new retrieval history.",
    )

    reproducibility = contract["reproducibility"]
    reproducibility_rules = "\n".join(str(rule) for rule in reproducibility["rules"])
    check(
        "same R7A context" in reproducibility_rules,
        "Reproducibility must be anchored to R7A context.",
    )
    check(
        "must not depend on wall-clock time" in reproducibility_rules,
        "R7B proposal generation must remain deterministic.",
    )
    check(
        "Persistence timestamps may differ" in "\n".join(
            str(rule)
            for rule in persistence["persistence_envelope"]["rules"]
        ),
        "Persistence timestamps must remain outside proposal identity/interpretation.",
    )

    # Validate the live R7B representation against the frozen canonical shape.
    policy = {
        "policy_version": "r7b5-test-v1",
        "history_window_events": 3,
        "repeated_non_success_threshold": 2,
        "repeated_empty_result_threshold": 2,
    }
    context = {
        "schema_version": 1,
        "event_count": 2,
        "query_provider_contexts": [
            {
                "query_scope": "weak form Galerkin FEM",
                "provider": "semantic_scholar",
                "observations": [
                    _observation("e1", 1, "invalid_response", 0),
                    _observation("e2", 2, "client_error", 0),
                ],
                "supporting_event_ids": ["e1", "e2"],
                "latest_observation": _observation("e2", 2, "client_error", 0),
            }
        ],
        "unscoped_provider_operations": [],
        "unscoped_events": [],
    }
    original = deepcopy(context)
    result = evaluate_retrieval_attention(context, policy)
    check(len(result["attention_items"]) == 1, "Expected one canonical R7B proposal.")
    proposal = result["attention_items"][0]
    check(set(proposal) == REQUIRED_FIELDS, "R7B output does not match canonical proposal fields.")
    check(proposal["observed_condition"] in ALLOWED_CONDITIONS, "Unexpected proposal trigger class.")
    check(proposal["recommended_acquisition_action"] in ALLOWED_ACTIONS, "Unexpected proposal recommendation.")
    check(proposal["lifecycle_status"] == "open", "R7B proposal must begin open.")
    check(proposal["supporting_event_ids"] == ["e1", "e2"], "Proposal provenance is not preserved.")
    check("generated_at" not in proposal, "Wall-clock persistence metadata must not enter the deterministic R7B core.")
    check(not (FORBIDDEN_SCIENTIFIC_FIELDS & set(proposal)), "Scientific fields leaked into proposal representation.")

    # Determinism and read-only behavior.
    assert evaluate_retrieval_attention(context, policy) == result
    assert context == original

    result["attention_items"][0]["supporting_event_ids"].clear()
    rebuilt = evaluate_retrieval_attention(context, policy)
    check(rebuilt["attention_items"][0]["supporting_event_ids"] == ["e1", "e2"], "R7B output is not defensive.")

    print("R7B.5 retrieval attention proposal boundary contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

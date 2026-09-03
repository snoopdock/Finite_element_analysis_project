#!/usr/bin/env python3
"""Audit the R7D.3 retrieval-attention lifecycle persistence contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_lifecycle_persistence_contract.yaml"
)

REQUIRED_EVENT_FIELDS = {
    "lifecycle_event_id",
    "attention_id",
    "previous_status",
    "new_status",
    "transition_reason",
    "created_at",
    "actor",
    "schema_version",
}
EXPECTED_EXECUTION_PROHIBITIONS = {
    "overwrite_existing_lifecycle_event",
    "delete_historical_lifecycle_event",
    "mutate_attention_proposal",
    "mutate_retrieval_history",
    "mutate_scientific_state",
    "execute_acquisition_action",
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


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "R7D.3 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_lifecycle_persistence_contract",
        "Unexpected R7D.3 contract name.",
    )

    dependencies = contract["dependencies"]
    check(
        dependencies["lifecycle_contract"]["name"]
        == "retrieval_attention_lifecycle_contract",
        "R7D.3 must depend on the lifecycle contract.",
    )
    check(
        dependencies["lifecycle_contract"]["version"] == 1,
        "Unexpected lifecycle contract version.",
    )
    check(
        dependencies["lifecycle_event_model"]["module"]
        == "analysis/retrieval_attention_lifecycle.py",
        "R7D.3 must depend on the R7D.2 lifecycle event model.",
    )

    storage = contract["storage_model"]
    check(
        storage["state_key"] == "retrieval_attention_lifecycle_history",
        "Unexpected lifecycle persistence state key.",
    )
    check(
        storage["structure"]["events"]["type"] == "append_only_event_list",
        "Lifecycle history must use an append-only event list.",
    )
    check(
        set(storage["structure"]["events"]["event_fields"]) == REQUIRED_EVENT_FIELDS,
        "Persisted lifecycle event fields are incomplete or unexpected.",
    )
    storage_rules = "\n".join(str(rule) for rule in storage["rules"])
    check(
        "rather than a mutable current-status field" in storage_rules,
        "Persistence must not collapse history into mutable current status.",
    )
    check(
        "complete event payload" in storage_rules,
        "Persisted events must retain sufficient reconstruction data.",
    )

    append_only = contract["append_only"]
    append_rules = "\n".join(str(rule) for rule in append_only["rules"])
    check("never be modified in place" in append_rules, "Existing lifecycle events must be immutable.")
    check("never be deleted" in append_rules, "Historical lifecycle events must not be deleted.")
    check("semantically reorder" in append_rules, "Persistence must preserve historical ordering semantics.")
    check("appended without changing prior event payloads" in append_rules, "New events must not alter prior events.")

    identity = contract["identity_integrity"]
    check(
        identity["identity_field"] == "lifecycle_event_id",
        "lifecycle_event_id must be the persistence identity key.",
    )
    identity_rules = "\n".join(str(rule) for rule in identity["rules"])
    check("identical canonical payload is an idempotent no-op" in identity_rules,
          "Identical duplicate lifecycle events must be idempotent.")
    check("different payload is an integrity failure" in identity_rules,
          "Conflicting duplicate lifecycle events must fail integrity validation.")
    check("must not overwrite the stored event" in identity_rules,
          "Conflicting duplicate events must not overwrite history.")
    check("leave the existing stored event unchanged" in identity_rules,
          "Integrity failure must preserve the original event.")
    check("event content" in identity_rules,
          "Duplicate handling must compare event content.")

    canonical = contract["canonical_payload"]
    check(
        set(canonical["required_fields"]) == REQUIRED_EVENT_FIELDS,
        "Canonical persisted event fields are incomplete or unexpected.",
    )
    canonical_rules = "\n".join(str(rule) for rule in canonical["rules"])
    check("No scientific fields are required or permitted" in canonical_rules,
          "Scientific fields must be excluded from lifecycle persistence payloads.")
    check("not converted into a mutable proposal-status record" in canonical_rules,
          "Lifecycle events must remain events rather than mutable proposal status.")

    separation = contract["proposal_separation"]
    separation_rules = "\n".join(str(rule) for rule in separation["rules"])
    check("through attention_id" in separation_rules,
          "Lifecycle persistence must reference proposals through attention_id.")
    check("must not embed a duplicate full AttentionProposal" in separation_rules,
          "Lifecycle persistence must not duplicate proposals.")
    check("must not modify the referenced AttentionProposal" in separation_rules,
          "Persistence must not mutate proposals.")
    check("remain separate concerns" in separation_rules,
          "Proposal and lifecycle persistence must remain separate.")

    ordering = contract["ordering"]
    ordering_rules = "\n".join(str(rule) for rule in ordering["rules"])
    check("Array position is storage order" in ordering_rules,
          "Array position must remain storage order rather than event identity.")
    check("created_at and lifecycle_event_id" in ordering_rules,
          "Recorded event metadata must support consumer ordering.")
    check("must not rewrite historical timestamps or identifiers" in ordering_rules,
          "Persistence must not manufacture ordering by rewriting history.")

    replay = contract["replayability"]
    replay_requirements = "\n".join(str(req) for req in replay["requirements"])
    check("sufficient event data" in replay_requirements,
          "Lifecycle history must support offline reconstruction.")
    check(
        "must not require network retrieval, an LLM call, or execution of the scientific pipeline"
        in replay_requirements,
        "Replay must remain offline and outside the scientific pipeline.",
    )
    check("must not recompute historical lifecycle transitions" in replay_requirements,
          "Replay must use recorded lifecycle events.")
    check("later policy changes" in replay_requirements,
          "Historical lifecycle events must survive policy evolution.")

    validation = contract["validation_and_integrity"]
    validation_rules = "\n".join(str(rule) for rule in validation["rules"])
    check("all required canonical fields" in validation_rules,
          "Persisted events require complete canonical fields.")
    check("null-to-open only for initial creation" in validation_rules,
          "Initial lifecycle transition semantics must be enforced.")
    check("process-level metadata" in validation_rules,
          "Transition reasons must remain process metadata.")
    check("silent overwrite" in validation_rules,
          "Silent overwrite must be forbidden.")
    check("silent loss" in validation_rules,
          "Silent historical loss must be forbidden.")

    isolation = contract["scientific_isolation"]
    protected = set(isolation["must_not_modify"])
    check(
        FORBIDDEN_SCIENTIFIC_FIELDS <= protected,
        "Scientific/process isolation boundary is incomplete.",
    )
    isolation_rules = "\n".join(str(rule) for rule in isolation["rules"])
    check("not scientific state" in isolation_rules,
          "Lifecycle persistence must remain process-history storage.")
    check("must not mutate historical RetrievalEvent records" in isolation_rules,
          "Persistence must not mutate historical RetrievalEvent records.")

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited_operations"]) == EXPECTED_EXECUTION_PROHIBITIONS,
        "Lifecycle persistence execution boundary is incomplete or unexpected.",
    )
    action_boundary = str(execution["action_boundary"])
    check("separate process" in action_boundary,
          "Acquisition action must remain outside persistence.")
    check("new RetrievalEvent records" in action_boundary,
          "Later actions must return through new retrieval events.")

    error_semantics = contract["error_semantics"]
    check(error_semantics["duplicate_identical"]["result"] == "no_op",
          "Identical duplicate result must be no_op.")
    check(error_semantics["duplicate_conflicting"]["result"] == "integrity_failure",
          "Conflicting duplicate result must be integrity_failure.")
    check(error_semantics["malformed_event"]["result"] == "validation_failure",
          "Malformed event result must be validation_failure.")
    check(error_semantics["persistence_failure"]["result"] == "explicit_failure",
          "Persistence failures must be explicit.")

    scope = contract["scope"]
    check(
        {
            "lifecycle history storage representation",
            "append-only semantics",
            "duplicate event identity integrity",
            "canonical persisted lifecycle event payload",
            "proposal separation",
            "ordering semantics",
            "offline replayability requirements",
            "persistence validation and error semantics",
            "scientific isolation",
            "action boundary",
        }
        <= set(scope["included"]),
        "R7D.3 included scope is incomplete.",
    )
    check(
        {
            "lifecycle event model implementation",
            "lifecycle persistence implementation",
            "lifecycle replay implementation",
            "runtime integration",
            "main.py changes",
            "automatic lifecycle transitions",
            "automatic action execution",
            "evidence assessment",
            "epistemic inference",
            "ranking changes",
            "convergence changes",
            "writer decisions",
        }
        <= set(scope["excluded"]),
        "R7D.3 exclusions are incomplete.",
    )

    print("R7D.3 retrieval attention lifecycle persistence contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
EXPECTED_PROHIBITED_OPERATIONS = {
    "overwrite_existing_lifecycle_event",
    "delete_historical_lifecycle_event",
    "mutate_attention_proposal",
    "mutate_retrieval_history",
    "mutate_scientific_state",
    "execute_acquisition_action",
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
    composition_rule = str(dependencies["composition_rule"])
    check(
        "persists lifecycle events defined by R7D.1/R7D.2" in composition_rule,
        "R7D.3 must persist the R7D lifecycle events rather than redefine them.",
    )
    check(
        "does not redefine lifecycle semantics" in composition_rule,
        "Persistence must not redefine lifecycle semantics.",
    )

    storage = contract["storage_model"]
    check(
        storage["state_key"] == "retrieval_attention_lifecycle_history",
        "Unexpected lifecycle persistence state key.",
    )
    check(
        storage["structure"]["events"]["type"] == "append_only_event_list",
        "Lifecycle history must be an append-only event list.",
    )
    check(
        set(storage["structure"]["events"]["event_fields"]) == REQUIRED_EVENT_FIELDS,
        "Persisted lifecycle event fields are incomplete or unexpected.",
    )
    storage_rules = "\n".join(str(rule) for rule in storage["rules"])
    check(
        "rather than a mutable current-status field" in storage_rules,
        "Storage must preserve events rather than replacing history with mutable status.",
    )
    check(
        "complete event payload" in storage_rules,
        "Persisted history must retain the payload needed for offline reconstruction.",
    )

    append_only = contract["append_only"]["rules"]
    append_rules = "\n".join(str(rule) for rule in append_only)
    check("must never be modified in place" in append_rules, "Existing lifecycle events must not be modified.")
    check("must never be deleted" in append_rules, "Existing lifecycle events must not be deleted.")
    check("semantically reorder" in append_rules, "Persistence must not rewrite historical ordering.")
    check("without changing prior event payloads" in append_rules, "New events must not mutate prior payloads.")

    identity = contract["identity_integrity"]
    check(identity["identity_field"] == "lifecycle_event_id", "Lifecycle event identity must use lifecycle_event_id.")
    identity_rules = "\n".join(str(rule) for rule in identity["rules"])
    check("immutable identity key" in identity_rules, "Lifecycle event identity must be immutable.")
    check("previously unseen lifecycle_event_id" in identity_rules, "New IDs must be appendable.")
    check("identical canonical payload is an idempotent no-op" in identity_rules,
          "Identical duplicate events must be idempotent.")
    check("any different payload is an integrity failure" in identity_rules,
          "Conflicting duplicate IDs must fail integrity validation.")
    check("must not overwrite the stored event" in identity_rules,
          "Conflicting duplicate IDs must not overwrite history.")
    check("existing stored event unchanged" in identity_rules,
          "Integrity failure must leave the original event unchanged.")

    canonical = contract["canonical_payload"]
    check(set(canonical["required_fields"]) == REQUIRED_EVENT_FIELDS,
          "Canonical lifecycle payload fields are incomplete or unexpected.")
    canonical_rules = "\n".join(str(rule) for rule in canonical["rules"])
    check("No scientific fields are required or permitted" in canonical_rules,
          "Lifecycle persistence must exclude scientific fields.")
    check("not converted into a mutable proposal-status record" in canonical_rules,
          "Lifecycle events must remain event objects.")

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
          "Ordering must not derive semantic identity from array position.")
    check("created_at and lifecycle_event_id" in ordering_rules,
          "Recorded event metadata must support consumer ordering.")
    check("must not rewrite historical timestamps or identifiers" in ordering_rules,
          "Persistence must not manufacture ordering by rewriting history.")

    replay = contract["replayability"]
    replay_requirements = "\n".join(str(req) for req in replay["requirements"])
    check("sufficient event data" in replay_requirements,
          "Lifecycle history must support offline reconstruction.")
    check(
        "without network retrieval, an LLM call, or execution of the scientific pipeline" in replay_requirements,
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
    check(FORBIDDEN_SCIENTIFIC_FIELDS <= protected,
          "Scientific/process isolation boundary is incomplete.")
    isolation_rules = "\n".join(str(rule) for rule in isolation["rules"])
    check("not scientific state" in isolation_rules,
          "Lifecycle persistence must remain process-history storage.")
    check("must not create evidence relations" in isolation_rules,
          "Persistence must not create evidence relations.")
    check("must not be interpreted as evidence quality" in isolation_rules,
          "Lifecycle status must not become scientific interpretation.")
    check("must not mutate historical RetrievalEvent records" in isolation_rules,
          "RetrievalEvent history must remain untouched.")

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited_operations"]) == EXPECTED_PROHIBITED_OPERATIONS,
        "Lifecycle persistence prohibited operations are incomplete or unexpected.",
    )
    action_boundary = str(execution["action_boundary"])
    check("records lifecycle facts only" in action_boundary,
          "Persistence must only record lifecycle facts.")
    check("must produce new RetrievalEvent records" in action_boundary,
          "Acquisition actions must return through new retrieval events.")

    errors = contract["error_semantics"]
    check(errors["duplicate_identical"]["result"] == "no_op",
          "Identical duplicate events must be a no-op.")
    check("remain unchanged" in errors["duplicate_identical"]["requirement"],
          "Identical duplicate no-op must preserve stored history.")
    check(errors["duplicate_conflicting"]["result"] == "integrity_failure",
          "Conflicting duplicate IDs must be integrity failures.")
    check("original event remain unchanged" in errors["duplicate_conflicting"]["requirement"],
          "Conflicting duplicates must preserve the original event.")
    check(errors["malformed_event"]["result"] == "validation_failure",
          "Malformed events must produce validation failures.")
    check(errors["persistence_failure"]["result"] == "explicit_failure",
          "Persistence failures must be explicit.")
    check("Partial silent mutation is forbidden" in errors["persistence_failure"]["requirement"],
          "Persistence failures must not silently partially mutate state.")

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

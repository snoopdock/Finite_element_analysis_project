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
REQUIRED_PROTECTED_FIELDS = {
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
EXPECTED_INCLUDED = {
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
EXPECTED_EXCLUDED = {
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
        "R7D.3 must identify the R7D.2 lifecycle event model.",
    )
    composition = str(dependencies["composition_rule"])
    check(
        "persists lifecycle events defined by R7D.1/R7D.2" in composition,
        "R7D.3 must persist the established lifecycle event model.",
    )
    check(
        "does not redefine lifecycle semantics" in composition,
        "Persistence must not redefine lifecycle semantics.",
    )

    storage = contract["storage_model"]
    check(
        storage["state_key"] == "retrieval_attention_lifecycle_history",
        "Unexpected lifecycle persistence state key.",
    )
    events = storage["structure"]["events"]
    check(
        events["type"] == "append_only_event_list",
        "Lifecycle history must use an append-only event list.",
    )
    check(
        set(events["event_fields"]) == REQUIRED_EVENT_FIELDS,
        "Persisted event fields are incomplete or unexpected.",
    )
    storage_rules = "\n".join(str(rule) for rule in storage["rules"])
    check(
        "contains lifecycle events rather than a mutable current-status field" in storage_rules,
        "Storage must preserve lifecycle history rather than only current status.",
    )
    check(
        "complete event payload" in storage_rules,
        "Storage must preserve a complete lifecycle event payload.",
    )

    append_only = contract["append_only"]
    append_rules = "\n".join(str(rule) for rule in append_only["rules"])
    check("must never be modified in place" in append_rules, "Existing lifecycle events must be immutable.")
    check("must never be deleted" in append_rules, "Lifecycle persistence must be append-only.")
    check("new lifecycle event is appended" in append_rules, "New lifecycle events must append without rewriting history.")

    identity = contract["identity_integrity"]
    check(identity["identity_field"] == "lifecycle_event_id", "Unexpected lifecycle event identity field.")
    identity_rules = "\n".join(str(rule) for rule in identity["rules"])
    check("previously unseen lifecycle_event_id" in identity_rules, "New event IDs must be appendable.")
    check("identical canonical payload" in identity_rules, "Identical duplicate semantics are missing.")
    check("idempotent no-op" in identity_rules, "Identical duplicate IDs must be idempotent no-ops.")
    check("different payload" in identity_rules, "Conflicting duplicate semantics are missing.")
    check("integrity failure" in identity_rules, "Conflicting duplicate IDs must fail integrity validation.")
    check("must not overwrite the stored event" in identity_rules, "Conflicting duplicate IDs must never overwrite history.")
    check("existing stored event unchanged" in identity_rules, "Integrity failures must preserve the original event.")

    canonical = contract["canonical_payload"]
    check(
        set(canonical["required_fields"]) == REQUIRED_EVENT_FIELDS,
        "Canonical persisted lifecycle event fields are incomplete or unexpected.",
    )
    canonical_rules = "\n".join(str(rule) for rule in canonical["rules"])
    check("No scientific fields" in canonical_rules, "Canonical lifecycle payload must exclude scientific fields.")
    check("mutable proposal-status record" in canonical_rules, "Lifecycle payload must remain an event object.")

    separation = contract["proposal_separation"]
    separation_rules = "\n".join(str(rule) for rule in separation["rules"])
    check("through attention_id" in separation_rules, "Lifecycle persistence must reference proposals through attention_id.")
    check("must not embed a duplicate full AttentionProposal" in separation_rules, "Lifecycle persistence must not duplicate proposals.")
    check("must not modify the referenced AttentionProposal" in separation_rules, "Persistence must not mutate proposals.")
    check("remain separate concerns" in separation_rules, "Proposal and lifecycle persistence must remain separate.")

    ordering = contract["ordering"]
    ordering_rules = "\n".join(str(rule) for rule in ordering["rules"])
    check("Array position is storage order" in ordering_rules, "Ordering must not derive semantic identity from array position.")
    check("created_at and lifecycle_event_id" in ordering_rules, "Recorded event metadata must support consumer ordering.")
    check("must not rewrite historical timestamps or identifiers" in ordering_rules, "Persistence must not manufacture ordering by rewriting history.")

    replay = contract["replayability"]
    replay_requirements = "\n".join(str(req) for req in replay["requirements"])
    check("sufficient event data" in replay_requirements, "Lifecycle history must support offline reconstruction.")
    check("without network retrieval, an LLM call" in replay_requirements, "Replay must remain offline.")
    check("must not recompute historical lifecycle transitions" in replay_requirements, "Replay must use recorded lifecycle events.")
    check("later policy changes" in replay_requirements, "Historical lifecycle events must survive policy evolution.")

    validation = contract["validation_and_integrity"]
    validation_rules = "\n".join(str(rule) for rule in validation["rules"])
    check("all required canonical fields" in validation_rules, "Persisted events require complete canonical fields.")
    check("null-to-open only for initial creation" in validation_rules, "Initial lifecycle transition semantics must be enforced.")
    check("process-level metadata" in validation_rules, "Transition reasons must remain process metadata.")
    check("silent overwrite" in validation_rules, "Silent overwrite must be forbidden.")
    check("silent loss" in validation_rules, "Silent historical loss must be forbidden.")

    isolation = contract["scientific_isolation"]
    check(
        REQUIRED_PROTECTED_FIELDS <= set(isolation["must_not_modify"]),
        "Scientific/process isolation boundary is incomplete.",
    )
    isolation_rules = "\n".join(str(rule) for rule in isolation["rules"])
    check("process-history storage" in isolation_rules, "Lifecycle persistence must remain process-history storage.")
    check("must not be interpreted as evidence quality" in isolation_rules, "Lifecycle status must not become scientific evidence metadata.")
    check("must not create evidence relations" in isolation_rules, "Persistence must not create evidence relations.")
    check("must not mutate historical RetrievalEvent records" in isolation_rules, "Persistence must not mutate retrieval events.")

    execution = contract["execution_boundary"]
    check(
        set(execution["prohibited_operations"]) == EXPECTED_PROHIBITED_OPERATIONS,
        "Lifecycle persistence prohibited operations are incomplete or unexpected.",
    )
    action_boundary = str(execution["action_boundary"])
    check("new RetrievalEvent records" in action_boundary, "Later acquisition actions must return through retrieval events.")

    errors = contract["error_semantics"]
    check(errors["duplicate_identical"]["result"] == "no_op", "Identical duplicates must be no-ops.")
    check("remain unchanged" in errors["duplicate_identical"]["requirement"], "Identical duplicate persistence must preserve history.")
    check(errors["duplicate_conflicting"]["result"] == "integrity_failure", "Conflicting duplicates must fail integrity.")
    check("original event remain unchanged" in errors["duplicate_conflicting"]["requirement"], "Conflicting duplicate persistence must preserve history.")
    check(errors["malformed_event"]["result"] == "validation_failure", "Malformed events must fail validation.")
    check(errors["persistence_failure"]["result"] == "explicit_failure", "Persistence failure semantics must be explicit.")

    scope = contract["scope"]
    check(EXPECTED_INCLUDED <= set(scope["included"]), "R7D.3 included scope is incomplete.")
    check(EXPECTED_EXCLUDED <= set(scope["excluded"]), "R7D.3 excluded scope is incomplete.")

    print("R7D.3 retrieval attention lifecycle persistence contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

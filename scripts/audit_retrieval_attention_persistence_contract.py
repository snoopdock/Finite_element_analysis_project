#!/usr/bin/env python3
"""Audit the R7C retrieval-attention proposal persistence contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_persistence_contract.yaml"
)

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
PROTECTED = {
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

    check(contract["version"] == 1, "R7C contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_persistence_contract",
        "Unexpected R7C contract name.",
    )

    dependency = contract["dependency"]
    check(
        dependency["proposal_contract"]["name"]
        == "retrieval_attention_proposal_contract",
        "R7C must depend on the R7B.5 proposal contract.",
    )
    check(
        dependency["proposal_contract"]["version"] == 1,
        "Unexpected R7B.5 proposal contract version.",
    )

    storage = contract["storage"]
    check(
        storage["state_field"] == "retrieval_attention_history",
        "Unexpected attention history state field.",
    )
    check(
        storage["events_field"] == "proposals",
        "Unexpected attention history proposals field.",
    )
    check(
        "append-only" in storage["append_only"]["rule"].casefold(),
        "Persistence must be append-only.",
    )

    canonical = contract["canonical_proposal"]
    check(
        set(canonical["required_fields"]) == REQUIRED_FIELDS,
        "Canonical persisted proposal fields are incomplete or unexpected.",
    )
    check(
        canonical["generation_rule"]
        == "R7B proposals must enter persistence with lifecycle_status open.",
        "Persistence must accept newly generated proposals as open.",
    )
    check(
        canonical["identity_rule"] == "attention_id is the stable idempotency key for persistence.",
        "Attention identity/idempotency rule is missing.",
    )

    envelope = contract["persistence_envelope"]
    check(envelope["fields"] == ["generated_at"], "Unexpected persistence-envelope fields.")
    envelope_rules = "\n".join(str(rule) for rule in envelope["rules"])
    check("storage metadata" in envelope_rules, "generated_at must remain storage metadata.")
    check("must not alter attention_id" in envelope_rules, "generated_at must not alter identity.")
    check("must not require generated_at" in envelope_rules, "Canonical reconstruction must not depend on timestamp metadata.")

    idempotency = contract["idempotency"]
    check(idempotency["key"] == "attention_id", "attention_id must be the persistence idempotency key.")
    idempotency_rules = "\n".join(str(rule) for rule in idempotency["rules"])
    check("no-op" in idempotency_rules, "Duplicate persistence must be a no-op.")
    check("must not create a second" in idempotency_rules, "Duplicate proposals must not be duplicated.")
    check("must not rewrite" in idempotency_rules, "Duplicate persistence must not rewrite existing history.")

    history_rules = "\n".join(str(rule) for rule in contract["immutability_and_history"]["rules"])
    check("append-only" in history_rules, "Attention history must remain append-only.")
    check("must not mutate or delete" in history_rules, "Older proposals must remain immutable.")
    check("supporting retrieval-history events" in history_rules, "Supporting retrieval history must remain immutable.")
    check("supporting_event_ids" in history_rules, "Proposal provenance must remain traceable.")

    lifecycle = contract["lifecycle_boundary"]
    check(lifecycle["initial_status"] == "open", "Persisted proposals must begin open.")
    lifecycle_rules = "\n".join(str(rule) for rule in lifecycle["rules"])
    check("does not perform lifecycle transitions" in lifecycle_rules, "R7C must not perform lifecycle transitions.")
    check("must not infer addressed or closed" in lifecycle_rules, "R7C must not invent lifecycle transitions.")

    isolation = contract["scientific_isolation"]
    check(set(isolation["must_not_modify"]) == PROTECTED, "Scientific/process isolation boundary is incomplete or unexpected.")
    isolation_rules = "\n".join(str(rule) for rule in isolation["rules"])
    check("not evidence storage" in isolation_rules, "Persistence must remain process-history storage.")
    check("must not create or modify scientific claims" in isolation_rules, "Persistence must remain scientifically isolated.")

    execution_rules = "\n".join(str(rule) for rule in contract["execution_boundary"]["rules"])
    check("does not execute" in execution_rules, "Persistence must not execute recommendations.")
    check("no network" in execution_rules, "R7C must not perform network/provider execution.")
    check("new retrieval-history events" in execution_rules, "Later execution must return through new history events.")

    behavior_rules = "\n".join(str(rule) for rule in contract["read_and_write_behavior"]["rules"])
    check("defensive copies" in behavior_rules, "Readers must use defensive copies.")
    check("deep-copy" in behavior_rules, "Writers must deep-copy stored proposals.")
    check("deterministic from attention_id" in behavior_rules, "Duplicate detection must be deterministic.")
    check("preserve the existing stored record" in behavior_rules, "Duplicate persistence must preserve the existing record.")

    excluded = set(contract["scope"]["excluded"])
    check("lifecycle transition implementation" in excluded, "Lifecycle implementation must remain outside R7C persistence.")
    check("action execution" in excluded, "Action execution must remain outside R7C persistence.")
    check("policy evaluation" in excluded, "Policy evaluation must remain outside R7C persistence.")
    check("evidence assessment" in excluded, "Evidence assessment must remain outside R7C persistence.")

    print("R7C retrieval attention persistence contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

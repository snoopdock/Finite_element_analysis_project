#!/usr/bin/env python3
"""Audit the R7C.9 retrieval-attention regression umbrella contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_regression_contract.yaml"
)

EXPECTED_AUDITS = [
    "python -m scripts.audit_retrieval_history_integration",
    "python -m scripts.audit_retrieval_attention_contract",
    "python -m scripts.audit_retrieval_attention_provenance_contract",
    "python -m scripts.audit_retrieval_attention_context_contract",
    "python -m scripts.audit_retrieval_attention_context",
    "python -m scripts.audit_retrieval_attention_policy_contract",
    "python -m scripts.audit_retrieval_attention_policy",
    "python -m scripts.audit_retrieval_attention_proposal_contract",
    "python -m scripts.audit_retrieval_attention_persistence_contract",
    "python -m scripts.audit_retrieval_attention_persistence",
    "python -m scripts.audit_retrieval_attention_replay",
    "python -m scripts.audit_retrieval_attention_pipeline_contract",
    "python -m scripts.audit_retrieval_attention_pipeline",
    "python -m scripts.audit_retrieval_attention_full_cycle_contract",
    "python -m scripts.audit_retrieval_attention_full_cycle",
    "python -m scripts.audit_retrieval_attention_runtime_contract",
    "python -m scripts.audit_retrieval_attention_runtime",
    "python -m scripts.audit_retrieval_attention_live_integration",
    "python -m scripts.audit_retrieval_attention_runtime_isolation_contract",
    "python -m scripts.audit_retrieval_attention_runtime_isolation",
]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "R7C.9 contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_regression_contract",
        "Unexpected R7C.9 contract name.",
    )

    objective = str(contract["objective"])
    check(
        "must not introduce new runtime behavior" in objective,
        "Umbrella must not introduce runtime behavior.",
    )

    purpose_rules = "\n".join(str(rule) for rule in contract["purpose"]["rules"])
    check("orchestration-only" in purpose_rules, "Regression umbrella must remain orchestration-only.")
    check("must not invoke network retrieval" in purpose_rules, "Network retrieval must remain excluded.")

    audits = contract["ordered_audits"]
    check(audits == EXPECTED_AUDITS, "Regression audit order is incomplete or unexpected.")
    check(len(audits) == len(set(audits)), "Regression audit list must not contain duplicates.")

    execution_rules = "\n".join(
        str(rule) for rule in contract["execution_rules"]["rules"]
    )
    check("dependency order" in execution_rules, "Dependency order must be explicit.")
    check("current Python interpreter" in execution_rules, "Audits must use the current Python interpreter.")
    check("Stop on the first failing audit" in execution_rules, "Fail-fast behavior is required.")
    check("stdout/stderr" in execution_rules, "Child audit diagnostics must be preserved.")

    isolation_rules = "\n".join(
        str(rule) for rule in contract["scientific_isolation"]["rules"]
    )
    check("must not import or modify scientific state" in isolation_rules, "Scientific-state isolation is missing.")
    check("must not write retrieval history" in isolation_rules, "Umbrella must not write runtime state.")
    check("only launches existing offline audits" in isolation_rules, "Umbrella scope must remain audit orchestration.")

    excluded = set(contract["scope"]["excluded"])
    check("lifecycle transitions" in excluded, "Lifecycle transitions must remain excluded.")
    check("action execution" in excluded, "Action execution must remain excluded.")
    check("scientific inference" in excluded, "Scientific inference must remain excluded.")

    print("R7C.9 retrieval attention regression contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

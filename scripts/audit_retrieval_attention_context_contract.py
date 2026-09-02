#!/usr/bin/env python3
"""Audit the R7A retrieval-attention context contract."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "specs"
    / "contracts"
    / "retrieval_attention_context_contract.yaml"
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    check(contract["version"] == 1, "Contract version must be 1.")
    check(
        contract["name"] == "retrieval_attention_context_contract",
        "Unexpected contract name.",
    )

    dependency = contract["dependency"]
    check(
        dependency["source_contract"]["name"] == "retrieval_history_contract",
        "R7A must consume retrieval history.",
    )
    check(
        dependency["attention_contract"]["name"] == "retrieval_attention_contract",
        "R7A must preserve the base attention semantics.",
    )
    check(
        dependency["provenance_contract"]["name"]
        == "retrieval_attention_provenance_contract",
        "R7A must remain compatible with attention provenance semantics.",
    )
    check(
        "does not create attention decisions or lifecycle states"
        in dependency["composition_rule"],
        "R7A must remain non-decisional.",
    )

    output = contract["output"]
    check(
        output["required_fields"]
        == [
            "schema_version",
            "event_count",
            "query_provider_contexts",
            "unscoped_provider_operations",
            "unscoped_events",
        ],
        "R7A context output fields are incomplete or reordered.",
    )
    check(output["schema_version"] == 1, "R7A context schema version must be 1.")

    context_fields = set(output["query_provider_context"]["required_fields"])
    check(
        {
            "query_scope",
            "provider",
            "observations",
            "supporting_event_ids",
            "latest_observation",
        }
        <= context_fields,
        "Query/provider context fields are incomplete.",
    )

    observation_fields = set(output["observation"]["required_fields"])
    check(
        {
            "event_id",
            "cycle",
            "retrieved_at",
            "provider_status",
            "attempts",
            "returned_records",
            "acquisition_assessment",
        }
        <= observation_fields,
        "Observation fields are incomplete.",
    )

    mapping_rules = contract["normalization_rules"]["query_provider_mapping"]
    mapping_text = "\n".join(str(rule) for rule in mapping_rules)
    check(
        "Only provider-level query lists establish" in mapping_text,
        "R7A must use provider-level query data for query/provider mapping.",
    )
    check(
        "must not be used to invent" in mapping_text,
        "R7A must prohibit fabricated query/provider associations.",
    )
    check(
        "unscoped_provider_operations" in mapping_text,
        "R7A must preserve unmappable provider operations.",
    )

    latest_rules = contract["latest_observation"]["rules"]
    latest_text = "\n".join(str(rule) for rule in latest_rules)
    check(
        "descriptive only" in latest_text,
        "Latest observation must remain descriptive.",
    )
    check(
        "must not be labeled open" in latest_text,
        "R7A must not assign lifecycle interpretation.",
    )

    forbidden = set(contract["read_only_boundary"]["forbidden"])
    check(
        {
            "create attention proposals",
            "assign attention lifecycle status",
            "select acquisition actions",
            "infer recovery or resolution",
            "score retrieval quality",
            "modify retrieval history",
            "modify propositions",
            "modify evidence relations",
            "modify epistemic state",
            "modify ranking",
            "modify convergence",
            "modify writing content",
            "perform network retrieval",
            "invoke an LLM",
        }
        <= forbidden,
        "R7A read-only boundary is incomplete.",
    )

    preservation = "\n".join(
        str(rule) for rule in contract["information_preservation"]["rules"]
    )
    check(
        "must not silently discard" in preservation,
        "R7A must preserve unmappable provider operations.",
    )
    check(
        "must not fabricate scientific meaning" in preservation,
        "R7A must not create scientific interpretation.",
    )
    check(
        "mutate the source retrieval history" in preservation,
        "R7A outputs must not alias mutable source history.",
    )

    excluded = set(contract["scope"]["excluded"])
    check("attention interpretation" in excluded, "R7A must exclude interpretation.")
    check("lifecycle assignment" in excluded, "R7A must exclude lifecycle assignment.")
    check("policy thresholds" in excluded, "R7A must exclude thresholds.")
    check("action execution" in excluded, "R7A must exclude execution.")

    print("R7A retrieval attention context contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""E.7.5 blinded paired-diagnosis review tests; offline and provider-free."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32c.blind_pair_review import (
    BlindReviewError,
    build_review_template,
    compare_reviews,
    prepare_blind_pair,
    prepare_from_files,
    unblind_pair,
    validate_isolated_pair,
    validate_review_record,
)
from audit_engine.semantic_audit.ae32c.tool_policy import GRAPH_DERIVED_TOOL_NAMES


def _report(*, graph_enabled: bool) -> dict:
    return {
        "status": "completed",
        "snapshot_check_status": "verified",
        "problem_statement": "Trace the repository entry point and its related implementation.",
        "graph_tools_enabled": graph_enabled,
        "provider": {"name": "openrouter", "model": "model-x"},
        "provenance": {
            "source_snapshot_status": "complete",
            "source_revision": "a" * 40,
            "source_manifest_sha256": "b" * 64,
            "graph_fingerprint": "graph:" + "c" * 24,
        },
        "diagnosis": {
            "summary": "A bounded diagnosis.",
            "root_cause": {
                "statement": "The consumer and provider expose different attribute names.",
                "confidence": "high",
                "evidence_refs": ["E0001"],
                "source_references": [{
                    "evidence_id": "E0001",
                    "path": "consumer.py",
                    "line": 10,
                    "source_sha256": "d" * 64,
                }],
            },
            "claims": [{
                "kind": "static_inference",
                "statement": "The call site reads provider.total_calls.",
                "confidence": "high",
                "evidence_refs": ["E0001", "E0002"],
                "source_references": [{
                    "evidence_id": "E0002",
                    "path": "provider.py",
                    "line": 20,
                    "source_sha256": "e" * 64,
                }],
            }],
            "proposed_corrective_action": "Align the interface contract.",
            "limitations": ["No runtime reproduction was performed."],
            "next_steps": ["Add a focused regression test."],
        },
        "evidence_ledger": [
            {"evidence_id": "E0001", "status": "ok", "tool": "read_source_file",
             "summary": "consumer.py", "response_sha256": "f" * 64},
            {"evidence_id": "E0002", "status": "ok", "tool": "graph_neighbors" if graph_enabled else "search_repository",
             "summary": "36 graph observations" if graph_enabled else "text search",
             "response_sha256": "1" * 64},
        ],
        "tool_calls": (
            [{"tool": "graph_neighbors", "evidence_id": "E0002"}]
            if graph_enabled else
            [{"tool": "search_repository", "evidence_id": "E0002"}]
        ),
        "graph_interaction_coverage": (
            {"status": "complete", "graph_follow_through_complete": True}
            if graph_enabled else
            {"status": "disabled", "graph_follow_through_complete": False}
        ),
    }


def _comparison(control_tools=None, treatment_tools=None) -> dict:
    graph_tools = sorted(GRAPH_DERIVED_TOOL_NAMES)
    control_tools = control_tools or ["read_source_file", "search_repository"]
    treatment_tools = treatment_tools or sorted(set(control_tools) | set(graph_tools))
    return {
        "schema_version": "ae32c/paired-graph-pilot/v2",
        "evaluation_id": "ae32c-graph-pilot-secret-id",
        "provider": "openrouter",
        "model": "model-x",
        "problem_statement": "Trace the repository entry point and its related implementation.",
        "acceptance": {
            "control_completed": True,
            "graph_enabled_completed": True,
            "graph_interaction_complete": True,
            "graph_tool_difference_isolated": True,
            "graph_derived_tool_difference_isolated": True,
            "source_only_control_enforced": True,
            "source_snapshot_stable": True,
        },
        "design": {
            "non_graph_tool_sets_match": True,
            "graph_tool_difference_isolated": True,
            "graph_derived_tool_difference_isolated": True,
            "source_only_control_enforced": True,
            "same_provider_and_model": True,
            "same_problem_statement": True,
            "same_source_snapshot": True,
            "same_graph_fingerprint": True,
            "same_limits": True,
            "both_conditions_snapshot_verified": True,
            "control_available_tools": list(control_tools),
            "graph_enabled_available_tools": list(treatment_tools),
        },
        "conditions": {
            "control": {
                "status": "completed",
                "available_tool_names": list(control_tools),
                "graph_tools_enabled": False,
            },
            "graph_enabled": {
                "status": "completed",
                "available_tool_names": list(treatment_tools),
                "graph_tools_enabled": True,
            },
        },
        "source": {
            "source_revision": "a" * 40,
            "source_manifest_sha256": "b" * 64,
            "graph_fingerprint": "graph:" + "c" * 24,
        },
    }


def _pair():
    comparison = _comparison()
    control = _report(graph_enabled=False)
    graph = _report(graph_enabled=True)
    packet, key = prepare_blind_pair(
        comparison, control, graph, pair_id="blind-pair-0123456789abcdef", alias_choice="control_A"
    )
    return comparison, control, graph, packet, key


def test_prepare_packet_strips_condition_provider_tool_names_and_confidence():
    comparison, control, graph, _, _ = _pair()
    control["diagnosis"]["summary"] = "OpenRouter model-x reports a bounded diagnosis."
    graph["diagnosis"]["summary"] = "OpenRouter model-x reports a bounded diagnosis."
    packet, key = prepare_blind_pair(
        comparison, control, graph, pair_id="blind-pair-0123456789abcdef", alias_choice="control_A"
    )
    serialized = json.dumps(packet).lower()
    assert "openrouter" not in serialized
    assert "model-x" not in serialized
    assert "control" not in serialized
    assert "graph_enabled" not in serialized
    assert "graph_neighbors" not in serialized
    assert '"confidence":' not in serialized
    assert "36 graph observations" not in serialized
    assert "[provider/model redacted]" in serialized
    assert packet["cases"]["A"]["diagnosis"]["root_cause"]["statement"]
    assert packet["cases"]["A"]["evidence_index"][0]["evidence_id"] == "E0001"
    assert key["aliases"]["A"]["condition"] == "control"
    assert key["aliases"]["B"]["condition"] == "graph_enabled"


def test_isolation_gate_rejects_control_graph_derived_tool_catalog():
    leaked = ["read_source_file", "search_repository", "trace_execution_context"]
    comparison = _comparison(control_tools=leaked, treatment_tools=sorted(set(leaked) | set(GRAPH_DERIVED_TOOL_NAMES)))
    with pytest.raises(BlindReviewError, match="control_graph_tool_exposure"):
        validate_isolated_pair(comparison, _report(graph_enabled=False), _report(graph_enabled=True))


def test_isolation_gate_rejects_control_graph_derived_call_even_if_catalog_claims_clean():
    comparison = _comparison()
    control = _report(graph_enabled=False)
    control["tool_calls"].append({"tool": "find_related_tests", "evidence_id": "E0003"})
    with pytest.raises(BlindReviewError, match="control_graph_tool_calls"):
        validate_isolated_pair(comparison, control, _report(graph_enabled=True))


def test_isolation_gate_rejects_non_graph_tool_mismatch():
    comparison = _comparison(
        control_tools=["read_source_file", "search_repository"],
        treatment_tools=["read_source_file", "search_symbols", *sorted(GRAPH_DERIVED_TOOL_NAMES)],
    )
    with pytest.raises(BlindReviewError, match="non_graph_tool_sets_do_not_match"):
        validate_isolated_pair(comparison, _report(graph_enabled=False), _report(graph_enabled=True))


def test_isolation_gate_rejects_source_snapshot_mismatch():
    comparison = _comparison()
    graph = _report(graph_enabled=True)
    graph["provenance"]["source_manifest_sha256"] = "9" * 64
    with pytest.raises(BlindReviewError, match="report_source_identity_mismatch"):
        validate_isolated_pair(comparison, _report(graph_enabled=False), graph)


def _complete_review(packet, reviewer_id, claim_outcome="partially_supported"):
    review = build_review_template(packet, reviewer_id)
    review["reviewed_at"] = "2026-11-19T09:00:00+03:30"
    for case in review["cases"]:
        case["overall_outcome"] = "correct_detection"
        case["localization"] = "partial"
        case["causal_explanation"] = "partially_supported"
        case["claim_level_support"] = "indirectly_supported"
        case["evidence_integrity"] = "valid"
        case["uncertainty"] = "appropriate"
        case["actionability"] = "actionable"
        case["rationale"] = "The source references support the interface mismatch, but no runtime reproduction is available."
        for claim in case["claim_reviews"]:
            claim["outcome"] = claim_outcome
            if claim_outcome == "entailed":
                claim["verification_level"] = "test_reproduction"
            claim["rationale"] = "The cited source line supports part, but not all, of the proposition."
    review["pair_preference"] = "tie"
    review["pair_rationale"] = "Both anonymized diagnoses have comparable support and limitations."
    review["blindness_attestation"] = {
        "has_not_seen_other_reviewer_labels": True,
        "has_not_seen_provider_or_model_identity": True,
        "has_not_seen_condition_mapping": True,
    }
    return review


def test_review_validation_requires_complete_claims_and_true_blinding():
    _, _, _, packet, _ = _pair()
    review = _complete_review(packet, "reviewer-one")
    assert validate_review_record(review, packet)["valid"] is True
    review["blindness_attestation"]["has_not_seen_condition_mapping"] = False
    result = validate_review_record(review, packet)
    assert result["valid"] is False
    assert "blindness_attestation_not_true:has_not_seen_condition_mapping" in result["errors"]


def test_contradicted_claim_requires_ledger_bound_counterevidence():
    _, _, _, packet, _ = _pair()
    review = _complete_review(packet, "reviewer-one", claim_outcome="contradicted")
    result = validate_review_record(review, packet)
    assert result["valid"] is False
    assert any("contradicted_requires_counterevidence" in item for item in result["errors"])


def test_agreement_is_descriptive_and_never_auto_creates_gold_label():
    _, _, _, packet, key = _pair()
    first = _complete_review(packet, "reviewer-one")
    second = _complete_review(packet, "reviewer-two", claim_outcome="entailed")
    agreement = compare_reviews(packet, first, second)
    assert agreement["valid"] is True
    assert agreement["claim_level_agreement"]["count"] == 4
    assert agreement["claim_level_agreement"]["observed_agreement"] == 0.0
    assert agreement["final_adjudication"] == "pending_human_adjudicator"
    assert agreement["primary_benchmark_eligible"] is False
    unblinded = unblind_pair(key, agreement)
    assert unblinded["aliases"]["A"]["condition"] == "control"
    assert unblinded["final_adjudication"] == "pending_human_adjudicator"


def test_reviewer_ids_must_be_distinct():
    _, _, _, packet, _ = _pair()
    first = _complete_review(packet, "same-reviewer")
    second = _complete_review(packet, "same-reviewer")
    with pytest.raises(BlindReviewError, match="reviewer_ids_must_differ"):
        compare_reviews(packet, first, second)


def test_prior_pilot_artifact_is_rejected_due_to_control_leakage():
    # This models the previously reviewed pilot, where the control catalog still
    # included trace_execution_context/find_related_tests/find_workflow_context.
    leaked = ["discover_case_context", "read_source_file", "repository_summary",
              "search_decision_history", "search_repository", "search_symbols",
              "trace_execution_context", "find_related_tests", "find_workflow_context"]
    treatment = sorted(set(leaked) | {"graph_neighbors", "graph_path"})
    comparison = _comparison(control_tools=leaked, treatment_tools=treatment)
    with pytest.raises(BlindReviewError, match="control_graph_tool_exposure"):
        prepare_blind_pair(comparison, _report(graph_enabled=False), _report(graph_enabled=True))


def test_prepare_from_files_separates_reviewer_packets_from_steward_key(tmp_path):
    comparison, control, graph, _, _ = _pair()
    comparison_path = tmp_path / "comparison.json"
    control_path = tmp_path / "control.json"
    graph_path = tmp_path / "graph.json"
    comparison_path.write_text(json.dumps(comparison), encoding="utf-8")
    control_path.write_text(json.dumps(control), encoding="utf-8")
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    output = tmp_path / "blind-review"

    result = prepare_from_files(
        comparison_path, control_path, graph_path, output, pair_id="blind-pair-fedcba9876543210"
    )
    assert result["pair_id"] == "blind-pair-fedcba9876543210"
    reviewer_one = json.loads((output / "reviewer-1" / "packet.json").read_text(encoding="utf-8"))
    reviewer_two = json.loads((output / "reviewer-2" / "packet.json").read_text(encoding="utf-8"))
    assert reviewer_one == reviewer_two
    assert not (output / "reviewer-1" / "unblinding-key.json").exists()
    assert (output / "steward" / "unblinding-key.json").is_file()
    assert (output / "steward" / "input-manifest.json").is_file()
    assert (output / "steward" / "README.md").is_file()


def test_packet_pair_id_must_not_reuse_source_evaluation_id():
    comparison, control, graph, _, _ = _pair()
    with pytest.raises(BlindReviewError, match="pair_id_must_be_anonymized"):
        prepare_blind_pair(
            comparison, control, graph,
            pair_id="ae32c-graph-pilot-fe977815527944ec817e05f54ba0ab1e",
        )


def test_schema_and_profile_include_the_blind_review_contract():
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "evaluation/ae32c/blind_pair_review.schema.json").read_text(encoding="utf-8"))
    profile = (root / "validation/profiles/G9.42.yaml").read_text(encoding="utf-8")
    assert schema["properties"]["schema_version"]["const"] == "ae32c/blind-pair-review/v1"
    assert "blindness_attestation" in schema["required"]
    assert "tests/semantic_audit/test_ae32c_blind_pair_review.py" in profile


def test_review_validator_rejects_provider_or_condition_fields():
    _, _, _, packet, _ = _pair()
    review = _complete_review(packet, "reviewer-one")
    review["provider"] = "openrouter"
    result = validate_review_record(review, packet)
    assert result["valid"] is False
    assert "unexpected_review_fields" in result["errors"]


def test_pair_gate_requires_report_provider_and_model_to_match():
    comparison, control, graph, _, _ = _pair()
    graph["provider"]["model"] = "different-model"
    with pytest.raises(BlindReviewError, match="graph_enabled_model_mismatch"):
        validate_isolated_pair(comparison, control, graph)


def test_causal_claim_cannot_be_entailed_from_static_review_only():
    _, _, _, packet, _ = _pair()
    review = _complete_review(packet, "reviewer-one")
    root_claim_id = next(
        claim["claim_id"]
        for claim in packet["cases"]["A"]["claim_index"]
        if claim["role"] == "root_cause"
    )
    root_review = next(
        item for item in review["cases"][0]["claim_reviews"]
        if item["claim_id"] == root_claim_id
    )
    root_review["outcome"] = "entailed"
    root_review["verification_level"] = "static_review"
    result = validate_review_record(review, packet)
    assert result["valid"] is False
    assert any("causal_or_runtime_entailment_requires_reproduction_or_expert_review" in item for item in result["errors"])
    root_review["verification_level"] = "test_reproduction"
    assert validate_review_record(review, packet)["valid"] is True


def test_unblinding_rejects_an_invalid_or_unvalidated_agreement():
    _, _, _, packet, key = _pair()
    with pytest.raises(BlindReviewError, match="agreement_record_not_valid"):
        unblind_pair(key, {"pair_id": packet["pair_id"], "valid": False})

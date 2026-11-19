"""E.7 claim-to-evidence linkage and human-adjudication tests.

No provider calls, network access, or target-code execution are performed.
"""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from audit_engine.semantic_audit.ae32c.claim_evidence import (
    build_adjudication_template,
    build_claim_evidence_assessment,
    compute_inter_rater_agreement,
    validate_adjudication_record,
)


def _read_entry(evidence_id="E0002", *, content="1: # provider.total_calls is mentioned but not assigned", path="providers/adapter.py"):
    digest = hashlib.sha256(b"fixture-source").hexdigest()
    return SimpleNamespace(
        evidence_id=evidence_id,
        tool="read_source_file",
        status="ok",
        response_sha256=hashlib.sha256(evidence_id.encode()).hexdigest(),
        summary=f"read {path}",
        response={
            "result": {
                "path": path,
                "source_sha256": digest,
                "start_line": 1,
                "end_line": 1,
                "total_lines": 1,
                "content": content,
                "content_omitted": False,
                "source_range_complete": True,
            }
        },
    ), digest


def _graph_entry(evidence_id="E0003"):
    return SimpleNamespace(
        evidence_id=evidence_id,
        tool="graph_neighbors",
        status="ok",
        response_sha256="a" * 64,
        summary="CALLS relationship observed",
        response={"result": {"observations": [{"predicate": "CALLS"}]}},
    )


def _diagnosis(*, source_refs=None, evidence_refs=None, kind="observation", statement="Provider initializes total_calls"):
    read, digest = _read_entry()
    refs = source_refs if source_refs is not None else [{
        "evidence_id": "E0002", "path": "providers/adapter.py", "line": 1, "source_sha256": digest
    }]
    return {
        "root_cause": {
            "statement": "The consumer/provider interface may be inconsistent.",
            "confidence": "medium",
            "evidence_refs": ["E0002"],
            "source_references": refs,
        },
        "claims": [{
            "statement": statement,
            "kind": kind,
            "confidence": "high",
            "evidence_refs": evidence_refs if evidence_refs is not None else ["E0002"],
            "source_references": refs,
        }],
    }, read, digest


def test_direct_source_line_is_textual_witness_not_semantic_entailment():
    diagnosis, entry, _ = _diagnosis()
    assessment = build_claim_evidence_assessment(diagnosis, [entry])
    claim = assessment["items"][1]

    assert claim["evidence_linkage"] == "direct_source_line"
    assert claim["verification_level"] == "textual_witness"
    assert claim["support_outcome"] == "unverified"
    assert claim["semantic_support_assessment"] == "not_assessed"
    assert claim["source_ranges"] == [{
        "evidence_id": "E0002",
        "path": "providers/adapter.py",
        "start_line": 1,
        "end_line": 1,
        "source_sha256": entry.response["result"]["source_sha256"],
    }]
    # The fixture line is only a comment mentioning the token. The system must
    # not promote token presence to semantic support.
    assert "mentioned but not assigned" in entry.response["result"]["content"]


def test_successful_source_read_without_exact_claim_citation_is_reported_as_gap():
    diagnosis, entry, _ = _diagnosis(source_refs=[])
    assessment = build_claim_evidence_assessment(diagnosis, [entry])
    claim = assessment["items"][1]

    assert claim["evidence_linkage"] == "indirect_tool_context"
    assert claim["citation_gap"] is True
    assert claim["source_ranges"] == []
    assert claim["available_uncited_source_candidates"] == [{
        "evidence_id": "E0002",
        "path": "providers/adapter.py",
        "line": 1,
        "source_sha256": entry.response["result"]["source_sha256"],
    }]


def test_graph_only_evidence_is_indirect_not_a_direct_source_witness():
    diagnosis, _, _ = _diagnosis(source_refs=[], evidence_refs=["E0003"])
    assessment = build_claim_evidence_assessment(diagnosis, [_graph_entry()])
    claim = assessment["items"][1]

    assert claim["evidence_linkage"] == "indirect_tool_context"
    assert claim["verification_level"] == "ledger_linked"
    assert claim["support_outcome"] == "unverified"


def test_legacy_claim_kinds_map_to_small_e7_claim_taxonomy():
    diagnosis, entry, _ = _diagnosis(kind="hypothesis")
    diagnosis["claims"].append({
        "statement": "The code structure suggests a caller relationship.",
        "kind": "conclusion",
        "confidence": "medium",
        "evidence_refs": ["E0003"],
        "source_references": [],
    })
    assessment = build_claim_evidence_assessment(diagnosis, [entry, _graph_entry()])

    assert assessment["items"][1]["claim_type"] == "causal_hypothesis"
    assert assessment["items"][2]["claim_type"] == "static_inference"


def test_runtime_claim_remains_unverified_without_execution_evidence():
    diagnosis, entry, _ = _diagnosis(kind="runtime_claim")
    assessment = build_claim_evidence_assessment(diagnosis, [entry])
    claim = assessment["items"][1]

    assert claim["claim_type"] == "runtime_claim"
    assert claim["verification_level"] == "textual_witness"
    assert claim["support_outcome"] == "unverified"


def test_claim_ids_are_stable_for_same_role_type_and_statement():
    diagnosis, entry, _ = _diagnosis()
    first = build_claim_evidence_assessment(diagnosis, [entry])
    second = build_claim_evidence_assessment(diagnosis, [entry])
    assert [item["claim_id"] for item in first["items"]] == [item["claim_id"] for item in second["items"]]


def test_adjudication_template_covers_every_claim_and_validates():
    diagnosis, entry, _ = _diagnosis()
    assessment = build_claim_evidence_assessment(diagnosis, [entry])
    assessment["investigation_id"] = "investigation-001"
    template = build_adjudication_template(assessment, "investigation-001")
    template["reviewer_id"] = "reviewer-a"
    template["reviewed_at"] = "2026-11-19T10:00:00Z"
    for item in template["items"]:
        item["rationale"] = "The cited line was inspected in context; causal entailment is not established."
        item["outcome"] = "partially_supported"
        item["verification_level"] = "static_review"

    result = validate_adjudication_record(template, assessment)
    assert result["valid"] is True
    assert result["errors"] == []


def test_adjudication_rejects_unknown_evidence_and_unreviewed_causal_entailment():
    diagnosis, entry, _ = _diagnosis(kind="hypothesis")
    assessment = build_claim_evidence_assessment(diagnosis, [entry])
    assessment["investigation_id"] = "investigation-002"
    template = build_adjudication_template(assessment, "investigation-002")
    template["reviewer_id"] = "reviewer-a"
    template["reviewed_at"] = "2026-11-19T10:00:00Z"
    for item in template["items"]:
        item["rationale"] = "Insufficient independent verification."
        item["outcome"] = "entailed"
        item["verification_level"] = "textual_witness"
        item["supporting_evidence_ids"] = ["E9999"]

    result = validate_adjudication_record(template, assessment)
    assert result["valid"] is False
    assert "supporting_evidence_ids_invalid" in result["errors"]
    assert "causal_or_runtime_entailment_requires_reproduction_or_independent_review" in result["errors"]


def test_contradicted_review_requires_a_ledger_bound_counterevidence_id():
    diagnosis, entry, _ = _diagnosis()
    assessment = build_claim_evidence_assessment(diagnosis, [entry, _graph_entry()])
    assessment["investigation_id"] = "investigation-003"
    template = build_adjudication_template(assessment, "investigation-003")
    template["reviewer_id"] = "reviewer-a"
    template["reviewed_at"] = "2026-11-19T10:00:00Z"
    for item in template["items"]:
        item["rationale"] = "The graph record conflicts with the proposed relationship."
        item["outcome"] = "contradicted"
        item["verification_level"] = "static_review"
        item["counterevidence_ids"] = ["E0003"]

    result = validate_adjudication_record(template, assessment)
    assert result["valid"] is True


def test_two_reviewer_agreement_reports_raw_agreement_and_cohens_kappa():
    first = {
        "investigation_id": "i-1", "reviewer_id": "a",
        "items": [
            {"claim_id": "c1", "outcome": "entailed"},
            {"claim_id": "c2", "outcome": "entailed"},
            {"claim_id": "c3", "outcome": "unverified"},
            {"claim_id": "c4", "outcome": "contradicted"},
        ],
    }
    second = {
        "investigation_id": "i-1", "reviewer_id": "b",
        "items": [
            {"claim_id": "c1", "outcome": "entailed"},
            {"claim_id": "c2", "outcome": "partially_supported"},
            {"claim_id": "c3", "outcome": "unverified"},
            {"claim_id": "c4", "outcome": "contradicted"},
        ],
    }
    result = compute_inter_rater_agreement(first, second)
    assert result["claim_count"] == 4
    assert result["observed_agreement"] == 0.75
    assert result["cohens_kappa"] == pytest.approx(2 / 3, abs=1e-6)


def test_agreement_rejects_different_claim_sets():
    with pytest.raises(ValueError, match="claim_review_set_mismatch"):
        compute_inter_rater_agreement(
            {"investigation_id": "i", "items": [{"claim_id": "a", "outcome": "entailed"}]},
            {"investigation_id": "i", "items": [{"claim_id": "b", "outcome": "entailed"}]},
        )

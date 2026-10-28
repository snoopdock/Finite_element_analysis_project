"""AE-32D adjudication pack invariants; no provider calls or external dependencies."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "evaluation" / "ae32d"
ADJ = BENCHMARK / "adjudication"
DOCS = ROOT / "docs" / "audit-engine"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_reviewer_forms_are_independent_and_still_pending():
    schema = read_json(ADJ / "reviewer-form.schema.json")
    first = read_json(ADJ / "reviewer-1.template.json")
    second = read_json(ADJ / "reviewer-2.template.json")

    assert schema["properties"]["schema_version"]["const"] == "ae32d/reviewer-form/v1"
    assert first["schema_version"] == second["schema_version"] == "ae32d/reviewer-form/v1"
    assert first["reviewer_id"] != second["reviewer_id"]
    assert first["label"] == second["label"] == "pending_adjudication"
    assert first["review_completed_at"] is None and second["review_completed_at"] is None
    assert first["blindness_attestation"]["has_not_seen_other_reviewer_labels"] is False
    assert second["blindness_attestation"]["has_not_seen_model_outputs_or_provider_identity"] is False


def test_adjudication_record_cannot_start_as_gold():
    schema = read_json(ADJ / "adjudication-record.schema.json")
    record = read_json(ADJ / "adjudication-record.template.json")
    assert schema["properties"]["schema_version"]["const"] == "ae32d/adjudication-record/v1"
    assert record["status"] == "pending"
    assert record["final_label"] == "pending_adjudication"
    assert record["primary_benchmark_eligible"] is False
    assert len(record["reviewer_submissions"]) == 2
    assert record["decided_at"] is None


def test_pilot_and_rubric_are_drafts_and_exclude_pending_case():
    plan = read_json(BENCHMARK / "pilot-plan.json")
    rubric = read_json(BENCHMARK / "scoring-rubric.json")
    manifest = read_json(BENCHMARK / "manifest.json")
    assert plan["status"] == "draft_pending_approval"
    assert plan["current_case_status"]["adjudicated_count"] == 0
    assert plan["current_case_status"]["primary_score_eligible_count"] == 0
    assert rubric["status"] == "draft_pending_approval"
    assert rubric["review_policy"]["no_weighted_composite_score"] is True
    assert manifest["status"] == "design_only"
    assert manifest["cases"][0]["primary_benchmark_eligible"] is False


def test_run_assessment_records_live_outcome_and_pause_deviation():
    assessment = (DOCS / "AE-32C-Live-Run-40503324230-Assessment.md").read_text(encoding="utf-8")
    assert "40502970945" in assessment
    assert "40503324230" in assessment
    assert "5 / 12" in assessment
    assert "60 seconds" in assessment
    assert "not assessed" in assessment.lower()


def test_nararouter_plan_does_not_claim_unverified_root_cause():
    plan = (DOCS / "AE-32C-NaraRouter-HTTP400-Diagnostic-Plan.md").read_text(encoding="utf-8")
    assert "no root cause established" in plan.lower()
    assert "deterministic fixtures" in plan.lower()
    assert "synthesize a completion" in plan.lower()

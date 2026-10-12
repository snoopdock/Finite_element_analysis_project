"""G3.4.17 behavioral and adversarial tests (real records, not dummy contracts)."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from decision_memory.learning_rules import RuleValidationError, inspect_repository

ROOT = Path(__file__).resolve().parents[2]
RULE = "RULE-G3.4.17-001"


@pytest.fixture
def repository(tmp_path):
    for part in [
        "decision_memory/decisions/DEC-G3.4.13-001.yaml",
        "decision_memory/actions/ACTION-G3.4.15-001.yaml",
        "decision_memory/outcomes/OUTCOME-G3.4.16-001.yaml",
        "decision_memory/rules/RULE-G3.4.17-001.yaml",
        "decision_memory/learning_rule_schema.json",
        "validation/profiles/G3.4.16.yaml",
    ]:
        dest = tmp_path / part
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / part, dest)
    return tmp_path


def read(repo, part):
    return yaml.safe_load((repo / part).read_text(encoding="utf-8"))


def rewrite(repo, part, fn):
    p = repo / part
    obj = read(repo, part)
    fn(obj)
    p.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")


RULE_PATH = f"decision_memory/rules/{RULE}.yaml"
ACTION_PATH = "decision_memory/actions/ACTION-G3.4.15-001.yaml"
OUTCOME_PATH = "decision_memory/outcomes/OUTCOME-G3.4.16-001.yaml"


def test_real_cross_reference_graph_passes(repository):
    projection = inspect_repository(repository)
    assert projection["status"] == "candidate_only"
    assert projection["rules"][0]["rule_id"] == RULE
    assert projection["rules"][0]["eligible_for_automatic_sat_execution"] is False
    assert "pending_action_with_successful_feedback" in projection["rules"][0]["conflicts_acknowledged"]


def test_inspection_is_read_only(repository):
    before = {p.relative_to(repository): p.read_bytes() for p in repository.rglob("*") if p.is_file()}
    inspect_repository(repository)
    after = {p.relative_to(repository): p.read_bytes() for p in repository.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.parametrize("status", ["approved", "active", "enforced", None, "promoted"])
def test_no_automatic_rule_promotion(repository, status):
    rewrite(repository, RULE_PATH, lambda r: r.update(status=status))
    with pytest.raises(RuleValidationError):
        inspect_repository(repository)


@pytest.mark.parametrize("value", [True, "true", 1])
def test_no_unsupported_engineering_impact_claim(repository, value):
    rewrite(repository, RULE_PATH, lambda r: r["evidence_assessment"].update(engineering_impact_verified=value))
    with pytest.raises(RuleValidationError):
        inspect_repository(repository)


def test_bundle_reference_cannot_claim_local_verification(repository):
    rewrite(repository, RULE_PATH, lambda r: r["evidence_assessment"].update(external_bundle_checked=True))
    with pytest.raises(RuleValidationError):
        inspect_repository(repository)


def test_missing_decision_reference_rejected(repository):
    rewrite(repository, RULE_PATH, lambda r: r["sources"].update(decision_ids=["DEC-UNKNOWN"]))
    with pytest.raises(RuleValidationError, match="Dangling decision"):
        inspect_repository(repository)


def test_missing_action_reference_rejected(repository):
    rewrite(repository, RULE_PATH, lambda r: r["sources"].update(action_ids=["ACTION-UNKNOWN"]))
    with pytest.raises(RuleValidationError, match="Dangling action"):
        inspect_repository(repository)


def test_missing_outcome_reference_rejected(repository):
    rewrite(repository, RULE_PATH, lambda r: r["sources"].update(outcome_ids=["OUTCOME-UNKNOWN"]))
    with pytest.raises(RuleValidationError, match="Dangling outcome"):
        inspect_repository(repository)


def test_action_must_cite_decision(repository):
    rewrite(repository, ACTION_PATH, lambda r: r.update(decision_refs=["DEC-DIFFERENT"]))
    with pytest.raises(RuleValidationError, match="does not cite"):
        inspect_repository(repository)


def test_outcome_must_refer_to_action(repository):
    rewrite(repository, OUTCOME_PATH, lambda r: r.update(action_id=["ACTION-DIFFERENT"]))
    with pytest.raises(RuleValidationError, match="not linked"):
        inspect_repository(repository)


def test_discrepancy_must_be_declared(repository):
    rewrite(repository, RULE_PATH, lambda r: r["evidence_assessment"].update(discrepancies=[]))
    with pytest.raises(RuleValidationError, match="Unacknowledged"):
        inspect_repository(repository)


def test_no_conflict_when_action_is_completed(repository):
    rewrite(repository, ACTION_PATH, lambda r: r["outcome"].update(status="completed"))
    rewrite(repository, RULE_PATH, lambda r: r["evidence_assessment"].update(discrepancies=[]))
    assert inspect_repository(repository)["rules"][0]["conflicts_acknowledged"] == []


@pytest.mark.parametrize("field", ["id", "statement", "applicability", "sources", "observations", "limitations", "evidence_assessment", "review"])
def test_required_rule_fields(repository, field):
    rewrite(repository, RULE_PATH, lambda r: r.pop(field))
    with pytest.raises(RuleValidationError):
        inspect_repository(repository)


def test_unknown_rule_field_rejected(repository):
    rewrite(repository, RULE_PATH, lambda r: r.update(execute_sat_automatically=True))
    with pytest.raises(RuleValidationError, match="unknown"):
        inspect_repository(repository)


def test_rule_filename_must_match_id(repository):
    rewrite(repository, RULE_PATH, lambda r: r.update(id="RULE-G3.4.17-999"))
    with pytest.raises(RuleValidationError, match="Filename/ID"):
        inspect_repository(repository)


def test_strict_yaml_duplicate_fields_rejected(repository):
    with (repository / RULE_PATH).open("a", encoding="utf-8") as f:
        f.write("status: active\n")
    with pytest.raises(RuleValidationError, match="Duplicate"):
        inspect_repository(repository)


def test_symlinked_rule_rejected(repository, tmp_path):
    link = repository / RULE_PATH
    dest = tmp_path.parent / "external_rules.yaml"
    dest.write_bytes(link.read_bytes())
    link.unlink()
    link.symlink_to(dest)
    with pytest.raises(RuleValidationError, match="Unsafe"):
        inspect_repository(repository)


def test_no_rule_candidates_rejected(repository):
    (repository / RULE_PATH).unlink()
    with pytest.raises(RuleValidationError, match="No learning-rule"):
        inspect_repository(repository)


def test_absent_validation_profile_rejected(repository):
    (repository / "validation/profiles/G3.4.16.yaml").unlink()
    with pytest.raises(RuleValidationError):
        inspect_repository(repository)


def test_profile_id_mismatch_rejected(repository):
    rewrite(repository, "validation/profiles/G3.4.16.yaml", lambda r: r.update(id="G3.4.15"))
    with pytest.raises(RuleValidationError, match="Profile identity"):
        inspect_repository(repository)


@pytest.mark.parametrize("digest", ["oops", "A"*64, "f"*63, "../bad"])
def test_invalid_report_digest_rejected(repository, digest):
    rewrite(repository, RULE_PATH, lambda r: r["sources"]["validation_reports"][0].update(report_sha256=digest))
    with pytest.raises(RuleValidationError, match="SHA-256"):
        inspect_repository(repository)


def test_invalid_commit_digest_rejected(repository):
    rewrite(repository, RULE_PATH, lambda r: r["sources"]["validation_reports"][0].update(source_commit_sha="f"*41))
    with pytest.raises(RuleValidationError, match="commit"):
        inspect_repository(repository)


def test_schema_rejects_promotion_allowlist(repository):
    p = repository / "decision_memory/learning_rule_schema.json"
    data = json.loads(p.read_text())
    data["allowed_statuses"].append("approved")
    p.write_text(json.dumps(data))
    with pytest.raises(RuleValidationError, match="candidate rules only"):
        inspect_repository(repository)


def test_schema_symlink_rejected(repository, tmp_path):
    p = repository / "decision_memory/learning_rule_schema.json"
    q = tmp_path.parent / "external_schema.json"
    q.write_bytes(p.read_bytes())
    p.unlink()
    p.symlink_to(q)
    with pytest.raises(RuleValidationError, match="unsafe"):
        inspect_repository(repository)


def test_cli_emits_audit_view_without_activating_rules(repository):
    script = ROOT / "decision_memory/learning_rules.py"
    out = repository / "summary.json"
    result = subprocess.run(
        [sys.executable, str(script), "--repository", str(repository), "--output", str(out)],
        text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    view = json.loads(out.read_text())
    assert view["rules"][0]["eligible_for_automatic_sat_execution"] is False


def test_cli_returns_failure_for_invalid_graph(repository):
    rewrite(repository, RULE_PATH, lambda r: r.update(status="approved"))
    script = ROOT / "decision_memory/learning_rules.py"
    result = subprocess.run([sys.executable, str(script), "--repository", str(repository)], text=True, capture_output=True, timeout=15)
    assert result.returncode != 0
    assert "Rule validation error" in result.stderr


def test_schema_cannot_weaken_required_keys(repository):
    p = repository / "decision_memory/learning_rule_schema.json"
    config = json.loads(p.read_text())
    config["required_fields"].remove("limitations")
    p.write_text(json.dumps(config))
    with pytest.raises(RuleValidationError, match="weakened"):
        inspect_repository(repository)


def test_projection_exposes_exact_provenance_sha(repository):
    item = inspect_repository(repository)["rules"][0]
    assert item["source_validation_report_sha256"] == [
        "5c89616682251124dc2443e3dc5e2ed6323989ea19d2b8ef6e2ce9395636d4fd"
    ]
    assert item["source_validation_commits"] == [
        "063f8bd3bf8d894f3d96d4418ac270cbd1ea8f88"
    ]

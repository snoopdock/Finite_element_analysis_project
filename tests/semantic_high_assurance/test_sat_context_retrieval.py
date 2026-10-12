"""Contract and adversarial tests for G3.4.18 SAT memory retrieval."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# This is the checked-out target repository (not the stable main checkout).
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from decision_memory import context_retrieval as ctx  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    for sub in ("decision_memory", "validation"):
        shutil.copytree(ROOT / sub, tmp_path / sub, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return tmp_path


def test_schema_and_flags(store):
    result = ctx.retrieve(store, "schema validation proof engineering", 12)
    assert result["schema_version"] == "sat-memory-context/v1"
    assert result["automated_sat_action_allowed"] is False
    assert result["human_review_required"] is True
    assert result["retrieval_is_evidence_verification"] is False
    assert result["matching_records"] >= 1
    assert all(hit["eligible_for_automatic_sat_execution"] is False for hit in result["results"])


def test_rule_candidate_never_promoted(store):
    matches = ctx.retrieve(store, "schema validation successful engineering impact", 20)["results"]
    rule = next(hit for hit in matches if hit["record_type"] == "rule_candidate")
    assert rule["review_status"] == "candidate_unapproved"
    assert "engineering_impact_not_verified" in rule["caveats"]
    assert "historical_status_conflict_acknowledged" in rule["caveats"]
    assert rule["external_validation_report_bytes_checked"] is False
    assert len(rule["validation_report_references"]) == 1


def test_decision_is_grounded(store):
    matches = ctx.retrieve(store, "engineering rationale", 20)["results"]
    dec = next(hit for hit in matches if hit["record_id"] == "DEC-G3.4.13-001")
    src = store / dec["source_path"]
    assert src.is_file()
    assert dec["source_sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert dec["record_type"] == "decision"


def test_conflict_is_not_silenced(store):
    matches = ctx.retrieve(store, "successful outcome pending", 20)["results"]
    outcome = next(hit for hit in matches if hit["record_type"] == "outcome")
    assert "pending_action_with_successful_feedback" in outcome["caveats"]


def test_unresolved_decision_not_invented(store):
    matches = ctx.retrieve(store, "architecture SAT action", 20)["results"]
    action = next(hit for hit in matches if hit["record_type"] == "action")
    assert "unresolved_decision_reference" in action["caveats"]
    assert all(x["record_id"] != "DEC-G3.4.14-001" for x in action["related_sources"])


def test_canonical_context_hash(store):
    out = ctx.retrieve(store, "decision evidence", 8)
    digest = out.pop("context_sha256")
    canon = json.dumps(out, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    assert hashlib.sha256(canon).hexdigest() == digest


def test_determinism(store):
    first = ctx.retrieve(store, "SAT action history", 8)
    second = ctx.retrieve(store, "SAT action history", 8)
    assert first == second
    assert first["results"] == sorted(first["results"], key=lambda x: (-x["match_score"], x["record_type"], x["record_id"]))


def test_empty_query_matches_nothing_not_everything(store):
    result = ctx.retrieve(store, "zzunmatchedrandom999", 10)
    assert result["matching_records"] == 0
    assert result["results"] == []


@pytest.mark.parametrize("query", ["", "  ", "the and is", "\x00unsafe", "word " * 200])
def test_reject_bad_queries(store, query):
    with pytest.raises(ctx.ContextRetrievalError):
        ctx.retrieve(store, query)


@pytest.mark.parametrize("limit", [0, 21, -1, True, 5.5])
def test_bad_max_results_rejected(store, limit):
    with pytest.raises(ctx.ContextRetrievalError):
        ctx.retrieve(store, "decision", limit)


def test_max_results_is_enforced(store):
    data = ctx.retrieve(store, "SAT engineering decision validation outcome", 1)
    assert len(data["results"]) <= 1
    assert data["matching_records"] >= len(data["results"])


def test_missing_rule_rejected(store):
    (store / "decision_memory/rules/RULE-G3.4.17-001.yaml").unlink()
    with pytest.raises(ctx.learning_rules.RuleValidationError):
        ctx.retrieve(store, "decision")


def test_dangling_rule_ref_fails_closed(store):
    (store / "decision_memory/decisions/DEC-G3.4.13-001.yaml").unlink()
    with pytest.raises(ctx.learning_rules.RuleValidationError):
        ctx.retrieve(store, "decision")


def test_duplicate_yaml_keys_rejected(store):
    target = store / "decision_memory/decisions/DEC-G3.4.13-001.yaml"
    target.write_text(target.read_text() + "\nid: DEC-G3.4.13-001\n")
    with pytest.raises(ctx.learning_rules.RuleValidationError):
        ctx.retrieve(store, "decision")


def test_dangerous_yaml_tags_rejected(store):
    target = store / "decision_memory/decisions/DEC-G3.4.13-001.yaml"
    target.write_text("id: DEC-G3.4.13-001\ndecision: !!python/object/apply:os.system ['echo evil']\n")
    with pytest.raises(ctx.learning_rules.RuleValidationError):
        ctx.retrieve(store, "decision")


def test_symlink_source_rejected(store, tmp_path):
    target = store / "decision_memory/actions/ACTION-G3.4.15-001.yaml"
    copy = tmp_path / "outside.yaml"
    copy.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(copy)
    with pytest.raises((ctx.learning_rules.RuleValidationError, ctx.ContextRetrievalError)):
        ctx.retrieve(store, "action")


def test_enormous_memory_file_rejected(store):
    target = store / "decision_memory/actions/ACTION-G3.4.15-001.yaml"
    target.write_text(target.read_text() + "\n#" + "x" * (ctx.MAX_SOURCE_BYTES + 2))
    with pytest.raises(ctx.ContextRetrievalError):
        ctx.retrieve(store, "action")


def test_human_review_flag_cannot_be_bypassed(store):
    target = store / "decision_memory/rules/RULE-G3.4.17-001.yaml"
    target.write_text(target.read_text().replace("approved: false", "approved: true"))
    with pytest.raises(ctx.learning_rules.RuleValidationError):
        ctx.retrieve(store, "decision")


def test_profile_tamper_rejected(store):
    target = store / "validation/profiles/G3.4.16.yaml"
    target.write_text("id: G0.0\n")
    with pytest.raises(ctx.learning_rules.RuleValidationError):
        ctx.retrieve(store, "action")


def test_stdout_command_does_not_write(store, tmp_path):
    output = subprocess.run(
        [sys.executable, str(ROOT / "decision_memory/context_retrieval.py"), "--repository", str(store), "--query", "engineering rationale"],
        cwd=tmp_path, text=True, capture_output=True, timeout=15, check=True,
    )
    assert json.loads(output.stdout)["schema_version"] == "sat-memory-context/v1"
    assert not (tmp_path / "sat-context.json").exists()


def test_explicit_output_outside_repo_only(store, tmp_path):
    external = tmp_path.parent / (tmp_path.name + "-result.json")
    try:
        ctx._write_optional(external, "{}\n", store)
        assert external.read_text() == "{}\n"
    finally:
        external.unlink(missing_ok=True)
    with pytest.raises(ctx.ContextRetrievalError):
        ctx._write_optional(store / "sat-context.json", "{}\n", store)


def test_symlink_output_rejected(store, tmp_path):
    target = tmp_path / "normal.json"
    target.write_text("safe")
    alias = tmp_path / "link.json"
    alias.symlink_to(target)
    with pytest.raises(ctx.ContextRetrievalError):
        ctx._write_optional(alias, "{}\n", store)
    assert target.read_text() == "safe"


def test_existing_output_atomic_replace(store, tmp_path):
    target = tmp_path.parent / (tmp_path.name + "-replace.json")
    try:
        target.write_text("old")
        ctx._write_optional(target, "new", store)
        assert target.read_text() == "new"
    finally:
        target.unlink(missing_ok=True)


def test_unicode_query_supported(store):
    # No transliteration, no fabricated match -- unicode tokens remain valid.
    data = ctx.retrieve(store, "تصمیم مهندسی", 5)
    assert data["results"] == []
    assert data["query_terms"] == ["تصمیم", "مهندسی"]


def test_no_script_instruction_execution(store, tmp_path):
    path = store / "decision_memory/decisions/DEC-G3.4.13-001.yaml"
    marker = tmp_path / "executed"
    path.write_text(path.read_text().replace("No rationale preservation.", f"echo > {marker}"))
    report = ctx.retrieve(store, "echo rationale", 10)
    assert report["automated_sat_action_allowed"] is False
    assert not marker.exists()

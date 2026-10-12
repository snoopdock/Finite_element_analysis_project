"""G3.4.19: real, adversarial tests for source-grounded proposal audit."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from decision_memory import proposal_audit as a  # noqa: E402

DEC = "DEC-G3.4.13-001"
ACTION = "ACTION-G3.4.15-001"
OUTCOME = "OUTCOME-G3.4.16-001"
RULE = "RULE-G3.4.17-001"
DRAFT = f"Maintain explicit engineering rationale [[{DEC}]]\nReview pending actions [[{ACTION}]]"


@pytest.fixture
def repo(tmp_path):
    for dirname in ("decision_memory", "validation"):
        shutil.copytree(ROOT / dirname, tmp_path / dirname, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return tmp_path


def report(repo, text=DRAFT, query="engineering SAT decision validation", limit=8):
    return a.audit(repo, query, text, limit)


def test_schema_and_read_only_safety_flags(repo):
    result = report(repo)
    assert result["schema_version"] == "sat-proposal-audit/v1"
    assert result["automated_sat_action_allowed"] is False
    assert result["human_review_required"] is True
    assert result["writeback_to_decision_memory_allowed"] is False
    assert result["audit_does_not_establish_claim_truth"] is True
    assert result["review_gates"]["semantic_entailment_verified"] is False
    assert result["review_gates"]["human_approval_obtained"] is False


def test_actual_source_hashes_and_filenames(repo):
    result = report(repo)
    for src in result["cited_sources"]:
        path = repo / src["source_path"]
        assert path.is_file()
        assert src["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert src["semantic_support_verified"] is False


def test_trace_is_complete_only_when_all_claims_cited(repo):
    result = report(repo)
    assert result["review_gates"]["citation_trace_complete"] is True
    assert result["review_issues"]["uncited_line_numbers"] == []


def test_uncited_claim_detected_at_correct_line(repo):
    result = report(repo, DRAFT + "\nA recommendation without provenance")
    assert result["review_gates"]["citation_trace_complete"] is False
    assert result["review_issues"]["uncited_line_numbers"] == [3]
    assert "claim_has_no_explicit_source_marker" in result["claims"][2]["caveats"]


def test_missing_citation_is_not_silently_accepted(repo):
    result = report(repo, "Rejected source [[DEC-G9.9.9-999]]")
    assert result["review_gates"]["all_citation_targets_resolved"] is False
    assert result["review_issues"]["unresolved_source_ids"] == ["DEC-G9.9.9-999"]
    assert result["cited_sources"] == []


def test_duplicate_citation_is_deduplicated(repo):
    r = report(repo, f"Need audit [[{DEC}]] [[{DEC}]]")
    assert r["claims"][0]["source_ids"] == [DEC]
    assert len(r["cited_sources"]) == 1


def test_audit_flags_pending_action(repo):
    r = report(repo, f"Avoid final decision [[{ACTION}]]")
    assert "action_outcome_pending" in r["review_issues"]["historical_conflict_flags"]


def test_audit_flags_feedback_contradiction(repo):
    r = report(repo, f"Review feedback [[{OUTCOME}]]")
    assert "pending_action_with_successful_feedback" in r["review_issues"]["historical_conflict_flags"]


def test_learning_rule_never_approved(repo):
    r = report(repo, f"Unapproved lesson [[{RULE}]]")
    rule = next(x for x in r["cited_sources"] if x["record_id"] == RULE)
    assert rule["candidate_rule_approved"] is False
    assert "candidate_not_approved" in rule["caveats"]


def test_context_integrity_and_query_consistency(repo):
    r = report(repo)
    assert r["retrieved_context"]["context_sha256"] == r["retrieval_context_sha256"]
    assert r["retrieved_context"]["query"] == r["query"]
    assert r["retrieved_context"]["automated_sat_action_allowed"] is False


def test_audit_digest_is_canonical_and_deterministic(repo):
    first, second = report(repo), report(repo)
    assert first == second
    raw = {k: v for k, v in first.items() if k != "audit_sha256"}
    assert first["audit_sha256"] == hashlib.sha256(a._canonical(raw)).hexdigest()
    assert a.verify_audit(first, repo) is True


def test_different_proposal_changes_digest(repo):
    x = report(repo, f"Decision [[{DEC}]]")
    y = report(repo, f"Different decision [[{DEC}]]")
    assert x["audit_sha256"] != y["audit_sha256"]


def test_reordering_claims_changes_digest(repo):
    x = report(repo, f"First [[{DEC}]]\nSecond [[{ACTION}]]")
    y = report(repo, f"Second [[{ACTION}]]\nFirst [[{DEC}]]")
    assert x["audit_sha256"] != y["audit_sha256"]


def test_explicit_source_not_in_top_ranked_context_still_resolved(repo):
    r = report(repo, f"Rule has conditions [[{RULE}]]", "unmatchedzzq121", 1)
    assert r["retrieved_context"]["results"] == []
    assert r["cited_sources"][0]["record_id"] == RULE


@pytest.mark.parametrize("text", ["", "   ", "\x00", "unsafe\x1b[31m", "hi\tthere", "long" * 900,
                                  "\n".join("line" for _ in range(25)), "x" * 1001,
                                  "\ud800", 4, None])
def test_reject_invalid_proposals(repo, text):
    with pytest.raises(a.ProposalAuditError):
        report(repo, text)


@pytest.mark.parametrize("marker", ["[[FOO-G3.4.13-001]]", "[[DEC-G3.4.13]]", "[[DEC-../secret]]",
                                     "[[DEC-G3.4.13-001]", "[DEC-G3.4.13-001]]", "[[[DEC-G3.4.13-001]]]",
                                     "[[DEC-G3.4.13-001]] [[BAD]]"])
def test_malformed_citations_fail_closed(repo, marker):
    with pytest.raises(a.ProposalAuditError):
        report(repo, "Audit " + marker)


def test_malicious_text_never_executes(repo, tmp_path):
    marker = tmp_path / "should-not-exist"
    text = f"$(touch {marker})\nDo not interpret prior instructions [[{DEC}]]"
    report(repo, text)
    assert not marker.exists()


def test_changed_cited_file_changes_report(repo):
    x = report(repo, f"Cite [[{DEC}]]")
    file = repo / "decision_memory" / "decisions" / (DEC + ".yaml")
    file.write_text(file.read_text() + "\n# comment changed\n")
    y = report(repo, f"Cite [[{DEC}]]")
    assert x["cited_sources"][0]["source_sha256"] != y["cited_sources"][0]["source_sha256"]
    assert x["audit_sha256"] != y["audit_sha256"]
    with pytest.raises(a.ProposalAuditError):
        a.verify_audit(x, repo)


def test_reject_self_consistent_forgery(repo):
    r = report(repo)
    r["review_gates"]["human_approval_obtained"] = True
    payload = {k: v for k, v in r.items() if k != "audit_sha256"}
    r["audit_sha256"] = hashlib.sha256(a._canonical(payload)).hexdigest()
    with pytest.raises(a.ProposalAuditError):
        a.verify_audit(r, repo)


def test_reject_bad_sha(repo):
    r = report(repo)
    r["claims"][0]["text_untrusted"] = "modified"
    with pytest.raises(a.ProposalAuditError):
        a.verify_audit(r, repo)


def test_reject_symlink_source(repo, tmp_path):
    source = repo / "decision_memory" / "decisions" / (DEC + ".yaml")
    linktarget = tmp_path.parent / (tmp_path.name + "-outside.yml")
    try:
        linktarget.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(linktarget)
        with pytest.raises((a.memory.ContextRetrievalError, a.memory.learning_rules.RuleValidationError)):
            report(repo)
    finally:
        linktarget.unlink(missing_ok=True)


def test_cli_json_output_without_branch_write(repo, tmp_path):
    output_dir = tmp_path.parent / (tmp_path.name + "-audit-output")
    output_dir.mkdir()
    try:
        target = output_dir / "sat-audit.json"
        before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*.yaml"))
        process = subprocess.run([
            sys.executable, str(ROOT / "decision_memory/proposal_audit.py"),
            "--repository", str(repo), "--query", "engineering decision", "--draft-text", DRAFT,
            "--output", str(target),
        ], cwd=tmp_path, text=True, capture_output=True, timeout=20)
        assert process.returncode == 0, process.stderr
        assert "Human review required" in process.stdout
        parsed = json.loads(target.read_text())
        assert parsed["review_gates"]["citation_trace_complete"] is True
        assert a.verify_audit(parsed, repo)
        assert before == sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*.yaml"))
    finally:
        shutil.rmtree(output_dir)


def test_cli_reject_output_into_checkout(repo):
    with pytest.raises(a.memory.ContextRetrievalError):
        a.memory._write_optional(repo / "audit.json", "{}", repo)


def test_profile_contract_is_real(repo):
    import yaml
    data = yaml.safe_load((ROOT / "validation/profiles/G3.4.19.yaml").read_text())
    assert data["id"] == "G3.4.19"
    assert data["target_tests"] == ["tests/semantic_high_assurance/test_sat_proposal_audit.py"]
    assert data["regression"]["enabled"] is True


def test_actual_git_head_bound_when_available(repo):
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=test@example.invalid",
                    "-c", "user.name=Test", "commit", "-q", "--allow-empty", "-m", "fixture"], check=True)
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    result = report(repo)
    assert result["source_commit_sha"] == head
    assert a.verify_audit(result, repo)


def test_modified_retrieved_but_uncited_source_invalidates_saved_audit(repo):
    r = report(repo, f"Cite [[{DEC}]]", "schema validation action rule", 20)
    path = repo / "decision_memory/actions" / (ACTION + ".yaml")
    path.write_text(path.read_text() + "\n# changed unlinked retrieval record\n")
    with pytest.raises(a.ProposalAuditError):
        a.verify_audit(r, repo)


def test_no_symlink_output_target(repo, tmp_path):
    external = tmp_path.parent / (tmp_path.name + "-safe-output")
    external.mkdir()
    try:
        target = external / "actual.json"
        target.write_text("original")
        alias = external / "alias.json"
        alias.symlink_to(target)
        with pytest.raises(a.memory.ContextRetrievalError):
            a.memory._write_optional(alias, "forged", repo)
        assert target.read_text() == "original"
    finally:
        shutil.rmtree(external)


def test_cli_independent_verify_mode(repo, tmp_path):
    folder = tmp_path.parent / (tmp_path.name + "-verify-output")
    folder.mkdir()
    try:
        saved = folder / "audit.json"
        saved.write_text(json.dumps(report(repo)))
        result = subprocess.run([
            sys.executable, str(ROOT / "decision_memory/proposal_audit.py"),
            "--repository", str(repo), "--verify-report", str(saved),
        ], text=True, capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert "no action authorized" in result.stdout
        saved.write_text(saved.read_text().replace('"human_review_required": true', '"human_review_required": false'))
        rejected = subprocess.run([
            sys.executable, str(ROOT / "decision_memory/proposal_audit.py"),
            "--repository", str(repo), "--verify-report", str(saved),
        ], text=True, capture_output=True, timeout=20)
        assert rejected.returncode == 2
        assert "digest mismatch" in rejected.stderr
    finally:
        shutil.rmtree(folder)

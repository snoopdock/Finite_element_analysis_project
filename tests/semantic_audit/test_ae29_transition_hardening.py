"""G9.32 transition-boundary hardening tests for AE-29.

These tests exercise the public session-transition API independently from the
AE-29 test suite. The goal is to prevent a validly hashed decision record from
being sufficient to seal an unauthorized state transition.
"""
from __future__ import annotations

import copy
import hashlib
import base64

import pytest

from audit_engine.semantic_audit.ae29 import (
    IterativeAuditError,
    RepositorySnapshot,
    advance_session,
    evaluate_iteration,
    make_audit_report,
    make_decision_record,
    make_finding,
    make_neural_handoff,
    make_repair_proposal,
    make_verification,
    start_session,
)


def _snapshot() -> RepositorySnapshot:
    return RepositorySnapshot({
        "src/bug.py": b"return 1\n",
        "tests/test_bug.py": b"assert True\n",
    })


def _audit(snapshot, findings=()):
    return make_audit_report(
        snapshot,
        list(findings),
        auditor_id="g932-auditor",
        auditor_version="1",
        run_sha256="1" * 64,
    )


def _finding(snapshot, status="open"):
    return make_finding(
        snapshot,
        finding_id="f-1",
        rule_id="r-1",
        category="correctness",
        severity="high",
        title="Bad return",
        message="The return value is incorrect.",
        evidence_paths=("src/bug.py",),
        status=status,
    )


def _handoff(snapshot):
    return make_neural_handoff(
        snapshot,
        interpretation_sha256="2" * 64,
        request_sha256="3" * 64,
        candidate_ids=["candidate-1"],
    )


def _repair(snapshot, finding, handoff):
    content = b"return 2\n"
    operation = {
        "op": "write_file",
        "path": "src/bug.py",
        "expected_sha256": hashlib.sha256(snapshot.files["src/bug.py"]).hexdigest(),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "content_b64": base64.b64encode(content).decode("ascii"),
    }
    return make_repair_proposal(
        snapshot,
        repair_id="repair-1",
        target_finding_ids=[finding["finding_id"]],
        target_finding_fingerprints={
            finding["finding_id"]: finding["finding_fingerprint"],
        },
        neural_handoff_sha256=handoff["handoff_sha256"],
        kind="code_fix",
        operations=[operation],
        reason_codes=["g932"],
    )


def _verification(before, after, repair):
    return make_verification(
        before,
        after,
        repair,
        verifier_id="g932-verifier",
        verifier_version="1",
        run_sha256="4" * 64,
        status="passed",
        checks=[{
            "id": "check",
            "status": "passed",
            "detail_sha256": "5" * 64,
        }],
    )


def test_forged_accept_decision_cannot_advance_session():
    snapshot = _snapshot()
    session = start_session(snapshot, session_id="forged", max_iterations=1)
    record = make_decision_record(
        session_id="forged",
        iteration_index=1,
        input_snapshot_sha256=snapshot.snapshot_sha256,
        output_snapshot_sha256=snapshot.snapshot_sha256,
        finding_ids=[],
        neural_handoff_sha256=None,
        repair_sha256=None,
        verification_sha256=None,
        decision="accept_repair",
        reason_code="forged_acceptance",
        remaining_finding_ids=[],
        lesson_codes=["g932"],
        finding_context=[],
        repair_kind=None,
    )
    forged_result = {
        "decision": "accept_repair",
        "decision_record": record,
        "state_changed": False,
        "input_snapshot": snapshot,
        "snapshot": snapshot,
        "candidate_snapshot": None,
        "audit": _audit(snapshot),
        "handoff": None,
        "repair": None,
        "verification": None,
        "post_audit": None,
        "candidate_rejected": False,
    }
    with pytest.raises(IterativeAuditError, match="complete repair evidence"):
        advance_session(session, forged_result)


def test_accepted_transition_requires_matching_candidate_snapshot():
    snapshot = _snapshot()
    finding = _finding(snapshot)
    audit = _audit(snapshot, [finding])
    handoff = _handoff(snapshot)
    repair = _repair(snapshot, finding, handoff)
    candidate = snapshot.apply(repair)
    verification = _verification(snapshot, candidate, repair)
    post = _audit(candidate, [_finding(candidate, status="resolved")])
    session = start_session(snapshot, session_id="candidate", max_iterations=2)
    result = evaluate_iteration(
        session=session,
        snapshot=snapshot,
        audit=audit,
        handoff=handoff,
        repair=repair,
        verification=verification,
        post_audit=post,
    )
    tampered = dict(result)
    tampered["candidate_snapshot"] = snapshot
    with pytest.raises(IterativeAuditError, match="Candidate snapshot"):
        advance_session(session, tampered)


def test_no_repair_transition_may_retain_a_verified_handoff():
    snapshot = _snapshot()
    finding = _finding(snapshot)
    audit = _audit(snapshot, [finding])
    handoff = _handoff(snapshot)
    session = start_session(snapshot, session_id="defer", max_iterations=2)
    result = evaluate_iteration(
        session=session,
        snapshot=snapshot,
        audit=audit,
        handoff=handoff,
        repair=None,
        verification=None,
        post_audit=None,
    )
    advanced = advance_session(session, result)
    assert advanced["iteration_index"] == 1
    assert advanced["current_snapshot_sha256"] == snapshot.snapshot_sha256
    assert advanced["status"] == "active"


def test_accepted_transition_rejects_missing_verification():
    snapshot = _snapshot()
    finding = _finding(snapshot)
    audit = _audit(snapshot, [finding])
    handoff = _handoff(snapshot)
    repair = _repair(snapshot, finding, handoff)
    candidate = snapshot.apply(repair)
    verification = _verification(snapshot, candidate, repair)
    post = _audit(candidate, [_finding(candidate, status="resolved")])
    session = start_session(snapshot, session_id="missing-verification", max_iterations=2)
    result = evaluate_iteration(
        session=session,
        snapshot=snapshot,
        audit=audit,
        handoff=handoff,
        repair=repair,
        verification=verification,
        post_audit=post,
    )
    tampered = dict(result)
    tampered["verification"] = None
    with pytest.raises(IterativeAuditError, match="complete repair evidence|verification binding"):
        advance_session(session, tampered)

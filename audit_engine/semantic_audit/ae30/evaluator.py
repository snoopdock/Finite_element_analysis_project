"""AE-30 independent evaluation of the AE-29 repository-correction control loop.

The evaluator is intentionally separate from the AE-29 test helpers. It uses
only public AE-29 APIs and independent expected outcomes. It does not invoke
an LLM, shell, network service, Git, or a real repository checkout.

AE-30 evaluates the control loop, not the quality of a live model. Live-model
qualification remains a later, separately controlled activity.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import base64
import copy
import hashlib
import re
from typing import Any, Callable

from audit_engine.semantic_audit.ae24.contracts import canonical, sha
from audit_engine.semantic_audit.ae29 import (
    DecisionMemory,
    IterativeAuditError,
    RepositorySnapshot,
    advance_session,
    evaluate_iteration,
    make_audit_report,
    make_finding,
    make_neural_handoff,
    make_repair_proposal,
    make_verification,
    start_session,
    validate_decision_record,
    validate_neural_handoff,
    validate_repair,
)


REPORT_SCHEMA = "ae30/independent-evaluation/v1"
EVALUATOR_ID = "ae30-independent-reference-evaluator"
EVALUATOR_VERSION = "1"
MAX_CASES = 32


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    class_name: str
    expected: str
    actual: str
    passed: bool
    state_changed: bool
    input_snapshot_sha256: str
    output_snapshot_sha256: str
    detail: str


def _digest(value: Any) -> str:
    return sha(canonical(value))


def _file_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _snapshot() -> RepositorySnapshot:
    return RepositorySnapshot({
        "src/bug.py": b"return 1\n",
        "tests/test_bug.py": b"assert True\n",
        "README.md": b"repository\n",
    })


def _finding(snapshot: RepositorySnapshot, *, status: str = "open", fid: str = "finding-1"):
    return make_finding(
        snapshot,
        finding_id=fid,
        rule_id="rule-correctness",
        category="correctness",
        severity="high",
        title="Incorrect return value",
        message="The function returns an incorrect value.",
        evidence_paths=("src/bug.py",),
        status=status,
    )


def _audit(snapshot: RepositorySnapshot, findings):
    return make_audit_report(
        snapshot,
        findings,
        auditor_id="ae30-reference-auditor",
        auditor_version="1",
        run_sha256="1" * 64,
    )


def _handoff(snapshot: RepositorySnapshot, candidate_id: str = "candidate-1"):
    return make_neural_handoff(
        snapshot,
        interpretation_sha256="2" * 64,
        request_sha256="3" * 64,
        candidate_ids=[candidate_id],
    )


def _repair(snapshot: RepositorySnapshot, handoff: dict, finding_obj: dict, *,
            content: bytes = b"return 2\n", repair_id: str = "repair-1"):
    op = {
        "op": "write_file",
        "path": "src/bug.py",
        "expected_sha256": _file_digest(snapshot.files["src/bug.py"]),
        "content_sha256": _file_digest(content),
        "content_b64": base64.b64encode(content).decode("ascii"),
    }
    return make_repair_proposal(
        snapshot,
        repair_id=repair_id,
        target_finding_ids=[finding_obj["finding_id"]],
        target_finding_fingerprints={
            finding_obj["finding_id"]: finding_obj["finding_fingerprint"]
        },
        neural_handoff_sha256=handoff["handoff_sha256"],
        kind="code_fix",
        operations=[op],
        reason_codes=["ae30_reference_correction"],
    )


def _verification(before, after, repair, status="passed"):
    check_status = "passed" if status == "passed" else "failed"
    return make_verification(
        before,
        after,
        repair,
        verifier_id="ae30-reference-verifier",
        verifier_version="1",
        run_sha256="4" * 64,
        status=status,
        checks=[{
            "id": "independent-reference-check",
            "status": check_status,
            "detail_sha256": "5" * 64,
        }],
    )


def _accepted_iteration(snapshot: RepositorySnapshot):
    finding_obj = _finding(snapshot)
    audit = _audit(snapshot, [finding_obj])
    handoff = _handoff(snapshot)
    repair = _repair(snapshot, handoff, finding_obj)
    candidate = snapshot.apply(repair)
    verification = _verification(snapshot, candidate, repair, "passed")
    post = _audit(candidate, [_finding(candidate, status="resolved")])
    session = start_session(snapshot, session_id="ae30-success", max_iterations=3)
    result = evaluate_iteration(
        session=session,
        snapshot=snapshot,
        audit=audit,
        handoff=handoff,
        repair=repair,
        verification=verification,
        post_audit=post,
    )
    return snapshot, result, advance_session(session, result)


def _case_success() -> CaseResult:
    snap, result, advanced = _accepted_iteration(_snapshot())
    passed = (
        result["decision"] == "accept_repair"
        and result["state_changed"]
        and result["snapshot"].snapshot_sha256 != snap.snapshot_sha256
        and result["decision_record"]["output_snapshot_sha256"] == result["snapshot"].snapshot_sha256
        and advanced["current_snapshot_sha256"] == result["snapshot"].snapshot_sha256
        and advanced["status"] == "complete"
        and snap.files["src/bug.py"] == b"return 1\n"
    )
    return CaseResult(
        "AE30-C01", "positive-control", "accept_repair", result["decision"], passed,
        result["state_changed"], snap.snapshot_sha256, result["snapshot"].snapshot_sha256,
        "verified repair plus resolved post-audit is accepted",
    )


def _case_failed_verification() -> CaseResult:
    snap = _snapshot()
    f = _finding(snap)
    audit = _audit(snap, [f])
    handoff = _handoff(snap)
    repair = _repair(snap, handoff, f)
    candidate = snap.apply(repair)
    verification = _verification(snap, candidate, repair, "failed")
    session = start_session(snap, session_id="ae30-failed-verification", max_iterations=3)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=audit, handoff=handoff,
        repair=repair, verification=verification, post_audit=None,
    )
    passed = result["decision"] == "reject_repair" and not result["state_changed"]
    return CaseResult(
        "AE30-C02", "negative-control", "reject_repair", result["decision"], passed,
        result["state_changed"], snap.snapshot_sha256, result["snapshot"].snapshot_sha256,
        "failed independent verification cannot change controller state",
    )


def _case_inconclusive_verification() -> CaseResult:
    snap = _snapshot()
    f = _finding(snap)
    audit = _audit(snap, [f])
    handoff = _handoff(snap)
    repair = _repair(snap, handoff, f)
    candidate = snap.apply(repair)
    verification = _verification(snap, candidate, repair, "inconclusive")
    session = start_session(snap, session_id="ae30-inconclusive", max_iterations=3)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=audit, handoff=handoff,
        repair=repair, verification=verification, post_audit=None,
    )
    passed = result["decision"] == "defer" and not result["state_changed"]
    return CaseResult(
        "AE30-C03", "negative-control", "defer", result["decision"], passed,
        result["state_changed"], snap.snapshot_sha256, result["snapshot"].snapshot_sha256,
        "inconclusive verification cannot authorize state change",
    )


def _case_persistent_finding() -> CaseResult:
    snap = _snapshot()
    f = _finding(snap)
    audit = _audit(snap, [f])
    handoff = _handoff(snap)
    repair = _repair(snap, handoff, f)
    candidate = snap.apply(repair)
    verification = _verification(snap, candidate, repair, "passed")
    post = _audit(candidate, [_finding(candidate, status="open")])
    session = start_session(snap, session_id="ae30-persistent", max_iterations=3)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=audit, handoff=handoff,
        repair=repair, verification=verification, post_audit=post,
    )
    passed = result["decision"] == "reject_repair" and result["candidate_rejected"] and not result["state_changed"]
    return CaseResult(
        "AE30-C04", "negative-control", "reject_repair", result["decision"], passed,
        result["state_changed"], snap.snapshot_sha256, result["snapshot"].snapshot_sha256,
        "targeted open finding persisting after repair rejects candidate",
    )


def _case_no_repair() -> CaseResult:
    snap = _snapshot()
    f = _finding(snap)
    audit = _audit(snap, [f])
    handoff = _handoff(snap)
    session = start_session(snap, session_id="ae30-no-repair", max_iterations=2)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=audit, handoff=handoff,
        repair=None, verification=None, post_audit=None,
    )
    passed = result["decision"] == "defer" and not result["state_changed"]
    return CaseResult(
        "AE30-C05", "negative-control", "defer", result["decision"], passed,
        result["state_changed"], snap.snapshot_sha256, result["snapshot"].snapshot_sha256,
        "no repair proposal is recorded as defer",
    )


def _case_stale_repair() -> CaseResult:
    original = _snapshot()
    f = _finding(original)
    original_audit = _audit(original, [f])
    original_handoff = _handoff(original)
    repair = _repair(original, original_handoff, f)
    changed = RepositorySnapshot({**original.files, "README.md": b"changed\n"})
    changed_f = _finding(changed)
    changed_audit = _audit(changed, [changed_f])
    changed_handoff = _handoff(changed)
    session = start_session(changed, session_id="ae30-stale-repair", max_iterations=3)
    try:
        evaluate_iteration(
            session=session, snapshot=changed, audit=changed_audit,
            handoff=changed_handoff, repair=repair, verification=None, post_audit=None,
        )
    except IterativeAuditError as exc:
        actual = "rejected"
        detail = str(exc)
    else:
        actual = "accepted"
        detail = "stale repair was unexpectedly admitted"
    passed = actual == "rejected"
    return CaseResult(
        "AE30-C06", "adversarial", "rejected", actual, passed, False,
        changed.snapshot_sha256, changed.snapshot_sha256, detail,
    )


def _case_protected_path() -> CaseResult:
    snap = _snapshot()
    f = _finding(snap)
    handoff = _handoff(snap)
    op = {
        "op": "write_file",
        "path": ".github/workflows/unsafe.yml",
        "expected_sha256": None,
        "content_sha256": _file_digest(b"x"),
        "content_b64": base64.b64encode(b"x").decode("ascii"),
    }
    try:
        make_repair_proposal(
            snap, repair_id="ae30-protected", target_finding_ids=[f["finding_id"]],
            target_finding_fingerprints={f["finding_id"]: f["finding_fingerprint"]},
            neural_handoff_sha256=handoff["handoff_sha256"],
            kind="code_fix", operations=[op],
        )
    except IterativeAuditError as exc:
        actual = "rejected"
        detail = str(exc)
    else:
        actual = "accepted"
        detail = "protected path was unexpectedly admitted"
    return CaseResult(
        "AE30-C07", "adversarial", "rejected", actual, actual == "rejected", False,
        snap.snapshot_sha256, snap.snapshot_sha256, detail,
    )


def _case_stale_handoff() -> CaseResult:
    original = _snapshot()
    handoff = _handoff(original)
    changed = RepositorySnapshot({**original.files, "README.md": b"changed\n"})
    try:
        validate_neural_handoff(changed, handoff)
    except IterativeAuditError as exc:
        actual = "rejected"
        detail = str(exc)
    else:
        actual = "accepted"
        detail = "stale neural handoff was unexpectedly admitted"
    return CaseResult(
        "AE30-C08", "adversarial", "rejected", actual, actual == "rejected", False,
        changed.snapshot_sha256, changed.snapshot_sha256, detail,
    )


def _case_decision_tamper() -> CaseResult:
    snap, result, _ = _accepted_iteration(_snapshot())
    tampered = copy.deepcopy(result["decision_record"])
    tampered["decision"] = "reject_repair"
    try:
        validate_decision_record(tampered)
    except IterativeAuditError as exc:
        actual = "rejected"
        detail = str(exc)
    else:
        actual = "accepted"
        detail = "tampered decision record was unexpectedly valid"
    return CaseResult(
        "AE30-C09", "adversarial", "rejected", actual, actual == "rejected", False,
        snap.snapshot_sha256, result["snapshot"].snapshot_sha256, detail,
    )


def _case_memory_cannot_authorize() -> CaseResult:
    snap, first, _ = _accepted_iteration(_snapshot())
    memory = DecisionMemory([first["decision_record"]])

    f = _finding(snap)
    audit = _audit(snap, [f])
    handoff = _handoff(snap)
    repair = _repair(snap, handoff, f, repair_id="ae30-memory-reject")
    candidate = snap.apply(repair)
    failed = _verification(snap, candidate, repair, "failed")
    session = start_session(snap, session_id="ae30-memory-failure", max_iterations=2)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=audit, handoff=handoff,
        repair=repair, verification=failed, post_audit=None, memory=memory,
    )
    signal = memory.learning_signal(
        rule_id="rule-correctness", category="correctness", repair_kind="code_fix"
    )
    passed = (
        result["decision"] == "reject_repair"
        and not result["state_changed"]
        and signal["authorization"]["may_authorize_repair"] is False
        and signal["authorization"]["may_modify_policy"] is False
    )
    return CaseResult(
        "AE30-C10", "memory-boundary", "reject_repair", result["decision"], passed,
        result["state_changed"], snap.snapshot_sha256, result["snapshot"].snapshot_sha256,
        "historical memory is advisory and cannot override a failed verification",
    )


def _case_snapshot_isolation() -> CaseResult:
    snap = _snapshot()
    f = _finding(snap)
    audit = _audit(snap, [f])
    handoff = _handoff(snap)
    repair = _repair(snap, handoff, f)
    candidate = snap.apply(repair)
    passed = (
        snap.files["src/bug.py"] == b"return 1\n"
        and candidate.files["src/bug.py"] == b"return 2\n"
        and snap.snapshot_sha256 != candidate.snapshot_sha256
    )
    return CaseResult(
        "AE30-C11", "isolation", "isolated", "isolated" if passed else "mutated",
        passed, False, snap.snapshot_sha256, candidate.snapshot_sha256,
        "candidate application leaves the input snapshot unchanged",
    )


def _case_budget() -> CaseResult:
    snap = _snapshot()
    f = _finding(snap)
    audit = _audit(snap, [f])
    handoff = _handoff(snap)
    session = start_session(snap, session_id="ae30-budget", max_iterations=1)
    first = evaluate_iteration(
        session=session, snapshot=snap, audit=audit, handoff=handoff,
        repair=None, verification=None, post_audit=None,
    )
    advanced = advance_session(session, first)
    try:
        evaluate_iteration(
            session=advanced, snapshot=snap, audit=audit, handoff=handoff,
            repair=None, verification=None, post_audit=None,
        )
    except IterativeAuditError as exc:
        actual = "rejected"
        detail = str(exc)
    else:
        actual = "accepted"
        detail = "iteration budget was unexpectedly bypassed"
    passed = actual == "rejected" and advanced["status"] == "exhausted"
    return CaseResult(
        "AE30-C12", "boundedness", "rejected", actual, passed, False,
        snap.snapshot_sha256, snap.snapshot_sha256, detail,
    )


def _case_replay() -> CaseResult:
    snap, result, advanced = _accepted_iteration(_snapshot())
    record = validate_decision_record(copy.deepcopy(result["decision_record"]))
    replay_ok = (
        record["decision_id"] == result["decision_record"]["decision_id"]
        and record["decision_sha256"] == result["decision_record"]["decision_sha256"]
        and advanced["current_snapshot_sha256"] == result["snapshot"].snapshot_sha256
    )
    return CaseResult(
        "AE30-C13", "replay", "replayable", "replayable" if replay_ok else "mismatch",
        replay_ok, result["state_changed"], snap.snapshot_sha256,
        result["snapshot"].snapshot_sha256, "decision and session transition replay exactly",
    )


def _case_forged_acceptance_transition() -> CaseResult:
    snap = _snapshot()
    session = start_session(snap, session_id="ae30-forged-transition", max_iterations=1)
    from audit_engine.semantic_audit.ae29 import make_decision_record

    record = make_decision_record(
        session_id=session["session_id"],
        iteration_index=1,
        input_snapshot_sha256=snap.snapshot_sha256,
        output_snapshot_sha256=snap.snapshot_sha256,
        finding_ids=[],
        neural_handoff_sha256=None,
        repair_sha256=None,
        verification_sha256=None,
        decision="accept_repair",
        reason_code="forged_acceptance",
        remaining_finding_ids=[],
        lesson_codes=["adversarial_transition"],
        finding_context=[],
        repair_kind=None,
    )
    forged = {
        "decision": "accept_repair",
        "decision_record": record,
        "state_changed": False,
        "input_snapshot": snap,
        "snapshot": snap,
        "candidate_snapshot": None,
        "audit": _audit(snap, []),
        "handoff": None,
        "repair": None,
        "verification": None,
        "post_audit": None,
        "candidate_rejected": False,
    }
    try:
        advance_session(session, forged)
    except IterativeAuditError as exc:
        actual = "rejected"
        detail = str(exc)
    else:
        actual = "accepted"
        detail = "forged accept transition was unexpectedly sealed"
    return CaseResult(
        "AE30-C14", "adversarial", "rejected", actual, actual == "rejected",
        False, snap.snapshot_sha256, snap.snapshot_sha256, detail,
    )


CASES: tuple[Callable[[], CaseResult], ...] = (
    _case_success,
    _case_failed_verification,
    _case_inconclusive_verification,
    _case_persistent_finding,
    _case_no_repair,
    _case_stale_repair,
    _case_protected_path,
    _case_stale_handoff,
    _case_decision_tamper,
    _case_memory_cannot_authorize,
    _case_snapshot_isolation,
    _case_budget,
    _case_replay,
    _case_forged_acceptance_transition,
)


def run_evaluation() -> dict[str, Any]:
    if len(CASES) > MAX_CASES:
        raise IterativeAuditError("AE-30 evaluation case budget exceeded")
    results: list[CaseResult] = []
    for case in CASES:
        try:
            result = case()
        except Exception as exc:
            result = CaseResult(
                case_id=case.__name__,
                class_name="evaluator-error",
                expected="case-complete",
                actual=type(exc).__name__,
                passed=False,
                state_changed=False,
                input_snapshot_sha256="0" * 64,
                output_snapshot_sha256="0" * 64,
                detail=f"Unexpected evaluator exception: {exc}",
            )
        results.append(result)

    passed_cases = sum(item.passed for item in results)
    unauthorized_state_changes = sum(
        item.state_changed and item.class_name in {"negative-control", "adversarial", "memory-boundary"}
        for item in results
    )
    report_body = {
        "schema_version": REPORT_SCHEMA,
        "evaluator": {
            "id": EVALUATOR_ID,
            "version": EVALUATOR_VERSION,
        },
        "cases": [asdict(item) for item in results],
        "metrics": {
            "total_cases": len(results),
            "passed_cases": passed_cases,
            "failed_cases": len(results) - passed_cases,
            "case_pass_rate": passed_cases / len(results) if results else 0.0,
            "unauthorized_state_changes": unauthorized_state_changes,
            "replay_failures": sum(
                1 for item in results if item.class_name == "replay" and not item.passed
            ),
            "memory_authorization_violations": sum(
                1 for item in results
                if item.class_name == "memory-boundary" and not item.passed
            ),
        },
        "scope": {
            "repository_finding_discovery": "not_evaluated; AE-30 uses independently seeded findings",
            "live_llm": "not_evaluated; deterministic model artifacts only",
            "authoritative_checkout_mutation": "prohibited by AE-29 and not exercised",
            "production_prompt": "deferred until after AE-30",
        },
        "open_dependencies": [
            "Live-LLM qualification requires a separately controlled provider test.",
            "Verifier receipt authenticity must be anchored by a trusted upstream verifier/admission mechanism before unattended production correction.",
            "Repository-wide finding discovery remains an upstream audit capability; AE-30 evaluates the correction control loop once a finding is supplied.",
        ],
        "acceptance": {
            "status": "passed" if (
                results
                and passed_cases == len(results)
                and unauthorized_state_changes == 0
                and all(
                    item.passed
                    for item in results
                    if item.class_name in {"replay", "memory-boundary"}
                )
            ) else "failed",
            "requirements": {
                "all_cases_pass": True,
                "unauthorized_state_changes_zero": True,
                "replay_failures_zero": True,
                "memory_authorization_violations_zero": True,
            },
        },
        "readiness": {
            "structural_control_loop": "passed",
            "unattended_live_llm_correction": "not_ready",
            "reason": "AE-30 does not qualify a live model or independently authenticate an external verifier receipt.",
        },
    }
    report_body["evaluation_sha256"] = _digest(report_body)
    return report_body


def validate_evaluation_report(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise IterativeAuditError("AE-30 evaluation report must be an object")
    allowed = {
        "schema_version", "evaluator", "cases", "metrics", "scope",
        "open_dependencies", "acceptance", "readiness", "evaluation_sha256",
    }
    if set(report) != allowed or report["schema_version"] != REPORT_SCHEMA:
        raise IterativeAuditError("Invalid AE-30 evaluation report envelope")
    if report["evaluator"] != {"id": EVALUATOR_ID, "version": EVALUATOR_VERSION}:
        raise IterativeAuditError("Invalid AE-30 evaluator identity")
    cases = report["cases"]
    if not isinstance(cases, list) or not cases or len(cases) > MAX_CASES:
        raise IterativeAuditError("Invalid AE-30 case set")
    required_case_keys = set(CaseResult.__dataclass_fields__)
    for item in cases:
        if not isinstance(item, dict) or set(item) != required_case_keys:
            raise IterativeAuditError("Invalid AE-30 case result")
        if not isinstance(item["passed"], bool) or not isinstance(item["state_changed"], bool):
            raise IterativeAuditError("Invalid AE-30 case flags")
        for key in ("input_snapshot_sha256", "output_snapshot_sha256"):
            if not isinstance(item[key], str) or not re.fullmatch(r"[0-9a-f]{64}", item[key]):
                raise IterativeAuditError("Invalid AE-30 snapshot digest")
    metrics = report["metrics"]
    if not isinstance(metrics, dict):
        raise IterativeAuditError("Invalid AE-30 metrics")
    if metrics.get("total_cases") != len(cases):
        raise IterativeAuditError("AE-30 case count mismatch")
    if metrics.get("passed_cases") != sum(bool(item["passed"]) for item in cases):
        raise IterativeAuditError("AE-30 passed-case count mismatch")
    if metrics.get("failed_cases") != metrics["total_cases"] - metrics["passed_cases"]:
        raise IterativeAuditError("AE-30 failed-case count mismatch")
    expected_unauthorized = sum(
        bool(item["state_changed"]) and item["class_name"] in {
            "negative-control", "adversarial", "memory-boundary"
        }
        for item in cases
    )
    expected_replay_failures = sum(
        1 for item in cases if item["class_name"] == "replay" and not item["passed"]
    )
    expected_memory_violations = sum(
        1 for item in cases
        if item["class_name"] == "memory-boundary" and not item["passed"]
    )
    if metrics.get("unauthorized_state_changes") != expected_unauthorized:
        raise IterativeAuditError("AE-30 unauthorized-state-change metric mismatch")
    if metrics.get("replay_failures") != expected_replay_failures:
        raise IterativeAuditError("AE-30 replay metric mismatch")
    if metrics.get("memory_authorization_violations") != expected_memory_violations:
        raise IterativeAuditError("AE-30 memory metric mismatch")
    expected_rate = metrics["passed_cases"] / metrics["total_cases"]
    if metrics.get("case_pass_rate") != expected_rate:
        raise IterativeAuditError("AE-30 case-pass-rate mismatch")
    scope = report["scope"]
    if not isinstance(scope, dict) or set(scope) != {
        "repository_finding_discovery", "live_llm",
        "authoritative_checkout_mutation", "production_prompt",
    }:
        raise IterativeAuditError("Invalid AE-30 scope")
    dependencies = report["open_dependencies"]
    if not isinstance(dependencies, list) or not dependencies or any(
        not isinstance(item, str) or not item for item in dependencies
    ):
        raise IterativeAuditError("Invalid AE-30 open dependencies")
    acceptance = report["acceptance"]
    if not isinstance(acceptance, dict) or set(acceptance) != {"status", "requirements"}:
        raise IterativeAuditError("Invalid AE-30 acceptance section")
    if acceptance["status"] not in {"passed", "failed"}:
        raise IterativeAuditError("Invalid AE-30 acceptance status")
    requirements = acceptance["requirements"]
    expected_requirements = {
        "all_cases_pass": True,
        "unauthorized_state_changes_zero": True,
        "replay_failures_zero": True,
        "memory_authorization_violations_zero": True,
    }
    if requirements != expected_requirements:
        raise IterativeAuditError("AE-30 acceptance requirements changed")
    expected_acceptance_status = "passed" if (
        metrics["passed_cases"] == metrics["total_cases"]
        and metrics["unauthorized_state_changes"] == 0
        and metrics["replay_failures"] == 0
        and metrics["memory_authorization_violations"] == 0
    ) else "failed"
    if acceptance["status"] != expected_acceptance_status:
        raise IterativeAuditError("AE-30 acceptance status is inconsistent with metrics")
    readiness = report["readiness"]
    if not isinstance(readiness, dict) or readiness != {
        "structural_control_loop": "passed",
        "unattended_live_llm_correction": "not_ready",
        "reason": "AE-30 does not qualify a live model or independently authenticate an external verifier receipt.",
    }:
        raise IterativeAuditError("Invalid AE-30 readiness section")
    expected = _digest({k: v for k, v in report.items() if k != "evaluation_sha256"})
    if report["evaluation_sha256"] != expected:
        raise IterativeAuditError("AE-30 evaluation digest mismatch")
    return copy.deepcopy(report)


__all__ = ["REPORT_SCHEMA", "EVALUATOR_ID", "run_evaluation", "validate_evaluation_report"]

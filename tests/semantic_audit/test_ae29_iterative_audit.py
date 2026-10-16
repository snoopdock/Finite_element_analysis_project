"""G9.31 / AE-29 bounded iterative repository audit and self-correction tests.

These tests use synthetic repository snapshots and deterministic verifier
receipts. No shell, network, source-program execution, or live LLM is invoked.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae24.contracts import canonical, sha, admit, SCHEMA as C_SCHEMA
from audit_engine.semantic_audit.ae26.semantics import snapshot as semantic_snapshot
from audit_engine.semantic_audit.ae28.adapter import make_request, ingest_model_response
from audit_engine.semantic_audit.ae29 import (
    IterativeAuditError,
    RepositorySnapshot,
    DecisionMemory,
    make_finding,
    AE29_REPOSITORY_MANIFEST_ID,
    validate_finding,
    make_audit_report,
    validate_audit_report,
    make_neural_handoff,
    bind_ae28_interpretation,
    validate_neural_handoff,
    make_repair_proposal,
    validate_repair,
    make_verification,
    validate_verification,
    make_decision_record,
    validate_decision_record,
    start_session,
    evaluate_iteration,
    advance_session,
    materialize_accepted_snapshot,
)


def digest(value: object) -> str:
    return sha(canonical(value))


def base_snapshot() -> RepositorySnapshot:
    return RepositorySnapshot({
        "src/a.py": b"return 1\n",
        "tests/test_a.py": b"assert True\n",
        "README.md": b"repo\n",
    })


def finding(snapshot: RepositorySnapshot, fid: str = "finding-1", status: str = "open"):
    return make_finding(
        snapshot,
        finding_id=fid,
        rule_id="rule-code-integrity",
        category="correctness",
        severity="high",
        title="Incorrect return value",
        message="The implementation returns an incorrect value.",
        evidence_paths=("src/a.py",),
        status=status,
    )


def audit(snapshot: RepositorySnapshot, findings=None):
    return make_audit_report(
        snapshot,
        [] if findings is None else findings,
        auditor_id="reference-auditor",
        auditor_version="1",
        run_sha256="1" * 64,
    )


def handoff(snapshot: RepositorySnapshot):
    return make_neural_handoff(
        snapshot,
        interpretation_sha256="2" * 64,
        request_sha256="3" * 64,
        candidate_ids=["candidate-1"],
    )


def repair(snapshot: RepositorySnapshot, h=None, fid="finding-1", content=b"return 2\n"):
    h = handoff(snapshot) if h is None else h
    op = {
        "op": "write_file",
        "path": "src/a.py",
        "expected_sha256": hashlib.sha256(snapshot.files["src/a.py"]).hexdigest(),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "content_b64": __import__("base64").b64encode(content).decode("ascii"),
    }
    return make_repair_proposal(
        snapshot,
        repair_id="repair-1",
        target_finding_ids=[fid],
        target_finding_fingerprints={
            fid: finding(snapshot, fid)["finding_fingerprint"],
        },
        neural_handoff_sha256=h["handoff_sha256"],
        kind="code_fix",
        operations=[op],
        reason_codes=["fix_return_value"],
    )


def verification(before, after, r, status="passed"):
    return make_verification(
        before,
        after,
        r,
        verifier_id="reference-verifier",
        verifier_version="1",
        run_sha256="4" * 64,
        status=status,
        checks=[
            {"id": "syntax", "status": "passed" if status == "passed" else "failed",
             "detail_sha256": "5" * 64}
        ],
    )


def test_snapshot_is_order_independent_and_content_bound():
    a = RepositorySnapshot({"b": b"2", "a": b"1"})
    b = RepositorySnapshot({"a": b"1", "b": b"2"})
    assert a.snapshot_sha256 == b.snapshot_sha256
    assert a.manifest == b.manifest


def test_snapshot_rejects_traversal_and_size():
    with pytest.raises(IterativeAuditError, match="path"):
        RepositorySnapshot({"../x": b"x"})
    with pytest.raises(IterativeAuditError, match="path"):
        RepositorySnapshot({r"src\\x": b"x"})
    with pytest.raises(IterativeAuditError, match="byte budget"):
        RepositorySnapshot({"x": b"x" * 2_000_001})


def test_snapshot_payload_exact_replay():
    snap = base_snapshot()
    payload = snap.to_payload(include_bytes=True)
    restored = RepositorySnapshot.from_payload(payload)
    assert restored.snapshot_sha256 == snap.snapshot_sha256
    assert dict(restored.files) == dict(snap.files)


def test_finding_is_bound_to_snapshot_and_evidence_bytes():
    snap = base_snapshot()
    f = finding(snap)
    assert validate_finding(snap, f)["finding_id"] == "finding-1"
    changed = RepositorySnapshot({**snap.files, "src/a.py": b"return 9\n"})
    with pytest.raises(IterativeAuditError, match="stale"):
        validate_finding(changed, f)


def test_audit_report_is_replayable():
    snap = base_snapshot()
    report = audit(snap, [finding(snap)])
    assert validate_audit_report(snap, report)["audit_sha256"] == report["audit_sha256"]


def test_audit_report_rejects_tampering():
    snap = base_snapshot()
    report = audit(snap, [finding(snap)])
    tampered = copy.deepcopy(report)
    tampered["findings"][0]["message"] = "changed"
    with pytest.raises(IterativeAuditError, match="digest"):
        validate_audit_report(snap, tampered)


def test_neural_handoff_is_candidate_only_and_snapshot_bound():
    snap = base_snapshot()
    h = handoff(snap)
    assert validate_neural_handoff(snap, h)["authority"]["candidate_only"] is True
    assert not h["authority"]["automatic_repository_mutation_permitted"]
    changed = RepositorySnapshot({**snap.files, "README.md": b"changed\n"})
    with pytest.raises(IterativeAuditError, match="stale"):
        validate_neural_handoff(changed, h)


def test_neural_handoff_rejects_authority_claim():
    snap = base_snapshot()
    h = handoff(snap)
    h["authority"]["automatic_repository_mutation_permitted"] = True
    h["handoff_sha256"] = digest({k: v for k, v in h.items() if k != "handoff_sha256"})
    with pytest.raises(IterativeAuditError, match="authority"):
        validate_neural_handoff(snap, h)


def test_ae28_interpretation_can_be_bound_to_current_repository_snapshot():
    snap = base_snapshot()
    raw_sources = {
        "design": b"design-v1",
        "observed": b"observed-v1",
    }
    contract = {
        "schema_version": C_SCHEMA,
        "namespace": "portable/ae29-integration",
        "sources": [
            {"id": key, "sha256": hashlib.sha256(value).hexdigest()}
            for key, value in raw_sources.items()
        ],
        "entities": [
            {"id": "system", "kind": "Component", "source_id": "design"},
            {"id": "publish", "kind": "Action", "source_id": "design"},
        ],
        "assertions": [{
            "id": "observed_action", "subject": "system", "predicate": "PERFORMS",
            "object": "publish", "origin": "observed", "source_id": "observed",
        }],
    }
    request = make_request(
        contract, raw_sources,
        request_id="ae29-request",
        context_occurrences=["observed_action"],
        task_digest="9" * 64,
        input_manifest=[{
            "id": AE29_REPOSITORY_MANIFEST_ID,
            "sha256": snap.snapshot_sha256,
        }],
    )
    semantic = semantic_snapshot(contract, raw_sources)
    raw_model = b'{"candidate":"publish"}'
    context_digest = digest({
        "graph_fingerprint": admit(contract, raw_sources).graph_digest,
        "semantic_fingerprint": semantic.semantic_fingerprint,
        "context_occurrences": ["observed_action"],
    })
    response = {
        "schema_version": "ae28/neural-model-response/v1",
        "request_sha256": request["request_sha256"],
        "proposal_id": "proposal-ae29",
        "model": {
            "adapter_id": "reference-adapter",
            "model_family": "reference-model",
            "model_version": "1",
            "context_sha256": context_digest,
        },
        "model_trace": {
            "adapter_id": "reference-adapter",
            "model_family": "reference-model",
            "model_version": "1",
            "raw_output_sha256": hashlib.sha256(raw_model).hexdigest(),
            "generation_config_sha256": "a" * 64,
        },
        "candidate_assertions": [{
            "id": "candidate-ae29",
            "subject": "system",
            "predicate": "PERFORMS",
            "object": "publish",
            "origin": "candidate",
            "source_id": "observed",
        }],
        "evidence_links": [{
            "candidate_occurrence_id": "candidate-ae29",
            "evidence_occurrence_id": "observed_action",
            "kind": "supports",
        }],
    }
    response["response_sha256"] = digest(response)
    interpretation = ingest_model_response(
        contract, raw_sources, request, raw_model, response
    )
    h = bind_ae28_interpretation(
        snap,
        contract=contract,
        sources=raw_sources,
        request=request,
        raw_output=raw_model,
        response=response,
        interpretation=interpretation,
    )
    assert h["repository_snapshot_sha256"] == snap.snapshot_sha256
    assert h["interpretation_sha256"] == interpretation["interpretation_sha256"]
    assert h["candidate_ids"] == ["candidate-ae29"]


def test_ae28_handoff_rejects_repository_snapshot_drift():
    snap = base_snapshot()
    h = handoff(snap)
    changed = RepositorySnapshot({**snap.files, "README.md": b"changed"})
    with pytest.raises(IterativeAuditError, match="stale"):
        validate_neural_handoff(changed, h)


def test_repair_is_canonical_and_snapshot_bound():
    snap = base_snapshot()
    r = repair(snap)
    assert validate_repair(snap, r)["repair_sha256"] == r["repair_sha256"]
    changed = RepositorySnapshot({**snap.files, "README.md": b"x"})
    with pytest.raises(IterativeAuditError, match="stale"):
        validate_repair(changed, r)


def test_repair_rejects_guardrail_paths():
    snap = base_snapshot()
    h = handoff(snap)
    op = {
        "op": "write_file", "path": ".github/workflows/x.yml",
        "expected_sha256": None, "content_sha256": "6" * 64, "content_b64": "eA==",
    }
    with pytest.raises(IterativeAuditError, match="protected"):
        make_repair_proposal(
            snap, repair_id="r", target_finding_ids=["finding-1"],
            target_finding_fingerprints={"finding-1": "0" * 64},
            neural_handoff_sha256=h["handoff_sha256"], kind="code_fix",
            operations=[op],
        )


def test_repair_expected_digest_prevents_stale_write():
    snap = base_snapshot()
    r = repair(snap)
    changed = RepositorySnapshot({**snap.files, "src/a.py": b"return 8\n"})
    with pytest.raises(IterativeAuditError, match="stale"):
        validate_repair(changed, r)


def test_repair_application_does_not_mutate_original():
    snap = base_snapshot()
    r = repair(snap)
    candidate = snap.apply(r)
    assert snap.files["src/a.py"] == b"return 1\n"
    assert candidate.files["src/a.py"] == b"return 2\n"
    assert candidate.snapshot_sha256 != snap.snapshot_sha256


def test_repair_creation_and_delete_are_bounded():
    snap = base_snapshot()
    h = handoff(snap)
    import base64
    content = b"new\n"
    ops = [
        {"op": "delete_file", "path": "README.md",
         "expected_sha256": hashlib.sha256(snap.files["README.md"]).hexdigest()},
        {"op": "write_file", "path": "src/new.py", "expected_sha256": None,
         "content_sha256": hashlib.sha256(content).hexdigest(),
         "content_b64": base64.b64encode(content).decode()},
    ]
    r = make_repair_proposal(
        snap, repair_id="repair-2", target_finding_ids=["finding-1"],
        target_finding_fingerprints={"finding-1": "0" * 64},
        neural_handoff_sha256=h["handoff_sha256"], kind="code_fix",
        operations=ops,
    )
    candidate = snap.apply(r)
    assert "README.md" not in candidate.files
    assert candidate.files["src/new.py"] == content


def test_repair_target_fingerprint_prevents_finding_identity_reuse():
    snap = base_snapshot()
    f = finding(snap)
    h = handoff(snap)
    r = repair(snap, h)
    tampered = copy.deepcopy(r)
    tampered["target_finding_fingerprints"][0]["finding_fingerprint"] = "0" * 64
    tampered["repair_sha256"] = digest({k: v for k, v in tampered.items() if k != "repair_sha256"})
    with pytest.raises(IterativeAuditError, match="fingerprint"):
        validate_repair(
            snap,
            tampered,
            finding_ids=[f["finding_id"]],
            finding_fingerprints={f["finding_id"]: f["finding_fingerprint"]},
        )


def test_verification_must_bind_to_exact_before_after_and_repair():
    snap = base_snapshot()
    r = repair(snap)
    after = snap.apply(r)
    v = verification(snap, after, r)
    assert validate_verification(snap, after, r, v)["status"] == "passed"
    tampered = copy.deepcopy(v)
    tampered["output_snapshot_sha256"] = snap.snapshot_sha256
    tampered["verification_sha256"] = digest({k: x for k, x in tampered.items() if k != "verification_sha256"})
    with pytest.raises(IterativeAuditError, match="output snapshot"):
        validate_verification(snap, after, r, tampered)


def test_passed_verification_requires_all_checks_passed():
    snap = base_snapshot()
    r = repair(snap)
    after = snap.apply(r)
    with pytest.raises(IterativeAuditError, match="non-passed"):
        make_verification(
            snap, after, r,
            verifier_id="v", verifier_version="1", run_sha256="7" * 64,
            status="passed",
            checks=[{"id": "x", "status": "failed", "detail_sha256": "8" * 64}],
        )


def test_failed_verification_does_not_change_state():
    snap = base_snapshot()
    f = finding(snap)
    a = audit(snap, [f])
    h = handoff(snap)
    r = repair(snap, h)
    candidate = snap.apply(r)
    v = verification(snap, candidate, r, "failed")
    session = start_session(snap, session_id="session-1", max_iterations=3)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=a, handoff=h, repair=r,
        verification=v, post_audit=None,
    )
    assert result["decision"] == "reject_repair"
    assert result["snapshot"].snapshot_sha256 == snap.snapshot_sha256
    assert not result["state_changed"]


def test_passed_verification_requires_post_audit():
    snap = base_snapshot()
    f = finding(snap)
    a = audit(snap, [f])
    h = handoff(snap)
    r = repair(snap, h)
    candidate = snap.apply(r)
    v = verification(snap, candidate, r)
    session = start_session(snap, session_id="session-2", max_iterations=3)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=a, handoff=h, repair=r,
        verification=v, post_audit=None,
    )
    assert result["decision"] == "await_post_audit"
    assert result["snapshot"].snapshot_sha256 == snap.snapshot_sha256
    assert result["candidate_snapshot"].snapshot_sha256 == candidate.snapshot_sha256


def test_persistent_target_finding_rejects_repair_after_post_audit():
    snap = base_snapshot()
    f = finding(snap)
    a = audit(snap, [f])
    h = handoff(snap)
    r = repair(snap, h)
    candidate = snap.apply(r)
    v = verification(snap, candidate, r)
    persistent = finding(candidate)
    post = audit(candidate, [persistent])
    session = start_session(snap, session_id="session-3", max_iterations=3)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=a, handoff=h, repair=r,
        verification=v, post_audit=post,
    )
    assert result["decision"] == "reject_repair"
    assert result["candidate_rejected"] is True
    assert result["snapshot"].snapshot_sha256 == snap.snapshot_sha256


def test_successful_repair_changes_only_controller_state_after_post_audit():
    snap = base_snapshot()
    f = finding(snap)
    a = audit(snap, [f])
    h = handoff(snap)
    r = repair(snap, h)
    candidate = snap.apply(r)
    v = verification(snap, candidate, r)
    resolved = finding(candidate, status="resolved")
    post = audit(candidate, [resolved])
    session = start_session(snap, session_id="session-4", max_iterations=3)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=a, handoff=h, repair=r,
        verification=v, post_audit=post,
    )
    assert result["decision"] == "accept_repair"
    assert result["state_changed"] is True
    assert result["snapshot"].files["src/a.py"] == b"return 2\n"
    assert snap.files["src/a.py"] == b"return 1\n"
    assert result["decision_record"]["output_snapshot_sha256"] == candidate.snapshot_sha256


def test_additional_findings_can_remain_after_target_is_resolved():
    snap = base_snapshot()
    f = finding(snap)
    a = audit(snap, [f])
    h = handoff(snap)
    r = repair(snap, h)
    candidate = snap.apply(r)
    v = verification(snap, candidate, r)
    resolved = finding(candidate, status="resolved")
    other = make_finding(
        candidate, finding_id="finding-2", rule_id="rule-other",
        category="maintainability", severity="low", title="Other issue",
        message="Another issue remains.", evidence_paths=("README.md",), status="open",
    )
    post = audit(candidate, [resolved, other])
    session = start_session(snap, session_id="session-5", max_iterations=3)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=a, handoff=h, repair=r,
        verification=v, post_audit=post,
    )
    assert result["decision"] == "accept_repair"
    assert result["decision_record"]["remaining_finding_ids"] == ["finding-2"]


def test_no_repair_is_recorded_as_defer():
    snap = base_snapshot()
    f = finding(snap)
    a = audit(snap, [f])
    h = handoff(snap)
    session = start_session(snap, session_id="session-6", max_iterations=2)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=a, handoff=h, repair=None,
        verification=None, post_audit=None,
    )
    assert result["decision"] == "defer"
    assert result["decision_record"]["repair_sha256"] is None


def test_decision_record_is_tamper_evident():
    record = make_decision_record(
        session_id="s", iteration_index=1,
        input_snapshot_sha256="1"*64, output_snapshot_sha256="1"*64,
        finding_ids=["f"], neural_handoff_sha256="2"*64,
        repair_sha256=None, verification_sha256=None,
        decision="defer", reason_code="no_repair_proposed",
        remaining_finding_ids=["f"], lesson_codes=["no_repair_proposed"],
        finding_context=[{"rule_id":"rule-x","category":"correctness"}],
        repair_kind=None,
    )
    assert validate_decision_record(record)["decision_id"] == record["decision_id"]
    tampered = copy.deepcopy(record)
    tampered["decision"] = "accept_repair"
    with pytest.raises(IterativeAuditError, match="(identity|digest)"):
        validate_decision_record(tampered)


def test_decision_memory_is_deterministic_and_non_authoritative():
    snap = base_snapshot()
    f = finding(snap)
    a = audit(snap, [f])
    h = handoff(snap)
    r = repair(snap, h)
    candidate = snap.apply(r)
    v = verification(snap, candidate, r)
    post = audit(candidate, [finding(candidate, status="resolved")])
    session = start_session(snap, session_id="session-7", max_iterations=3)
    memory = DecisionMemory()
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=a, handoff=h, repair=r,
        verification=v, post_audit=post, memory=memory,
    )
    assert len(memory.records) == 1
    signal = memory.learning_signal(
        rule_id="rule-code-integrity", category="correctness", repair_kind="code_fix"
    )
    assert signal["accepted_repairs"] == 1
    assert signal["authorization"]["may_authorize_repair"] is False


def test_decision_memory_rejects_tampering_and_duplicates():
    record = make_decision_record(
        session_id="s", iteration_index=1,
        input_snapshot_sha256="1"*64, output_snapshot_sha256="1"*64,
        finding_ids=["f"], neural_handoff_sha256="2"*64,
        repair_sha256=None, verification_sha256=None,
        decision="defer", reason_code="no_repair_proposed",
        remaining_finding_ids=["f"], lesson_codes=["no_repair_proposed"],
        finding_context=[{"rule_id":"rule-x","category":"correctness"}],
    )
    memory = DecisionMemory([record])
    with pytest.raises(IterativeAuditError, match="Duplicate"):
        memory.add(record)


def test_session_advances_only_with_next_decision_and_state():
    snap = base_snapshot()
    f = finding(snap)
    a = audit(snap, [f])
    h = handoff(snap)
    r = repair(snap, h)
    candidate = snap.apply(r)
    v = verification(snap, candidate, r)
    post = audit(candidate, [finding(candidate, status="resolved")])
    session = start_session(snap, session_id="session-8", max_iterations=2)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=a, handoff=h, repair=r,
        verification=v, post_audit=post,
    )
    advanced = advance_session(session, result)
    assert advanced["iteration_index"] == 1
    assert advanced["current_snapshot_sha256"] == candidate.snapshot_sha256
    assert advanced["status"] == "complete"


def test_session_rejects_stale_snapshot_for_iteration():
    snap = base_snapshot()
    session = start_session(snap, session_id="session-9", max_iterations=2)
    changed = RepositorySnapshot({**snap.files, "README.md": b"changed"})
    with pytest.raises(IterativeAuditError, match="stale"):
        evaluate_iteration(
            session=session, snapshot=changed,
            audit=audit(changed, []), handoff=handoff(changed),
            repair=None, verification=None, post_audit=None,
        )


def test_iteration_budget_is_hard():
    snap = base_snapshot()
    session = start_session(snap, session_id="session-10", max_iterations=1)
    f = finding(snap)
    a = audit(snap, [f])
    h = handoff(snap)
    result = evaluate_iteration(
        session=session, snapshot=snap, audit=a, handoff=h,
        repair=None, verification=None, post_audit=None,
    )
    advanced = advance_session(session, result)
    with pytest.raises(IterativeAuditError, match="budget"):
        evaluate_iteration(
            session=advanced, snapshot=snap, audit=a, handoff=h,
            repair=None, verification=None, post_audit=None,
        )


def test_materialization_creates_separate_candidate_workspace(tmp_path):
    snap = base_snapshot()
    destination = tmp_path / "candidate"
    path = materialize_accepted_snapshot(snap, destination)
    assert path == destination
    assert (destination / "src/a.py").read_bytes() == b"return 1\n"
    assert not (tmp_path / "candidate" / ".git").exists()


def test_materialization_refuses_existing_destination(tmp_path):
    snap = base_snapshot()
    destination = tmp_path / "candidate"
    destination.mkdir()
    with pytest.raises(IterativeAuditError, match="must not already exist"):
        materialize_accepted_snapshot(snap, destination)

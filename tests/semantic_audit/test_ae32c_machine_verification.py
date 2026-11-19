from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from audit_engine.semantic_audit.ae32c.machine_verification import (
    build_deterministic_follow_up_plan,
    build_machine_verification_assessment,
)


def _read_entry(root: Path, *, evidence_id: str = "E0002", path: str = "src/module.py"):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = b"def run():\n    return 7\n"
    target.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    entry = SimpleNamespace(
        evidence_id=evidence_id,
        tool="read_source_file",
        status="ok",
        response={"result": {
            "path": path,
            "source_sha256": digest,
            "content": "1: def run():\n2:     return 7",
            "content_omitted": False,
        }},
        provenance={},
    )
    reference = {"evidence_id": evidence_id, "path": path, "line": 2, "source_sha256": digest}
    return entry, reference, digest


def _assessment(reference, *, claim_type="static_inference", evidence_ids=None):
    return {"items": [{
        "claim_id": "ROOT-0123456789ab",
        "claim_type": claim_type,
        "evidence_refs": evidence_ids or [reference["evidence_id"]],
        "source_references": [reference],
        "available_uncited_source_candidates": [],
    }]}


def _verify(root, entry, reference, digest, *, claim_type="static_inference", extras=(), evidence_ids=None, snapshot_status="verified"):
    return build_machine_verification_assessment(
        diagnosis={"root_cause": {"statement": "static hypothesis"}},
        claim_assessment=_assessment(reference, claim_type=claim_type, evidence_ids=evidence_ids),
        ledger_entries=[entry, *extras],
        repo_root=root,
        expected_file_hashes={reference["path"]: digest},
        expected_manifest_sha256="a" * 64,
        expected_graph_fingerprint="graph:" + "b" * 24,
        snapshot_status=snapshot_status,
    )


def test_exact_source_line_and_current_hash_are_machine_verified(tmp_path):
    entry, reference, digest = _read_entry(tmp_path)
    result = _verify(tmp_path, entry, reference, digest)
    assert result["status"] == "evidence_integrity_passed"
    assert result["semantic_correctness"] == "not_assessed"
    assert result["human_review_required"] is False
    assert result["accuracy_claim_permitted"] is False
    assert result["items"][0]["source_reference_checks"][0]["status"] == "passed"


def test_changed_source_hash_fails_closed(tmp_path):
    entry, reference, digest = _read_entry(tmp_path)
    (tmp_path / reference["path"]).write_text("def run():\n    return 8\n", encoding="utf-8")
    result = _verify(tmp_path, entry, reference, digest)
    assert result["status"] == "failed"
    assert result["items"][0]["machine_status"] == "evidence_integrity_failed"


def test_graph_provenance_must_match_snapshot_and_graph_fingerprint(tmp_path):
    entry, reference, digest = _read_entry(tmp_path)
    graph = SimpleNamespace(
        evidence_id="E0003", tool="graph_neighbors", status="ok",
        response={"result": {}},
        provenance={"source_manifest_sha256": "a" * 64, "graph_fingerprint": "graph:wrong"},
    )
    result = _verify(tmp_path, entry, reference, digest, extras=(graph,), evidence_ids=["E0002", "E0003"])
    assert result["status"] == "failed"
    assert result["items"][0]["graph_provenance_checks"][0]["status"] == "failed"


def test_runtime_and_causal_claims_are_not_promoted_without_registered_reproduction(tmp_path):
    entry, reference, digest = _read_entry(tmp_path)
    result = _verify(tmp_path, entry, reference, digest, claim_type="causal_hypothesis")
    item = result["items"][0]
    assert item["machine_status"] == "evidence_integrity_passed_semantics_unassessed"
    assert item["runtime_reproduction_status"] == "not_performed_read_only"
    assert result["summary"]["runtime_or_causal_claims_reproduced"] == 0


def test_follow_up_plan_is_stable_inert_and_never_executes_actions(tmp_path):
    entry, reference, digest = _read_entry(tmp_path)
    result = _verify(tmp_path, entry, reference, digest, claim_type="runtime_claim")
    first = build_deterministic_follow_up_plan(result)
    second = build_deterministic_follow_up_plan(result)
    assert first["plan_id"] == second["plan_id"]
    assert first["execution_mode"] == "plan_only"
    assert first["actions_executed"] == 0
    assert first["shell_execution_permitted"] is False
    assert first["repository_code_execution_permitted"] is False
    assert first["source_mutation_permitted"] is False
    assert first["actions"][0]["action_type"] == "run_registered_runtime_witness"
    assert first["actions"][0]["status"] == "blocked_no_registered_harness_binding"


def test_snapshot_not_verified_prevents_overall_pass(tmp_path):
    entry, reference, digest = _read_entry(tmp_path)
    result = _verify(tmp_path, entry, reference, digest, snapshot_status="snapshot_unavailable_or_changed")
    assert result["status"] == "incomplete"

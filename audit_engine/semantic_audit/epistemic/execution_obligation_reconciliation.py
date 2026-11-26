"""M7.5.14 reconciliation of extractor execution with rule obligations and dossiers.

This layer links execution accounting to a specific existing coverage dossier.
It does not reinterpret extractor output as typed semantic evidence and never
changes the underlying epistemic coverage manifest or its status.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from .assurance import AssuranceClaim
from .assurance_store import AssuranceStore
from .coverage import EpistemicCoverageManifest
from .coverage_dossier import CoverageDossierStore, _canonical
from .dossier_verification import verify_coverage_dossier_replay
from .extractor_execution import (
    ExtractorExecutionError, verify_extractor_execution_report,
)
from .rule_coverage import RuleCoveragePlan, verify_rule_derived_manifest
from .source_inventory import verify_source_extractor_inventory
from .store import EpistemicStore


SCHEMA = "ae32c/execution-obligation-reconciliation/v1"


class ExecutionObligationReconciliationError(ValueError):
    """Execution evidence cannot be reconciled to the selected dossier."""


def _digest(value: Any) -> str:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _manifest_dict(manifest: EpistemicCoverageManifest) -> dict[str, Any]:
    data = {
        "manifest_id": manifest.manifest_id,
        "claim_id": manifest.claim_id,
        "proposition_id": manifest.proposition_id,
        "subject_id": manifest.subject_id,
        "scope_id": manifest.scope_id,
        "source_snapshot_id": manifest.source_snapshot_id,
        "registry_id": manifest.registry_id,
        "registry_version": manifest.registry_version,
        "registry_sha256": manifest.registry_sha256,
        "expected_obligation_ids": list(manifest.expected_obligation_ids),
        "obligations": [{
            "obligation_id": x.obligation_id,
            "disposition": x.disposition.value,
            "evidence_ids": list(x.evidence_ids),
            "gap_ids": list(x.gap_ids),
            "limitation": x.limitation,
        } for x in manifest.obligations],
    }
    return data


def _assess_obligation(oid: str, candidates: list[dict], outcomes: dict[str, dict],
                       source_manifest_verified: bool) -> dict[str, Any]:
    parts = oid.split(":")
    if len(parts) < 4 or parts[0] != "rule":
        return {"obligation_id": oid, "kind": "unrecognized",
                "status": "UNKNOWN", "reason": "obligation_identifier_not_recognized",
                "candidate_ids": [], "outcome_ids": []}
    dimension, requirement = parts[-2], ":".join(parts[3:])
    if dimension == "evidence":
        return {"obligation_id": oid, "kind": "typed_evidence",
                "status": "UNKNOWN", "reason": "extractor_output_is_not_typed_semantic_evidence",
                "candidate_ids": [], "outcome_ids": []}
    if dimension != "coverage":
        return {"obligation_id": oid, "kind": dimension,
                "status": "UNKNOWN", "reason": "unsupported_obligation_dimension",
                "candidate_ids": [], "outcome_ids": []}
    if requirement == "source_manifest":
        return {"obligation_id": oid, "kind": "source_manifest",
                "status": "MANIFEST_VERIFIED_WITHIN_DECLARED_INVENTORY" if source_manifest_verified else "UNKNOWN",
                "reason": "verified_snapshot_manifest_and_derived_inventory" if source_manifest_verified else "source_manifest_not_verified",
                "candidate_ids": [], "outcome_ids": []}
    relevant = [x for x in candidates if x.get("extractor_id") == requirement]
    if not relevant:
        return {"obligation_id": oid, "kind": "extractor_coverage",
                "status": "UNKNOWN", "reason": "no_candidates_for_required_extractor",
                "candidate_ids": [], "outcome_ids": []}
    rows = [outcomes.get(x["candidate_id"]) for x in relevant]
    statuses = [x.get("status") if x else "MISSING_OUTCOME" for x in rows]
    ids = [x["candidate_id"] for x in relevant]
    outcome_ids = [x.get("outcome_id") if x else None for x in rows]
    if all(status == "EXECUTED" for status in statuses):
        status = "EXTRACTOR_EXECUTION_COMPLETE"
        reason = "all_declared_candidates_for_extractor_have_EXECUTED_outcomes"
    elif any(status in {"FAILED", "RESOURCE_LIMIT", "UNSUPPORTED_INPUT",
                        "UNSUPPORTED_EXECUTOR", "MISSING_OUTCOME"} for status in statuses):
        status = "INCOMPLETE"
        reason = "one_or_more_required_extractor_candidates_did_not_execute_successfully"
    else:
        status = "INCOMPLETE"
        reason = "one_or_more_required_extractor_candidates_were_explicitly_excluded"
    return {"obligation_id": oid, "kind": "extractor_coverage",
            "status": status, "reason": reason,
            "candidate_ids": ids, "outcome_ids": outcome_ids}


def build_execution_obligation_reconciliation(
    *, dossier_id: str, claim: AssuranceClaim, plan: RuleCoveragePlan,
    manifest: EpistemicCoverageManifest, source_manifest: Mapping[str, Any],
    inventory: Mapping[str, Any], execution_report: Mapping[str, Any],
    repository_root: str | Path, assurance_store: AssuranceStore,
    epistemic_store: EpistemicStore, dossier_store: CoverageDossierStore,
) -> dict[str, Any]:
    """Build a dossier-bound reconciliation without upgrading epistemic coverage."""
    if not isinstance(dossier_id, str) or not dossier_id.strip():
        raise ExecutionObligationReconciliationError("dossier_id_required")
    if not isinstance(claim, AssuranceClaim) or not isinstance(plan, RuleCoveragePlan):
        raise TypeError("claim and plan must use their declared contracts")
    verify_rule_derived_manifest(claim, plan, manifest)
    if source_manifest.get("source_snapshot_id") != plan.source_snapshot_id:
        raise ExecutionObligationReconciliationError("source_snapshot_does_not_match_rule_plan")
    if source_manifest.get("source_snapshot_id") != manifest.source_snapshot_id:
        raise ExecutionObligationReconciliationError("source_snapshot_does_not_match_coverage_manifest")
    try:
        inventory_check = verify_source_extractor_inventory(source_manifest, inventory)
        execution_check = verify_extractor_execution_report(
            source_manifest, inventory, execution_report, repository_root
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ExecutionObligationReconciliationError("upstream_execution_evidence_verification_failed:" + type(exc).__name__) from exc
    if inventory.get("source_snapshot_id") != plan.source_snapshot_id:
        raise ExecutionObligationReconciliationError("inventory_source_snapshot_mismatch")
    if execution_report.get("source_snapshot_id") != plan.source_snapshot_id:
        raise ExecutionObligationReconciliationError("execution_report_source_snapshot_mismatch")

    dossier = dossier_store.get(dossier_id)
    if dossier is None:
        raise ExecutionObligationReconciliationError("coverage_dossier_not_found")
    if dossier.get("claim_id") != claim.claim_id:
        raise ExecutionObligationReconciliationError("coverage_dossier_claim_mismatch")
    dossier_manifest = dossier.get("manifest")
    if not isinstance(dossier_manifest, Mapping) or _canonical(dict(dossier_manifest)) != _canonical(_manifest_dict(manifest)):
        raise ExecutionObligationReconciliationError("coverage_dossier_manifest_mismatch")
    dossier_check = verify_coverage_dossier_replay(
        dossier_id, assurance_store=assurance_store,
        epistemic_store=epistemic_store, dossier_store=dossier_store,
    )
    if not dossier_check.get("semantic_integrity") or not dossier_check.get("source_snapshots_match") or not dossier_check.get("replay_matches"):
        raise ExecutionObligationReconciliationError("coverage_dossier_not_currently_replay_verified")

    candidate_list = inventory.get("extractor_candidates")
    outcome_list = execution_report.get("outcomes")
    if not isinstance(candidate_list, list) or not isinstance(outcome_list, list):
        raise ExecutionObligationReconciliationError("candidate_or_outcome_collection_invalid")
    outcome_map = {x.get("candidate_id"): x for x in outcome_list if isinstance(x, Mapping)}
    if len(outcome_map) != len(outcome_list):
        raise ExecutionObligationReconciliationError("duplicate_or_invalid_outcome_candidate_identity")
    assessments = [
        _assess_obligation(oid, candidate_list, outcome_map, True)
        for oid in plan.expected_obligation_ids
    ]
    execution_complete = all(
        x["status"] in {"EXTRACTOR_EXECUTION_COMPLETE", "MANIFEST_VERIFIED_WITHIN_DECLARED_INVENTORY"}
        for x in assessments if x["kind"] in {"extractor_coverage", "source_manifest"}
    )
    unresolved_semantic = [x["obligation_id"] for x in assessments if x["kind"] == "typed_evidence"]
    payload = {
        "schema": SCHEMA,
        "dossier_id": dossier_id,
        "dossier_sha256": _digest(dossier),
        "claim_id": claim.claim_id,
        "source_snapshot_id": plan.source_snapshot_id,
        "plan_sha256": plan.plan_sha256,
        "coverage_manifest_sha256": manifest.manifest_sha256,
        "source_manifest_sha256": source_manifest.get("manifest_sha256"),
        "inventory_sha256": inventory.get("inventory_sha256"),
        "execution_report_sha256": execution_report.get("report_sha256"),
        "inventory_semantic_integrity": bool(inventory_check.get("semantic_integrity")),
        "execution_semantic_replay": bool(execution_check.get("replay_matches")),
        "dossier_semantic_replay": bool(dossier_check.get("replay_matches")),
        "candidate_count": execution_report.get("candidate_count"),
        "outcome_count": execution_report.get("outcome_count"),
        "execution_status": execution_report.get("execution_status"),
        "obligations": assessments,
        "summary": {
            "obligation_count": len(assessments),
            "extractor_execution_complete_for_declared_coverage": execution_complete,
            "typed_evidence_obligation_count": len(unresolved_semantic),
            "typed_evidence_obligations_remain_unknown": unresolved_semantic,
            "epistemic_coverage_upgraded": False,
            "coverage_dossier_mutated": False,
        },
        "authority": {
            "extractor_execution_reconciled_to_declared_obligations": True,
            "semantic_evidence_sufficiency_established": False,
            "proposition_truth_established": False,
            "graph_completeness_established": False,
            "audit_decision_authority": False,
            "production_approval": False,
        },
    }
    return {**payload, "reconciliation_sha256": _digest(payload)}


class ExecutionObligationReconciliationStore:
    """Independent append-only hash-chained ledger for dossier-linked reconciliations."""
    def __init__(self, database: str | Path, *, max_records: int = 10000):
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records < 1:
            raise ValueError("max_records must be a positive integer")
        self.max_records = max_records
        self._db = sqlite3.connect(str(database))
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS execution_obligation_events (
                sequence INTEGER PRIMARY KEY, reconciliation_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TRIGGER IF NOT EXISTS execution_obligation_no_update
            BEFORE UPDATE ON execution_obligation_events
            BEGIN SELECT RAISE(ABORT, 'execution-obligation ledger is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS execution_obligation_no_delete
            BEFORE DELETE ON execution_obligation_events
            BEGIN SELECT RAISE(ABORT, 'execution-obligation ledger is append-only'); END;
        """)
        self._db.commit()

    def close(self):
        self._db.close()

    def verify_integrity(self) -> bool:
        previous = "0" * 64
        rows = self._db.execute("SELECT * FROM execution_obligation_events ORDER BY sequence").fetchall()
        for expected, row in enumerate(rows, 1):
            digest = hashlib.sha256(row["payload"].encode("utf-8")).hexdigest()
            material = f"{expected}\n{row['reconciliation_id']}\n{digest}\n{previous}"
            calculated = hashlib.sha256(material.encode("utf-8")).hexdigest()
            if (row["sequence"] != expected or row["payload_sha256"] != digest
                    or row["previous_hash"] != previous or row["event_hash"] != calculated):
                return False
            try:
                decoded = json.loads(row["payload"])
                identity = decoded.get("reconciliation_sha256")
                semantic_payload = {k: v for k, v in decoded.items() if k != "reconciliation_sha256"}
                if identity != row["reconciliation_id"] or identity != _digest(semantic_payload):
                    return False
            except (TypeError, ValueError, AttributeError):
                return False
            previous = calculated
        return True

    def record(self, reconciliation: Mapping[str, Any]) -> bool:
        if not isinstance(reconciliation, Mapping):
            raise TypeError("reconciliation must be an object")
        payload = json.dumps(dict(reconciliation), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        rid = str(reconciliation.get("reconciliation_sha256", ""))
        if not rid:
            raise ExecutionObligationReconciliationError("reconciliation_digest_missing")
        calculated = _digest({k: v for k, v in reconciliation.items() if k != "reconciliation_sha256"})
        if calculated != rid:
            raise ExecutionObligationReconciliationError("reconciliation_digest_mismatch")
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            if not self.verify_integrity():
                raise ExecutionObligationReconciliationError("reconciliation_ledger_integrity_failure")
            old = self._db.execute("SELECT payload_sha256 FROM execution_obligation_events WHERE reconciliation_id=?", (rid,)).fetchone()
            if old:
                if old["payload_sha256"] != payload_hash:
                    raise ExecutionObligationReconciliationError("reconciliation_id_conflict")
                return False
            sequence = self._db.execute("SELECT COUNT(*) AS n FROM execution_obligation_events").fetchone()["n"] + 1
            if sequence > self.max_records:
                raise ExecutionObligationReconciliationError("reconciliation_storage_bound_reached")
            row = self._db.execute("SELECT event_hash FROM execution_obligation_events ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = row["event_hash"] if row else "0" * 64
            material = f"{sequence}\n{rid}\n{payload_hash}\n{previous}"
            event_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
            self._db.execute("INSERT INTO execution_obligation_events VALUES (?, ?, ?, ?, ?, ?)",
                             (sequence, rid, payload, payload_hash, previous, event_hash))
        return True

    def get(self, reconciliation_id: str) -> dict[str, Any] | None:
        if not self.verify_integrity():
            raise ExecutionObligationReconciliationError("reconciliation_ledger_integrity_failure")
        row = self._db.execute("SELECT payload FROM execution_obligation_events WHERE reconciliation_id=?", (reconciliation_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def history(self) -> tuple[dict[str, Any], ...]:
        if not self.verify_integrity():
            raise ExecutionObligationReconciliationError("reconciliation_ledger_integrity_failure")
        rows = self._db.execute("SELECT sequence, reconciliation_id, payload, event_hash FROM execution_obligation_events ORDER BY sequence").fetchall()
        return tuple({"sequence": r["sequence"], "reconciliation_id": r["reconciliation_id"],
                      "payload": json.loads(r["payload"]), "event_hash": r["event_hash"]} for r in rows)


def build_and_persist_execution_obligation_reconciliation(
    *, reconciliation_store: ExecutionObligationReconciliationStore, **kwargs,
) -> dict[str, Any]:
    report = build_execution_obligation_reconciliation(**kwargs)
    reconciliation_store.record(report)
    return report


def verify_execution_obligation_reconciliation(
    reconciliation_id: str, *, reconciliation_store: ExecutionObligationReconciliationStore,
    **kwargs,
) -> dict[str, Any]:
    stored = reconciliation_store.get(reconciliation_id)
    if stored is None:
        raise ExecutionObligationReconciliationError("reconciliation_not_found")
    expected = build_execution_obligation_reconciliation(**kwargs)
    if _canonical(stored) != _canonical(expected) or reconciliation_id != expected.get("reconciliation_sha256"):
        raise ExecutionObligationReconciliationError("reconciliation_semantic_replay_mismatch")
    return {"reconciliation_sha256": reconciliation_id, "ledger_integrity": True,
            "semantic_replay": True, "dossier_unchanged": True,
            "obligation_count": len(expected["obligations"]),
            "epistemic_coverage_upgraded": False}

"""M7.5.15 typed structural evidence observations and obligation binding.

Observations are source-bound records, not truth assertions. This module
intentionally supports only narrowly verifiable extractor facts; unsupported
semantic evidence kinds remain explicit and unresolved.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from audit_engine.semantic_audit.ae32c.rule_contracts import resolve_rule, rule_registry
from .assurance import AssuranceClaim
from .coverage import EpistemicCoverageManifest
from .extractor_execution import verify_extractor_execution_report
from .rule_coverage import RuleCoveragePlan, verify_rule_derived_manifest
from .source_inventory import verify_source_extractor_inventory
from .execution_obligation_reconciliation import (
    ExecutionObligationReconciliationStore,
    verify_execution_obligation_reconciliation,
)
from .assurance_store import AssuranceStore
from .coverage_dossier import CoverageDossierStore
from .store import EpistemicStore

SCHEMA = "ae32c/typed-evidence-observation-bundle/v1"
STORE_SCHEMA = "ae32c/typed-evidence-observation-ledger/v1"

# Deliberately narrow allowlist: a match proves an import statement was parsed,
# not that the imported library is used correctly or is reachable at runtime.
_GRAPH_MODULE_ROOTS = frozenset({
    "networkx", "rustworkx", "igraph", "graph_tool", "pygraphviz",
    "graphviz", "rustworkx", "networkit", "nx", "dgl", "torch_geometric",
})

# The registry distinguishes evidence kinds we can currently observe
# mechanically from semantic kinds that require a future domain validator.
_EVIDENCE_PRODUCERS = {
    "graph_import": "python_ast_import_root_v1",
    "python_syntax_error": "python_ast_parse_failure_v1",
    "scope_exclusion": "source_inventory_exclusion_v1",
}
_SUPPORTED_RULES = frozenset(_EVIDENCE_PRODUCERS)


class TypedEvidenceError(ValueError):
    """Typed evidence observation or obligation binding is invalid."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _source_line(root: Path, path: str, line: int) -> tuple[str, str]:
    raw = (root / path).read_bytes()
    lines = raw.splitlines()
    if line < 1 or line > len(lines):
        raise TypedEvidenceError("extractor_line_outside_source:" + path)
    return lines[line - 1].decode("utf-8", errors="replace"), hashlib.sha256(lines[line - 1]).hexdigest()


def _rule_evidence_requirements(plan: RuleCoveragePlan) -> dict[str, list[str]]:
    registry = rule_registry()
    result: dict[str, list[str]] = {}
    for obligation_id in plan.expected_obligation_ids:
        parts = obligation_id.split(":")
        if len(parts) < 4 or parts[0] != "rule" or parts[2] != "evidence":
            continue
        rule_id, evidence_kind = parts[1], ":".join(parts[3:])
        contract = resolve_rule(rule_id, registry)
        if evidence_kind not in contract.get("required_evidence_kinds", []):
            raise TypedEvidenceError("obligation_evidence_kind_not_in_rule_contract:" + obligation_id)
        result.setdefault(evidence_kind, []).append(obligation_id)
    return {key: sorted(value) for key, value in result.items()}


def _observation(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "evidence_observation_id": _digest(payload)}


def derive_typed_evidence_observations(
    *, plan: RuleCoveragePlan, inventory: Mapping[str, Any],
    execution_report: Mapping[str, Any], repository_root: str | Path,
) -> dict[str, Any]:
    """Derive limited structural observations and explicit unresolved obligations.

    No output from this function is an accepted semantic assertion. In
    particular, graph imports do not prove service use, reachability, or absence.
    """
    if not isinstance(plan, RuleCoveragePlan):
        raise TypeError("plan must be a RuleCoveragePlan")
    requirements = _rule_evidence_requirements(plan)
    candidates = inventory.get("extractor_candidates")
    outcomes = execution_report.get("outcomes")
    if not isinstance(candidates, list) or not isinstance(outcomes, list):
        raise TypedEvidenceError("candidate_or_outcome_collection_invalid")
    candidate_by_id = {x.get("candidate_id"): x for x in candidates if isinstance(x, Mapping)}
    outcome_by_id = {x.get("candidate_id"): x for x in outcomes if isinstance(x, Mapping)}
    if len(candidate_by_id) != len(candidates) or len(outcome_by_id) != len(outcomes):
        raise TypedEvidenceError("duplicate_or_invalid_candidate_identity")
    if set(candidate_by_id) != set(outcome_by_id):
        raise TypedEvidenceError("candidate_outcome_identity_set_mismatch")

    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise TypedEvidenceError("repository_root_not_directory")
    observations: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    source_snapshot_id = plan.source_snapshot_id

    def emit(kind: str, rule_obligation_ids: list[str], candidate: Mapping[str, Any],
             outcome: Mapping[str, Any], source_path: str, line: int | None,
             observation_type: str, structural_value: Mapping[str, Any]) -> None:
        source_hash = candidate.get("source_content_sha256") or next(
            (x.get("content_sha256") for x in inventory.get("source_units", [])
             if x.get("path") == source_path), None
        )
        line_hash = None
        if line is not None:
            _, line_hash = _source_line(root, source_path, line)
        payload = {
            "schema": "ae32c/typed-evidence-observation/v1",
            "source_snapshot_id": source_snapshot_id,
            "rule_obligation_ids": sorted(rule_obligation_ids),
            "evidence_kind": kind,
            "producer_id": _EVIDENCE_PRODUCERS[kind],
            "producer_version": "1.0.0",
            "extractor_id": candidate.get("extractor_id"),
            "extractor_version": candidate.get("extractor_version"),
            "candidate_id": candidate.get("candidate_id"),
            "outcome_id": outcome.get("outcome_id"),
            "source_path": source_path,
            "source_content_sha256": source_hash,
            "source_line": line,
            "source_line_sha256": line_hash,
            "observation_type": observation_type,
            "structural_value": dict(structural_value),
            "status": "STRUCTURALLY_OBSERVED",
            "semantic_acceptance": "NOT_ESTABLISHED",
            "limitation": "observation_is_not_a_truth_assertion_or_rule_satisfaction",
        }
        observations.append(_observation(payload))

    # 1. Exact Python import statements for known graph-library module roots.
    graph_obligations = requirements.get("graph_import", [])
    if graph_obligations:
        emitted = 0
        for candidate_id, candidate in candidate_by_id.items():
            if candidate.get("extractor_id") != "python_ast":
                continue
            outcome = outcome_by_id[candidate_id]
            if outcome.get("status") != "EXECUTED":
                continue
            result = outcome.get("result") or {}
            for item in result.get("imports", []):
                module = item.get("module", "")
                root_name = module.split(".", 1)[0]
                if root_name not in _GRAPH_MODULE_ROOTS:
                    continue
                line = item.get("line")
                emit("graph_import", graph_obligations, candidate, outcome,
                     candidate["source_path"], line, "python_import_statement",
                     {"module": module, "imported_symbols": item.get("imported_symbols", []),
                      "matched_module_root": root_name})
                emitted += 1
        if not emitted:
            unresolved.append({"evidence_kind": "graph_import",
                               "status": "NO_MATCHING_STRUCTURAL_OBSERVATION",
                               "reason": "no_registered_graph_module_import_was_observed"})

    # 2. Python syntax errors are evidence of a failed parse for this exact file.
    syntax_obligations = requirements.get("python_syntax_error", [])
    if syntax_obligations:
        emitted = 0
        for candidate_id, candidate in candidate_by_id.items():
            if candidate.get("extractor_id") != "python_ast":
                continue
            outcome = outcome_by_id[candidate_id]
            diagnostic = outcome.get("diagnostic") or {}
            if outcome.get("status") == "FAILED" and outcome.get("diagnostic_code") == "source_parse_failed":
                line = diagnostic.get("line")
                emit("python_syntax_error", syntax_obligations, candidate, outcome,
                     candidate["source_path"], line, "python_ast_parse_failure",
                     {"exception_type": diagnostic.get("exception_type"),
                      "diagnostic_code": outcome.get("diagnostic_code"),
                      "message": diagnostic.get("message")})
                emitted += 1
        if not emitted:
            unresolved.append({"evidence_kind": "python_syntax_error",
                               "status": "NO_MATCHING_STRUCTURAL_OBSERVATION",
                               "reason": "no_python_ast_parse_failure_was_observed"})

    # 3. Explicit scope exclusions are inventory facts, not semantic findings.
    exclusion_obligations = requirements.get("scope_exclusion", [])
    if exclusion_obligations:
        exclusions = inventory.get("scope_exclusions", [])
        for item in exclusions:
            path = item.get("path")
            source_unit = next((x for x in inventory.get("source_units", [])
                                if x.get("path") == path), None)
            if source_unit is None:
                raise TypedEvidenceError("scope_exclusion_source_unit_missing:" + str(path))
            payload = {
                "schema": "ae32c/typed-evidence-observation/v1",
                "source_snapshot_id": source_snapshot_id,
                "rule_obligation_ids": sorted(exclusion_obligations),
                "evidence_kind": "scope_exclusion",
                "producer_id": _EVIDENCE_PRODUCERS["scope_exclusion"],
                "producer_version": "1.0.0",
                "extractor_id": None, "extractor_version": None,
                "candidate_id": None, "outcome_id": None,
                "source_path": path,
                "source_content_sha256": source_unit.get("content_sha256"),
                "source_line": None, "source_line_sha256": None,
                "observation_type": "declared_scope_exclusion",
                "structural_value": {"reason": item.get("reason")},
                "status": "STRUCTURALLY_OBSERVED",
                "semantic_acceptance": "NOT_ESTABLISHED",
                "limitation": "declared_exclusion_does_not_establish_scope_completeness",
            }
            observations.append(_observation(payload))
        if not exclusions:
            unresolved.append({"evidence_kind": "scope_exclusion",
                               "status": "NO_MATCHING_STRUCTURAL_OBSERVATION",
                               "reason": "inventory_contains_no_declared_scope_exclusions"})

    supported = set(_EVIDENCE_PRODUCERS)
    for kind in sorted(set(requirements) - supported):
        unresolved.append({"evidence_kind": kind, "status": "NO_AUTOMATIC_VALIDATOR",
                           "reason": "semantic_or_domain_specific_validator_not_implemented"})

    observations.sort(key=lambda x: (x["evidence_kind"], x.get("source_path") or "",
                                     x.get("source_line") or 0, x["evidence_observation_id"]))
    payload = {
        "schema": SCHEMA,
        "source_snapshot_id": source_snapshot_id,
        "plan_sha256": plan.plan_sha256,
        "inventory_sha256": inventory.get("inventory_sha256"),
        "execution_report_sha256": execution_report.get("report_sha256"),
        "observation_count": len(observations),
        "observations": observations,
        "unresolved_evidence_kinds": sorted(unresolved, key=lambda x: (x["evidence_kind"], x["status"])),
        "summary": {
            "required_evidence_kind_count": len(requirements),
            "structurally_observed_count": len(observations),
            "unsupported_or_unobserved_kind_count": len(unresolved),
            "semantic_evidence_accepted_count": 0,
            "epistemic_assertions_created": False,
            "coverage_dossier_mutated": False,
        },
        "authority": {
            "source_bound_structural_observations_created": True,
            "typed_semantic_evidence_sufficiency_established": False,
            "rule_obligations_satisfied": False,
            "proposition_truth_established": False,
            "audit_decision_authority": False,
            "production_approval": False,
        },
    }
    return {**payload, "bundle_sha256": _digest(payload)}


def verify_typed_evidence_observation_bundle(
    bundle: Mapping[str, Any], *, plan: RuleCoveragePlan,
    inventory: Mapping[str, Any], execution_report: Mapping[str, Any],
    repository_root: str | Path,
) -> dict[str, Any]:
    if not isinstance(bundle, Mapping):
        raise TypedEvidenceError("bundle_must_be_an_object")
    submitted = dict(bundle)
    digest = submitted.get("bundle_sha256")
    payload = {k: v for k, v in submitted.items() if k != "bundle_sha256"}
    if digest != _digest(payload):
        raise TypedEvidenceError("bundle_digest_mismatch")
    expected = derive_typed_evidence_observations(
        plan=plan, inventory=inventory, execution_report=execution_report,
        repository_root=repository_root)
    if _canonical(expected) != _canonical(submitted):
        raise TypedEvidenceError("bundle_semantic_replay_mismatch")
    return {"bundle_sha256": digest, "semantic_integrity": True,
            "semantic_replay": True, "observation_count": expected["observation_count"],
            "semantic_evidence_accepted_count": 0}


class TypedEvidenceObservationStore:
    """Append-only SQLite hash-chain store for deterministic observation bundles."""
    def __init__(self, database: str | Path, *, max_records: int = 10000):
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records < 1:
            raise ValueError("max_records_must_be_positive_integer")
        self.max_records = max_records
        self._db = sqlite3.connect(str(database))
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS typed_evidence_events (
                sequence INTEGER PRIMARY KEY, bundle_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TRIGGER IF NOT EXISTS typed_evidence_no_update
            BEFORE UPDATE ON typed_evidence_events
            BEGIN SELECT RAISE(ABORT, 'typed evidence ledger is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS typed_evidence_no_delete
            BEFORE DELETE ON typed_evidence_events
            BEGIN SELECT RAISE(ABORT, 'typed evidence ledger is append-only'); END;
        """)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def verify_integrity(self) -> bool:
        previous = "0" * 64
        rows = self._db.execute("SELECT * FROM typed_evidence_events ORDER BY sequence").fetchall()
        for sequence, row in enumerate(rows, 1):
            digest = hashlib.sha256(row["payload"].encode("utf-8")).hexdigest()
            event = hashlib.sha256(
                f"{sequence}\n{row['bundle_id']}\n{digest}\n{previous}".encode()).hexdigest()
            try:
                payload = json.loads(row["payload"])
                bundle_id = payload.get("bundle_sha256")
                semantic = {k: v for k, v in payload.items() if k != "bundle_sha256"}
            except (TypeError, ValueError, AttributeError):
                return False
            if (row["sequence"] != sequence or row["payload_sha256"] != digest
                    or row["previous_hash"] != previous or row["event_hash"] != event
                    or bundle_id != row["bundle_id"] or bundle_id != _digest(semantic)):
                return False
            previous = event
        return True

    def record(self, bundle: Mapping[str, Any]) -> bool:
        if not isinstance(bundle, Mapping):
            raise TypeError("bundle_must_be_an_object")
        identity = bundle.get("bundle_sha256")
        payload = json.dumps(dict(bundle), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if identity != _digest({k: v for k, v in bundle.items() if k != "bundle_sha256"}):
            raise TypedEvidenceError("bundle_digest_mismatch")
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            if not self.verify_integrity():
                raise TypedEvidenceError("ledger_integrity_failure")
            prior = self._db.execute("SELECT payload_sha256 FROM typed_evidence_events WHERE bundle_id=?",
                                     (identity,)).fetchone()
            if prior:
                if prior["payload_sha256"] != payload_hash:
                    raise TypedEvidenceError("bundle_identity_conflict")
                return False
            sequence = self._db.execute("SELECT COUNT(*) FROM typed_evidence_events").fetchone()[0] + 1
            if sequence > self.max_records:
                raise TypedEvidenceError("ledger_storage_limit_reached")
            last = self._db.execute("SELECT event_hash FROM typed_evidence_events ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = last["event_hash"] if last else "0" * 64
            event = hashlib.sha256(
                f"{sequence}\n{identity}\n{payload_hash}\n{previous}".encode()).hexdigest()
            self._db.execute("INSERT INTO typed_evidence_events VALUES (?, ?, ?, ?, ?, ?)",
                             (sequence, identity, payload, payload_hash, previous, event))
        return True

    def get(self, bundle_id: str) -> dict[str, Any] | None:
        if not self.verify_integrity():
            raise TypedEvidenceError("ledger_integrity_failure")
        row = self._db.execute("SELECT payload FROM typed_evidence_events WHERE bundle_id=?",
                               (bundle_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def history(self) -> tuple[dict[str, Any], ...]:
        if not self.verify_integrity():
            raise TypedEvidenceError("ledger_integrity_failure")
        rows = self._db.execute("SELECT sequence,bundle_id,event_hash FROM typed_evidence_events ORDER BY sequence").fetchall()
        return tuple({"sequence": r["sequence"], "bundle_id": r["bundle_id"],
                      "event_hash": r["event_hash"]} for r in rows)


def build_and_persist_typed_evidence_observations(
    *, store: TypedEvidenceObservationStore, plan: RuleCoveragePlan,
    claim: AssuranceClaim, manifest: EpistemicCoverageManifest,
    source_manifest: Mapping[str, Any], inventory: Mapping[str, Any],
    execution_report: Mapping[str, Any], dossier_id: str,
    reconciliation_id: str,
    reconciliation_store: ExecutionObligationReconciliationStore,
    assurance_store: AssuranceStore, epistemic_store: EpistemicStore,
    dossier_store: CoverageDossierStore, repository_root: str | Path,
) -> dict[str, Any]:
    """Persist observations only after independent M7.5.14 semantic replay."""
    verify_rule_derived_manifest(claim, plan, manifest)
    try:
        verify_source_extractor_inventory(source_manifest, inventory)
        verify_extractor_execution_report(source_manifest, inventory, execution_report, repository_root)
        reconciliation_check = verify_execution_obligation_reconciliation(
            reconciliation_id,
            reconciliation_store=reconciliation_store,
            dossier_id=dossier_id, claim=claim, plan=plan, manifest=manifest,
            source_manifest=source_manifest, inventory=inventory,
            execution_report=execution_report, repository_root=repository_root,
            assurance_store=assurance_store, epistemic_store=epistemic_store,
            dossier_store=dossier_store,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise TypedEvidenceError("upstream_evidence_verification_failed:" + type(exc).__name__) from exc
    if reconciliation_check.get("semantic_replay") is not True:
        raise TypedEvidenceError("execution_reconciliation_replay_not_verified")
    if source_manifest.get("source_snapshot_id") != plan.source_snapshot_id:
        raise TypedEvidenceError("source_snapshot_mismatch")
    if execution_report.get("source_snapshot_id") != plan.source_snapshot_id:
        raise TypedEvidenceError("execution_snapshot_mismatch")
    bundle = derive_typed_evidence_observations(
        plan=plan, inventory=inventory, execution_report=execution_report,
        repository_root=repository_root)
    store.record(bundle)
    return bundle

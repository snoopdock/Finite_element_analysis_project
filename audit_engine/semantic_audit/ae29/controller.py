"""AE-29: bounded iterative repository audit and self-correction control.

AE-29 is the controlled loop between repository auditing, AE-28 neural
interpretation, repair proposal, independent verification, post-repair audit,
and non-authoritative decision memory.

The engine operates on immutable in-memory repository snapshots. It never
writes to the authoritative checkout, executes shell commands, invokes a
network service, or promotes an LLM statement to truth. An accepted repair can
be materialized only as a separate candidate workspace by an explicit caller.

Decision memory is historical guidance only. It cannot authorize a repair.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import copy
import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence
from types import MappingProxyType

from audit_engine.semantic_audit.ae24.contracts import canonical, sha

SESSION_SCHEMA = "ae29/iterative-audit-session/v1"
FINDING_SCHEMA = "ae29/repository-audit-finding/v1"
AUDIT_SCHEMA = "ae29/repository-audit-report/v1"
HANDOFF_SCHEMA = "ae29/neural-investigation-handoff/v1"
REPAIR_SCHEMA = "ae29/repair-proposal/v1"
VERIFICATION_SCHEMA = "ae29/repair-verification/v1"
DECISION_SCHEMA = "ae29/decision-record/v1"

MAX_FILES = 4000
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_FINDINGS = 1000
MAX_EVIDENCE = 200
MAX_ITERATIONS = 8
MAX_OPERATIONS = 200
MAX_DECISIONS = 500
MAX_LESSON_CODES = 32
MAX_TEXT = 4000
MAX_MEMORY_RECORDS = 2000
MAX_MATERIALIZE_FILES = 4000
AE29_REPOSITORY_MANIFEST_ID = "ae29-repository-snapshot"

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
PATH = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\\)(?!.*//)[^\x00]{1,512}$")
SEVERITIES = frozenset({"info", "low", "medium", "high", "critical"})
FINDING_STATUSES = frozenset({"open", "resolved", "suppressed"})
REPAIR_KINDS = frozenset({
    "code_fix",
    "test_fix",
    "configuration_fix",
    "dependency_fix",
    "data_fix",
    "documentation_fix",
    "refactor",
    "other",
})
DECISIONS = frozenset({
    "await_verification",
    "await_post_audit",
    "reject_repair",
    "accept_repair",
    "defer",
})
VERIFICATION_STATUSES = frozenset({"passed", "failed", "inconclusive"})
CHECK_STATUSES = frozenset({"passed", "failed", "skipped"})


class IterativeAuditError(ValueError):
    """Invalid, stale, unsafe, or non-replayable AE-29 state."""


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise IterativeAuditError(f"Invalid {label}")
    return value


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise IterativeAuditError(f"Invalid {label}")
    return value


def _require_text(value: Any, label: str, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise IterativeAuditError(f"Invalid {label}")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise IterativeAuditError(f"Invalid {label}")
    return value


def _require_path(value: Any) -> str:
    if not isinstance(value, str) or not PATH.fullmatch(value):
        raise IterativeAuditError("Invalid repository-relative path")
    if value == "." or value.startswith(".git/") or value == ".git":
        raise IterativeAuditError("Repository metadata paths are forbidden")
    return value


def _digest_json(value: Any) -> str:
    return sha(canonical(value))


def _body_without_digest(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    body = copy.deepcopy(dict(value))
    body.pop(field, None)
    return body


def _digest_file(data: bytes) -> str:
    if not isinstance(data, bytes):
        raise IterativeAuditError("Repository file content must be bytes")
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class RepositorySnapshot:
    """Immutable-by-convention, bounded repository file snapshot.

    The snapshot is detached from the caller's mapping. It is a data object,
    not a live filesystem view.
    """

    files: Mapping[str, bytes]

    def __post_init__(self) -> None:
        normalized = _normalize_files(self.files)
        object.__setattr__(self, "files", MappingProxyType(normalized))

    @property
    def total_bytes(self) -> int:
        return sum(len(value) for value in self.files.values())

    @property
    def manifest(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {"path": path, "sha256": _digest_file(data), "size": len(data)}
            for path, data in sorted(self.files.items())
        )

    @property
    def snapshot_sha256(self) -> str:
        return _digest_json({"schema_version": "ae29/repository-snapshot/v1",
                             "files": list(self.manifest)})

    def to_payload(self, *, include_bytes: bool = False) -> dict[str, Any]:
        rows = []
        for row in self.manifest:
            item = dict(row)
            if include_bytes:
                item["content_b64"] = base64.b64encode(self.files[row["path"]]).decode("ascii")
            rows.append(item)
        return {
            "schema_version": "ae29/repository-snapshot/v1",
            "snapshot_sha256": self.snapshot_sha256,
            "files": rows,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RepositorySnapshot":
        if not isinstance(payload, Mapping) or payload.get("schema_version") != "ae29/repository-snapshot/v1":
            raise IterativeAuditError("Invalid repository snapshot payload")
        rows = payload.get("files")
        if not isinstance(rows, list):
            raise IterativeAuditError("Repository snapshot files must be a list")
        files: dict[str, bytes] = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"path", "sha256", "size", "content_b64"}:
                raise IterativeAuditError("Invalid repository snapshot entry")
            path = _require_path(row["path"])
            _require_digest(row["sha256"], "snapshot file digest")
            if type(row["size"]) is not int or row["size"] < 0 or row["size"] > MAX_FILE_BYTES:
                raise IterativeAuditError("Invalid snapshot file size")
            try:
                data = base64.b64decode(row["content_b64"], validate=True)
            except (ValueError, TypeError):
                raise IterativeAuditError("Invalid snapshot file encoding")
            if len(data) != row["size"] or _digest_file(data) != row["sha256"]:
                raise IterativeAuditError("Repository snapshot file digest mismatch")
            if path in files:
                raise IterativeAuditError("Duplicate repository snapshot path")
            files[path] = data
        snapshot = cls(files)
        if snapshot.snapshot_sha256 != payload.get("snapshot_sha256"):
            raise IterativeAuditError("Repository snapshot digest mismatch")
        return snapshot

    def apply(self, repair: Mapping[str, Any]) -> "RepositorySnapshot":
        normalized = validate_repair(self, repair)
        updated = dict(self.files)
        for op in normalized["operations"]:
            path = op["path"]
            if op["op"] == "write_file":
                try:
                    data = base64.b64decode(op["content_b64"], validate=True)
                except (ValueError, TypeError):
                    raise IterativeAuditError("Repair content encoding is invalid")
                if _digest_file(data) != op["content_sha256"]:
                    raise IterativeAuditError("Repair content digest mismatch")
                updated[path] = data
            elif op["op"] == "delete_file":
                if path not in updated:
                    raise IterativeAuditError("Repair delete target disappeared")
                del updated[path]
            else:
                raise IterativeAuditError("Unsupported repair operation")
        return RepositorySnapshot(updated)


def _normalize_files(files: Mapping[str, bytes]) -> dict[str, bytes]:
    if not isinstance(files, Mapping):
        raise IterativeAuditError("Repository files must be a mapping")
    if len(files) > MAX_FILES:
        raise IterativeAuditError("Repository file-count budget exceeded")
    normalized: dict[str, bytes] = {}
    total = 0
    for raw_path, raw_data in files.items():
        path = _require_path(raw_path)
        if path in normalized:
            raise IterativeAuditError("Duplicate repository path")
        if not isinstance(raw_data, bytes) or len(raw_data) > MAX_FILE_BYTES:
            raise IterativeAuditError("Repository file exceeds byte budget")
        total += len(raw_data)
        if total > MAX_TOTAL_BYTES:
            raise IterativeAuditError("Repository snapshot byte budget exceeded")
        normalized[path] = bytes(raw_data)
    return dict(sorted(normalized.items()))


def make_finding(
    snapshot: RepositorySnapshot,
    *,
    finding_id: str,
    rule_id: str,
    category: str,
    severity: str,
    title: str,
    message: str,
    evidence_paths: Sequence[str] = (),
    status: str = "open",
) -> dict[str, Any]:
    _require_id(finding_id, "finding identity")
    _require_id(rule_id, "rule identity")
    _require_id(category, "finding category")
    if severity not in SEVERITIES:
        raise IterativeAuditError("Unsupported finding severity")
    if status not in FINDING_STATUSES:
        raise IterativeAuditError("Unsupported finding status")
    _require_text(title, "finding title")
    _require_text(message, "finding message")
    paths = list(dict.fromkeys(evidence_paths))
    if len(paths) > MAX_EVIDENCE:
        raise IterativeAuditError("Finding evidence budget exceeded")
    evidence = []
    for path in paths:
        path = _require_path(path)
        if path not in snapshot.files:
            raise IterativeAuditError(f"Finding evidence path is absent: {path}")
        evidence.append({"path": path, "sha256": _digest_file(snapshot.files[path])})
    body = {
        "schema_version": FINDING_SCHEMA,
        "finding_id": finding_id,
        "rule_id": rule_id,
        "category": category,
        "severity": severity,
        "title": title,
        "message": message,
        "evidence": sorted(evidence, key=lambda item: item["path"]),
        "snapshot_sha256": snapshot.snapshot_sha256,
        "status": status,
    }
    body["finding_fingerprint"] = _digest_json({
        key: body[key]
        for key in ("rule_id", "category", "severity", "title", "evidence")
    })
    return body


def validate_finding(snapshot: RepositorySnapshot, finding: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(finding, Mapping):
        raise IterativeAuditError("Finding must be an object")
    allowed = {
        "schema_version", "finding_id", "rule_id", "category", "severity",
        "title", "message", "evidence", "snapshot_sha256", "status",
        "finding_fingerprint",
    }
    if set(finding) != allowed or finding["schema_version"] != FINDING_SCHEMA:
        raise IterativeAuditError("Invalid finding envelope")
    _require_id(finding["finding_id"], "finding identity")
    _require_id(finding["rule_id"], "rule identity")
    _require_id(finding["category"], "finding category")
    if finding["severity"] not in SEVERITIES or finding["status"] not in FINDING_STATUSES:
        raise IterativeAuditError("Invalid finding classification")
    _require_text(finding["title"], "finding title")
    _require_text(finding["message"], "finding message")
    if finding["snapshot_sha256"] != snapshot.snapshot_sha256:
        raise IterativeAuditError("Finding is stale for repository snapshot")
    evidence = finding["evidence"]
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE:
        raise IterativeAuditError("Invalid finding evidence")
    seen = set()
    normalized = []
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise IterativeAuditError("Invalid finding evidence entry")
        path = _require_path(item["path"])
        digest = _require_digest(item["sha256"], "finding evidence digest")
        if path in seen or path not in snapshot.files:
            raise IterativeAuditError("Finding evidence path is invalid or duplicated")
        if _digest_file(snapshot.files[path]) != digest:
            raise IterativeAuditError("Finding evidence digest mismatch")
        seen.add(path)
        normalized.append({"path": path, "sha256": digest})
    expected_fp = _digest_json({
        key: finding[key] for key in ("rule_id", "category", "severity", "title", "evidence")
    })
    if finding["finding_fingerprint"] != expected_fp:
        raise IterativeAuditError("Finding fingerprint mismatch")
    return copy.deepcopy(dict(finding))


def make_audit_report(
    snapshot: RepositorySnapshot,
    findings: Sequence[Mapping[str, Any]],
    *,
    auditor_id: str,
    auditor_version: str,
    run_sha256: str,
) -> dict[str, Any]:
    _require_id(auditor_id, "auditor identity")
    _require_text(auditor_version, "auditor version", 256)
    _require_digest(run_sha256, "auditor run digest")
    if len(findings) > MAX_FINDINGS:
        raise IterativeAuditError("Finding budget exceeded")
    normalized = [validate_finding(snapshot, item) for item in findings]
    ids = [item["finding_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise IterativeAuditError("Duplicate finding identity")
    body = {
        "schema_version": AUDIT_SCHEMA,
        "snapshot_sha256": snapshot.snapshot_sha256,
        "auditor": {"id": auditor_id, "version": auditor_version},
        "run_sha256": run_sha256,
        "findings": sorted(normalized, key=lambda item: item["finding_id"]),
    }
    body["audit_sha256"] = _digest_json(body)
    return body


def validate_audit_report(snapshot: RepositorySnapshot, report: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise IterativeAuditError("Audit report must be an object")
    if set(report) != {"schema_version", "snapshot_sha256", "auditor", "run_sha256", "findings", "audit_sha256"}:
        raise IterativeAuditError("Invalid audit report envelope")
    if report["schema_version"] != AUDIT_SCHEMA or report["snapshot_sha256"] != snapshot.snapshot_sha256:
        raise IterativeAuditError("Audit report is stale for repository snapshot")
    auditor = report["auditor"]
    if not isinstance(auditor, dict) or set(auditor) != {"id", "version"}:
        raise IterativeAuditError("Invalid auditor metadata")
    _require_id(auditor["id"], "auditor identity")
    _require_text(auditor["version"], "auditor version", 256)
    _require_digest(report["run_sha256"], "auditor run digest")
    findings = report["findings"]
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        raise IterativeAuditError("Invalid audit findings")
    normalized = [validate_finding(snapshot, item) for item in findings]
    ids = [item["finding_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise IterativeAuditError("Duplicate finding identity")
    expected = _digest_json(_body_without_digest(report, "audit_sha256"))
    if report["audit_sha256"] != expected:
        raise IterativeAuditError("Audit report digest mismatch")
    return copy.deepcopy(dict(report))


def bind_ae28_interpretation(
    snapshot: RepositorySnapshot,
    *,
    contract: Mapping[str, Any],
    sources: Mapping[str, bytes],
    request: Mapping[str, Any],
    raw_output: bytes,
    response: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify an AE-28 interpretation and bind it to this repository snapshot.

    The AE-28 request must explicitly include the AE-29 repository snapshot
    digest as an input-manifest item. This prevents a valid interpretation from
    one repository state from being reused for another state.
    """
    try:
        from audit_engine.semantic_audit.ae28.adapter import verify_interpretation
        verify_interpretation(contract, sources, dict(request), raw_output, dict(response), dict(interpretation))
    except KeyError as exc:
        raise IterativeAuditError("AE-28 interpretation handoff is missing required fields") from exc
    except Exception as exc:
        raise IterativeAuditError(f"AE-28 interpretation verification failed: {exc}") from exc

    manifest = request.get("input_manifest")
    if not isinstance(manifest, list):
        raise IterativeAuditError("AE-28 request has no input manifest")
    repository_entries = [
        item for item in manifest
        if isinstance(item, Mapping) and item.get("id") == AE29_REPOSITORY_MANIFEST_ID
    ]
    if len(repository_entries) != 1 or repository_entries[0].get("sha256") != snapshot.snapshot_sha256:
        raise IterativeAuditError("AE-28 request is not bound to the current repository snapshot")

    if not isinstance(interpretation, Mapping):
        raise IterativeAuditError("AE-28 interpretation handoff must be an object")
    authority = interpretation.get("authority")
    expected_authority = {
        "model_output_verified": False,
        "semantic_truth_verified": False,
        "candidate_only": True,
        "automatic_graph_mutation_permitted": False,
        "candidate_promoted_to_authoritative_fact": False,
    }
    if authority != expected_authority:
        raise IterativeAuditError("AE-28 interpretation authority boundary violated")
    proposal = interpretation.get("proposal")
    if not isinstance(proposal, Mapping):
        raise IterativeAuditError("AE-28 interpretation has no proposal")
    candidates = proposal.get("candidate_assertions")
    if not isinstance(candidates, list) or not candidates:
        raise IterativeAuditError("AE-28 interpretation has no candidate assertions")
    candidate_ids = [_require_id(item.get("id"), "candidate identity") for item in candidates if isinstance(item, Mapping)]
    if len(candidate_ids) != len(candidates) or len(set(candidate_ids)) != len(candidate_ids):
        raise IterativeAuditError("AE-28 candidate identities are invalid")

    interpretation_sha = interpretation.get("interpretation_sha256")
    request_sha = request.get("request_sha256")
    _require_digest(interpretation_sha, "interpretation digest")
    _require_digest(request_sha, "request digest")
    return make_neural_handoff(
        snapshot,
        interpretation_sha256=interpretation_sha,
        request_sha256=request_sha,
        candidate_ids=candidate_ids,
    )


def make_neural_handoff(
    snapshot: RepositorySnapshot,
    *,
    interpretation_sha256: str,
    request_sha256: str,
    candidate_ids: Sequence[str],
) -> dict[str, Any]:
    _require_digest(interpretation_sha256, "interpretation digest")
    _require_digest(request_sha256, "request digest")
    ids = sorted(dict.fromkeys(_require_id(x, "candidate identity") for x in candidate_ids))
    if not ids:
        raise IterativeAuditError("Neural handoff requires at least one candidate")
    body = {
        "schema_version": HANDOFF_SCHEMA,
        "repository_snapshot_sha256": snapshot.snapshot_sha256,
        "interpretation_sha256": interpretation_sha256,
        "request_sha256": request_sha256,
        "candidate_ids": ids,
        "authority": {
            "candidate_only": True,
            "automatic_repository_mutation_permitted": False,
            "candidate_promoted_to_authoritative_fact": False,
        },
    }
    body["handoff_sha256"] = _digest_json(body)
    return body


def validate_neural_handoff(
    snapshot: RepositorySnapshot,
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(handoff, Mapping):
        raise IterativeAuditError("Neural handoff must be an object")
    allowed = {
        "schema_version", "repository_snapshot_sha256", "interpretation_sha256",
        "request_sha256", "candidate_ids", "authority", "handoff_sha256",
    }
    if set(handoff) != allowed or handoff["schema_version"] != HANDOFF_SCHEMA:
        raise IterativeAuditError("Invalid neural handoff envelope")
    if handoff["repository_snapshot_sha256"] != snapshot.snapshot_sha256:
        raise IterativeAuditError("Neural investigation is stale for repository snapshot")
    _require_digest(handoff["interpretation_sha256"], "interpretation digest")
    _require_digest(handoff["request_sha256"], "request digest")
    ids = handoff["candidate_ids"]
    if not isinstance(ids, list) or not ids or len(ids) > MAX_FINDINGS:
        raise IterativeAuditError("Invalid neural candidate set")
    normalized_ids = [_require_id(x, "candidate identity") for x in ids]
    if len(set(normalized_ids)) != len(normalized_ids) or normalized_ids != sorted(normalized_ids):
        raise IterativeAuditError("Neural candidate identities must be unique and canonical")
    authority = handoff["authority"]
    expected_authority = {
        "candidate_only": True,
        "automatic_repository_mutation_permitted": False,
        "candidate_promoted_to_authoritative_fact": False,
    }
    if authority != expected_authority:
        raise IterativeAuditError("Neural handoff authority boundary violated")
    expected = _digest_json(_body_without_digest(handoff, "handoff_sha256"))
    if handoff["handoff_sha256"] != expected:
        raise IterativeAuditError("Neural handoff digest mismatch")
    return copy.deepcopy(dict(handoff))


def _validate_operation(snapshot: RepositorySnapshot, operation: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(operation, Mapping):
        raise IterativeAuditError("Repair operation must be an object")
    op = operation.get("op")
    if op == "write_file":
        allowed = {"op", "path", "expected_sha256", "content_sha256", "content_b64"}
        if set(operation) != allowed:
            raise IterativeAuditError("Invalid write operation")
        path = _require_path(operation["path"])
        if _is_protected_repair_path(path):
            raise IterativeAuditError("Repair cannot modify protected audit-control path")
        expected = operation["expected_sha256"]
        if expected is not None:
            _require_digest(expected, "expected file digest")
            if path not in snapshot.files:
                raise IterativeAuditError("Repair expected an existing file")
            if _digest_file(snapshot.files[path]) != expected:
                raise IterativeAuditError("Repair target file changed since proposal")
        elif path in snapshot.files:
            raise IterativeAuditError("Repair create operation expected an absent file")
        content_sha = _require_digest(operation["content_sha256"], "repair content digest")
        if not isinstance(operation["content_b64"], str):
            raise IterativeAuditError("Repair content must be base64 text")
        try:
            content = base64.b64decode(operation["content_b64"], validate=True)
        except (ValueError, TypeError):
            raise IterativeAuditError("Repair content encoding is invalid")
        if len(content) > MAX_FILE_BYTES:
            raise IterativeAuditError("Repair content exceeds file byte budget")
        if _digest_file(content) != content_sha:
            raise IterativeAuditError("Repair content digest mismatch")
    elif op == "delete_file":
        allowed = {"op", "path", "expected_sha256"}
        if set(operation) != allowed:
            raise IterativeAuditError("Invalid delete operation")
        path = _require_path(operation["path"])
        if _is_protected_repair_path(path):
            raise IterativeAuditError("Repair cannot modify protected audit-control path")
        _require_digest(operation["expected_sha256"], "expected delete digest")
        if path not in snapshot.files or _digest_file(snapshot.files[path]) != operation["expected_sha256"]:
            raise IterativeAuditError("Repair delete target does not match current file")
    else:
        raise IterativeAuditError("Unsupported repair operation")
    return copy.deepcopy(dict(operation))


def _is_protected_repair_path(path: str) -> bool:
    protected = (
        ".github/",
        "validation/",
        "validation-engine/",
        "decision_memory/",
    )
    return path == ".github" or any(path.startswith(prefix) for prefix in protected)


def make_repair_proposal(
    snapshot: RepositorySnapshot,
    *,
    repair_id: str,
    target_finding_ids: Sequence[str],
    target_finding_fingerprints: Mapping[str, str],
    neural_handoff_sha256: str,
    kind: str,
    operations: Sequence[Mapping[str, Any]],
    reason_codes: Sequence[str] = (),
) -> dict[str, Any]:
    """Construct a canonical repair proposal without touching the filesystem."""
    _require_id(repair_id, "repair identity")
    _require_digest(neural_handoff_sha256, "neural handoff digest")
    if kind not in REPAIR_KINDS:
        raise IterativeAuditError("Unsupported repair kind")
    targets = sorted(dict.fromkeys(_require_id(x, "repair target finding identity") for x in target_finding_ids))
    if not targets:
        raise IterativeAuditError("Repair requires at least one target finding")
    if not isinstance(target_finding_fingerprints, Mapping):
        raise IterativeAuditError("Repair target finding fingerprints must be a mapping")
    if set(target_finding_fingerprints) != set(targets):
        raise IterativeAuditError("Repair target finding fingerprints must match target findings")
    fingerprint_rows = []
    for ident in targets:
        fingerprint_rows.append({
            "finding_id": ident,
            "finding_fingerprint": _require_digest(
                target_finding_fingerprints[ident], "repair target finding fingerprint"
            ),
        })
    if not isinstance(operations, Sequence) or isinstance(operations, (str, bytes)) or not operations:
        raise IterativeAuditError("Repair requires operations")
    normalized_ops = [_validate_operation(snapshot, op) for op in operations]
    normalized_ops.sort(key=lambda item: (item["path"], item["op"]))
    if len({(item["op"], item["path"]) for item in normalized_ops}) != len(normalized_ops):
        raise IterativeAuditError("Duplicate repair operation target")
    codes = sorted(dict.fromkeys(_require_id(x, "repair reason code") for x in reason_codes))
    if len(codes) > MAX_LESSON_CODES:
        raise IterativeAuditError("Repair reason-code budget exceeded")
    body = {
        "schema_version": REPAIR_SCHEMA,
        "repair_id": repair_id,
        "base_snapshot_sha256": snapshot.snapshot_sha256,
        "target_finding_ids": targets,
        "target_finding_fingerprints": fingerprint_rows,
        "neural_handoff_sha256": neural_handoff_sha256,
        "kind": kind,
        "operations": normalized_ops,
        "reason_codes": codes,
    }
    body["repair_sha256"] = _digest_json(body)
    return body


def validate_repair(
    snapshot: RepositorySnapshot,
    repair: Mapping[str, Any],
    *,
    finding_ids: Sequence[str] | None = None,
    finding_fingerprints: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not isinstance(repair, Mapping):
        raise IterativeAuditError("Repair proposal must be an object")
    allowed = {
        "schema_version", "repair_id", "base_snapshot_sha256",
        "target_finding_ids", "target_finding_fingerprints", "neural_handoff_sha256", "kind",
        "operations", "reason_codes", "repair_sha256",
    }
    required = allowed - {"repair_sha256"}
    if set(repair) - allowed or not required <= set(repair):
        raise IterativeAuditError("Invalid repair proposal envelope")
    if repair["schema_version"] != REPAIR_SCHEMA:
        raise IterativeAuditError("Unsupported repair schema")
    _require_id(repair["repair_id"], "repair identity")
    if repair["base_snapshot_sha256"] != snapshot.snapshot_sha256:
        raise IterativeAuditError("Repair is stale for repository snapshot")
    _require_digest(repair["neural_handoff_sha256"], "neural handoff digest")
    if repair["kind"] not in REPAIR_KINDS:
        raise IterativeAuditError("Unsupported repair kind")
    targets = repair["target_finding_ids"]
    if not isinstance(targets, list) or not targets or len(targets) > MAX_FINDINGS:
        raise IterativeAuditError("Invalid repair target findings")
    targets = [_require_id(x, "repair target finding identity") for x in targets]
    if len(set(targets)) != len(targets) or targets != sorted(targets):
        raise IterativeAuditError("Repair target findings must be unique and canonical")
    target_fingerprints = repair["target_finding_fingerprints"]
    if not isinstance(target_fingerprints, list) or len(target_fingerprints) != len(targets):
        raise IterativeAuditError("Invalid repair target finding fingerprints")
    seen_target_fingerprints = set()
    normalized_target_fingerprints = []
    for item in target_fingerprints:
        if not isinstance(item, Mapping) or set(item) != {"finding_id", "finding_fingerprint"}:
            raise IterativeAuditError("Invalid repair target finding fingerprint entry")
        ident = _require_id(item["finding_id"], "repair target finding identity")
        fp = _require_digest(item["finding_fingerprint"], "repair target finding fingerprint")
        if ident in seen_target_fingerprints:
            raise IterativeAuditError("Duplicate repair target finding fingerprint")
        seen_target_fingerprints.add(ident)
        normalized_target_fingerprints.append({
            "finding_id": ident,
            "finding_fingerprint": fp,
        })
    if [item["finding_id"] for item in normalized_target_fingerprints] != targets:
        raise IterativeAuditError("Repair target finding fingerprints must be canonical")
    if finding_ids is not None and not set(targets) <= set(finding_ids):
        raise IterativeAuditError("Repair targets an unknown audit finding")
    if finding_fingerprints is not None:
        for item in normalized_target_fingerprints:
            if item["finding_id"] not in finding_fingerprints:
                raise IterativeAuditError("Repair target finding fingerprint is unknown")
            if item["finding_fingerprint"] != finding_fingerprints[item["finding_id"]]:
                raise IterativeAuditError("Repair target finding fingerprint does not match current audit")
    operations = repair["operations"]
    if not isinstance(operations, list) or not operations or len(operations) > MAX_OPERATIONS:
        raise IterativeAuditError("Invalid repair operation set")
    normalized = [_validate_operation(snapshot, op) for op in operations]
    keys = [(_op["op"], _op["path"]) for _op in normalized]
    if len(keys) != len(set(keys)):
        raise IterativeAuditError("Duplicate repair operation target")
    if normalized != sorted(normalized, key=lambda item: (item["path"], item["op"])):
        raise IterativeAuditError("Repair operations must be canonicalized")
    codes = repair["reason_codes"]
    if not isinstance(codes, list) or len(codes) > MAX_LESSON_CODES:
        raise IterativeAuditError("Invalid repair reason codes")
    for code in codes:
        _require_id(code, "repair reason code")
    body = _body_without_digest(repair, "repair_sha256")
    expected = _digest_json(body)
    if repair.get("repair_sha256") != expected:
        raise IterativeAuditError("Repair proposal digest mismatch")
    return copy.deepcopy(dict(repair))


def make_verification(
    before: RepositorySnapshot,
    after: RepositorySnapshot,
    repair: Mapping[str, Any],
    *,
    verifier_id: str,
    verifier_version: str,
    run_sha256: str,
    status: str,
    checks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    repair = validate_repair(before, repair)
    if status not in VERIFICATION_STATUSES:
        raise IterativeAuditError("Unsupported verification status")
    _require_id(verifier_id, "verifier identity")
    _require_text(verifier_version, "verifier version", 256)
    _require_digest(run_sha256, "verifier run digest")
    if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes)) or not checks:
        raise IterativeAuditError("Verification requires checks")
    normalized = []
    seen = set()
    for check in checks:
        if not isinstance(check, Mapping) or set(check) != {"id", "status", "detail_sha256"}:
            raise IterativeAuditError("Invalid verification check")
        ident = _require_id(check["id"], "verification check identity")
        if ident in seen:
            raise IterativeAuditError("Duplicate verification check identity")
        seen.add(ident)
        if check["status"] not in CHECK_STATUSES:
            raise IterativeAuditError("Invalid verification check status")
        _require_digest(check["detail_sha256"], "verification check detail digest")
        normalized.append({
            "id": ident,
            "status": check["status"],
            "detail_sha256": check["detail_sha256"],
        })
    normalized.sort(key=lambda item: item["id"])
    if status == "passed" and any(item["status"] != "passed" for item in normalized):
        raise IterativeAuditError("Passed verification contains a non-passed check")
    body = {
        "schema_version": VERIFICATION_SCHEMA,
        "repair_sha256": repair["repair_sha256"],
        "input_snapshot_sha256": before.snapshot_sha256,
        "output_snapshot_sha256": after.snapshot_sha256,
        "verifier": {"id": verifier_id, "version": verifier_version},
        "run_sha256": run_sha256,
        "status": status,
        "checks": normalized,
        "authority": {
            "repository_truth_verified": False,
            "authoritative_checkout_mutation_permitted": False,
        },
    }
    body["verification_sha256"] = _digest_json(body)
    return body


def validate_verification(
    before: RepositorySnapshot,
    after: RepositorySnapshot,
    repair: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    repair = validate_repair(before, repair)
    if not isinstance(verification, Mapping):
        raise IterativeAuditError("Verification result must be an object")
    allowed = {
        "schema_version", "repair_sha256", "input_snapshot_sha256",
        "output_snapshot_sha256", "verifier", "run_sha256", "status",
        "checks", "authority", "verification_sha256",
    }
    if set(verification) != allowed or verification["schema_version"] != VERIFICATION_SCHEMA:
        raise IterativeAuditError("Invalid verification envelope")
    if verification["repair_sha256"] != repair["repair_sha256"]:
        raise IterativeAuditError("Verification is bound to a different repair")
    if verification["input_snapshot_sha256"] != before.snapshot_sha256:
        raise IterativeAuditError("Verification input snapshot mismatch")
    if verification["output_snapshot_sha256"] != after.snapshot_sha256:
        raise IterativeAuditError("Verification output snapshot mismatch")
    verifier = verification["verifier"]
    if not isinstance(verifier, dict) or set(verifier) != {"id", "version"}:
        raise IterativeAuditError("Invalid verifier metadata")
    _require_id(verifier["id"], "verifier identity")
    _require_text(verifier["version"], "verifier version", 256)
    _require_digest(verification["run_sha256"], "verifier run digest")
    if verification["status"] not in VERIFICATION_STATUSES:
        raise IterativeAuditError("Unsupported verification status")
    checks = verification["checks"]
    if not isinstance(checks, list) or not checks:
        raise IterativeAuditError("Verification checks are required")
    normalized = []
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"id", "status", "detail_sha256"}:
            raise IterativeAuditError("Invalid verification check")
        ident = _require_id(check["id"], "verification check identity")
        if ident in seen:
            raise IterativeAuditError("Duplicate verification check")
        seen.add(ident)
        if check["status"] not in CHECK_STATUSES:
            raise IterativeAuditError("Invalid verification check status")
        _require_digest(check["detail_sha256"], "verification check detail digest")
        normalized.append(dict(check))
    if verification["status"] == "passed" and any(x["status"] != "passed" for x in normalized):
        raise IterativeAuditError("Passed verification contains a non-passed check")
    authority = verification["authority"]
    if authority != {
        "repository_truth_verified": False,
        "authoritative_checkout_mutation_permitted": False,
    }:
        raise IterativeAuditError("Verification authority boundary violated")
    expected = _digest_json(_body_without_digest(verification, "verification_sha256"))
    if verification["verification_sha256"] != expected:
        raise IterativeAuditError("Verification digest mismatch")
    return copy.deepcopy(dict(verification))


def make_decision_record(
    *,
    session_id: str,
    iteration_index: int,
    input_snapshot_sha256: str,
    output_snapshot_sha256: str,
    finding_ids: Sequence[str],
    neural_handoff_sha256: str | None,
    repair_sha256: str | None,
    verification_sha256: str | None,
    decision: str,
    reason_code: str,
    remaining_finding_ids: Sequence[str],
    lesson_codes: Sequence[str] = (),
    finding_context: Sequence[Mapping[str, str]] = (),
    repair_kind: str | None = None,
) -> dict[str, Any]:
    _require_id(session_id, "session identity")
    if type(iteration_index) is not int or iteration_index < 1 or iteration_index > MAX_ITERATIONS:
        raise IterativeAuditError("Invalid iteration index")
    _require_digest(input_snapshot_sha256, "input snapshot digest")
    _require_digest(output_snapshot_sha256, "output snapshot digest")
    ids = sorted(dict.fromkeys(_require_id(x, "finding identity") for x in finding_ids))
    remaining = sorted(dict.fromkeys(_require_id(x, "remaining finding identity") for x in remaining_finding_ids))
    if decision not in DECISIONS:
        raise IterativeAuditError("Unsupported decision")
    _require_id(reason_code, "decision reason code")
    if neural_handoff_sha256 is not None:
        _require_digest(neural_handoff_sha256, "neural handoff digest")
    if repair_sha256 is not None:
        _require_digest(repair_sha256, "repair digest")
    if verification_sha256 is not None:
        _require_digest(verification_sha256, "verification digest")
    lessons = sorted(dict.fromkeys(_require_id(x, "lesson code") for x in lesson_codes))
    if len(lessons) > MAX_LESSON_CODES:
        raise IterativeAuditError("Lesson-code budget exceeded")
    if repair_kind is not None and repair_kind not in REPAIR_KINDS:
        raise IterativeAuditError("Unsupported repair kind")
    contexts = []
    for item in finding_context:
        if not isinstance(item, Mapping) or set(item) != {"rule_id", "category"}:
            raise IterativeAuditError("Invalid decision finding context")
        contexts.append({
            "rule_id": _require_id(item["rule_id"], "decision rule identity"),
            "category": _require_id(item["category"], "decision finding category"),
        })
    contexts = sorted(set((item["rule_id"], item["category"]) for item in contexts))
    normalized_context = [{"rule_id": a, "category": b} for a, b in contexts]
    body = {
        "schema_version": DECISION_SCHEMA,
        "decision_id": _digest_json({
            "session_id": session_id,
            "iteration_index": iteration_index,
            "input_snapshot_sha256": input_snapshot_sha256,
            "output_snapshot_sha256": output_snapshot_sha256,
            "finding_ids": ids,
            "repair_sha256": repair_sha256,
            "verification_sha256": verification_sha256,
            "finding_context": normalized_context,
            "repair_kind": repair_kind,
            "decision": decision,
        })[:32],
        "session_id": session_id,
        "iteration_index": iteration_index,
        "input_snapshot_sha256": input_snapshot_sha256,
        "output_snapshot_sha256": output_snapshot_sha256,
        "finding_ids": ids,
        "neural_handoff_sha256": neural_handoff_sha256,
        "repair_sha256": repair_sha256,
        "verification_sha256": verification_sha256,
        "decision": decision,
        "reason_code": reason_code,
        "remaining_finding_ids": remaining,
        "lesson_codes": lessons,
        "finding_context": normalized_context,
        "repair_kind": repair_kind,
        "memory_scope": "non_authoritative_historical_guidance",
    }
    body["decision_sha256"] = _digest_json(body)
    return body


def validate_decision_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise IterativeAuditError("Decision record must be an object")
    allowed = {
        "schema_version", "decision_id", "session_id", "iteration_index",
        "input_snapshot_sha256", "output_snapshot_sha256", "finding_ids",
        "neural_handoff_sha256", "repair_sha256", "verification_sha256",
        "finding_context", "repair_kind", "decision", "reason_code", "remaining_finding_ids", "lesson_codes",
        "memory_scope", "decision_sha256",
    }
    if set(record) != allowed or record["schema_version"] != DECISION_SCHEMA:
        raise IterativeAuditError("Invalid decision record envelope")
    _require_id(record["decision_id"], "decision identity")
    _require_id(record["session_id"], "session identity")
    if type(record["iteration_index"]) is not int or not 1 <= record["iteration_index"] <= MAX_ITERATIONS:
        raise IterativeAuditError("Invalid decision iteration")
    _require_digest(record["input_snapshot_sha256"], "input snapshot digest")
    _require_digest(record["output_snapshot_sha256"], "output snapshot digest")
    if record["decision"] not in DECISIONS:
        raise IterativeAuditError("Unsupported decision")
    _require_id(record["reason_code"], "decision reason code")
    for key in ("neural_handoff_sha256", "repair_sha256", "verification_sha256"):
        if record[key] is not None:
            _require_digest(record[key], key)
    if record["repair_kind"] is not None and record["repair_kind"] not in REPAIR_KINDS:
        raise IterativeAuditError("Unsupported decision repair kind")
    contexts = record["finding_context"]
    if not isinstance(contexts, list) or len(contexts) > MAX_FINDINGS:
        raise IterativeAuditError("Invalid decision finding context")
    for item in contexts:
        if not isinstance(item, dict) or set(item) != {"rule_id", "category"}:
            raise IterativeAuditError("Invalid decision finding context entry")
        _require_id(item["rule_id"], "decision rule identity")
        _require_id(item["category"], "decision finding category")
    if contexts != sorted(contexts, key=lambda item: (item["rule_id"], item["category"])) or len(contexts) != len({(x["rule_id"], x["category"]) for x in contexts}):
        raise IterativeAuditError("Decision finding context must be unique and canonical")
    for key in ("finding_ids", "remaining_finding_ids", "lesson_codes"):
        if not isinstance(record[key], list):
            raise IterativeAuditError(f"Invalid {key}")
        if len(record[key]) > (MAX_LESSON_CODES if key == "lesson_codes" else MAX_FINDINGS):
            raise IterativeAuditError(f"{key} budget exceeded")
        for item in record[key]:
            _require_id(item, f"{key} identity")
        if len(record[key]) != len(set(record[key])) or record[key] != sorted(record[key]):
            raise IterativeAuditError(f"{key} must be canonical")
    if record["memory_scope"] != "non_authoritative_historical_guidance":
        raise IterativeAuditError("Decision memory authority boundary violated")
    expected_id = _digest_json({
        "session_id": record["session_id"],
        "iteration_index": record["iteration_index"],
        "input_snapshot_sha256": record["input_snapshot_sha256"],
        "output_snapshot_sha256": record["output_snapshot_sha256"],
        "finding_ids": record["finding_ids"],
        "repair_sha256": record["repair_sha256"],
        "verification_sha256": record["verification_sha256"],
        "finding_context": record["finding_context"],
        "repair_kind": record["repair_kind"],
        "decision": record["decision"],
    })[:32]
    if record["decision_id"] != expected_id:
        raise IterativeAuditError("Decision identity mismatch")
    expected = _digest_json(_body_without_digest(record, "decision_sha256"))
    if record["decision_sha256"] != expected:
        raise IterativeAuditError("Decision record digest mismatch")
    return copy.deepcopy(dict(record))


def start_session(
    snapshot: RepositorySnapshot,
    *,
    session_id: str,
    max_iterations: int = MAX_ITERATIONS,
) -> dict[str, Any]:
    _require_id(session_id, "session identity")
    if type(max_iterations) is not int or not 1 <= max_iterations <= MAX_ITERATIONS:
        raise IterativeAuditError("Invalid maximum iteration budget")
    body = {
        "schema_version": SESSION_SCHEMA,
        "session_id": session_id,
        "initial_snapshot_sha256": snapshot.snapshot_sha256,
        "current_snapshot_sha256": snapshot.snapshot_sha256,
        "max_iterations": max_iterations,
        "iteration_index": 0,
        "status": "active",
        "decision_ids": [],
        "authority": {
            "automatic_authoritative_checkout_mutation_permitted": False,
            "decision_memory_authorizes_repairs": False,
        },
    }
    body["session_sha256"] = _digest_json(body)
    return body


def _open_finding_ids(report: Mapping[str, Any]) -> set[str]:
    return {item["finding_id"] for item in report["findings"] if item["status"] == "open"}


def evaluate_iteration(
    *,
    session: Mapping[str, Any],
    snapshot: RepositorySnapshot,
    audit: Mapping[str, Any],
    handoff: Mapping[str, Any] | None,
    repair: Mapping[str, Any] | None,
    verification: Mapping[str, Any] | None,
    post_audit: Mapping[str, Any] | None,
    memory: "DecisionMemory | None" = None,
) -> dict[str, Any]:
    """Evaluate one bounded correction attempt.

    A repair is accepted only after:
      1. current audit is source-bound;
      2. AE-28 handoff is bound to the same repository snapshot;
      3. repair is bound to current findings;
      4. independent verification passes;
      5. post-repair audit no longer reports targeted findings as open.

    The returned snapshot is the new controller state only when all gates pass.
    No filesystem mutation occurs.
    """
    _validate_session(session, snapshot)
    current_audit = validate_audit_report(snapshot, audit)
    current_findings = {item["finding_id"]: item for item in current_audit["findings"]}
    open_ids = _open_finding_ids(current_audit)
    verified_handoff = (
        validate_neural_handoff(snapshot, handoff)
        if handoff is not None
        else None
    )

    iteration = session["iteration_index"] + 1
    if iteration > session["max_iterations"]:
        raise IterativeAuditError("Session iteration budget exhausted")
    finding_context = [
        {"rule_id": current_findings[item]["rule_id"], "category": current_findings[item]["category"]}
        for item in sorted(current_findings)
    ]

    if repair is None:
        decision = "defer"
        reason = "no_repair_proposal"
        record = make_decision_record(
            session_id=session["session_id"],
            iteration_index=iteration,
            input_snapshot_sha256=snapshot.snapshot_sha256,
            output_snapshot_sha256=snapshot.snapshot_sha256,
            finding_ids=sorted(open_ids),
            neural_handoff_sha256=(
                verified_handoff["handoff_sha256"] if verified_handoff is not None else None
            ),
            repair_sha256=None,
            verification_sha256=None,
            decision=decision,
            reason_code=reason,
            remaining_finding_ids=sorted(open_ids),
            lesson_codes=("no_repair_proposed",),
            finding_context=finding_context,
            repair_kind=None,
        )
        return _result(record, snapshot, current_audit, None, None, None, memory, input_snapshot=snapshot, handoff=verified_handoff)

    if verified_handoff is None:
        raise IterativeAuditError("A repair proposal requires a verified AE-28 neural handoff")

    normalized_repair = validate_repair(
        snapshot,
        repair,
        finding_ids=current_findings.keys(),
        finding_fingerprints={
            key: current_findings[key]["finding_fingerprint"]
            for key in current_findings
        },
    )
    if normalized_repair["neural_handoff_sha256"] != verified_handoff["handoff_sha256"]:
        raise IterativeAuditError("Repair is bound to a different neural handoff")
    if not set(normalized_repair["target_finding_ids"]) <= open_ids:
        raise IterativeAuditError("Repair must target currently open findings")

    candidate = snapshot.apply(normalized_repair)

    if verification is None:
        record = make_decision_record(
            session_id=session["session_id"],
            iteration_index=iteration,
            input_snapshot_sha256=snapshot.snapshot_sha256,
            output_snapshot_sha256=snapshot.snapshot_sha256,
            finding_ids=sorted(normalized_repair["target_finding_ids"]),
            neural_handoff_sha256=verified_handoff["handoff_sha256"],
            repair_sha256=normalized_repair["repair_sha256"],
            verification_sha256=None,
            decision="await_verification",
            reason_code="verification_required_before_state_change",
            remaining_finding_ids=sorted(open_ids),
            lesson_codes=("verification_gate_required",),
            finding_context=finding_context,
            repair_kind=normalized_repair["kind"],
        )
        return _result(record, snapshot, current_audit, normalized_repair, None, candidate, memory, input_snapshot=snapshot, handoff=verified_handoff)

    verified = validate_verification(snapshot, candidate, normalized_repair, verification)
    if verified["status"] != "passed":
        decision = "defer" if verified["status"] == "inconclusive" else "reject_repair"
        reason = "verification_inconclusive" if decision == "defer" else "verification_failed"
        record = make_decision_record(
            session_id=session["session_id"],
            iteration_index=iteration,
            input_snapshot_sha256=snapshot.snapshot_sha256,
            output_snapshot_sha256=snapshot.snapshot_sha256,
            finding_ids=sorted(normalized_repair["target_finding_ids"]),
            neural_handoff_sha256=verified_handoff["handoff_sha256"],
            repair_sha256=normalized_repair["repair_sha256"],
            verification_sha256=verified["verification_sha256"],
            decision=decision,
            reason_code=reason,
            remaining_finding_ids=sorted(open_ids),
            lesson_codes=("repair_verification_failed",) if decision == "reject_repair" else ("repair_verification_inconclusive",),
            finding_context=finding_context,
            repair_kind=normalized_repair["kind"],
        )
        return _result(record, snapshot, current_audit, normalized_repair, verified, candidate, memory, input_snapshot=snapshot, handoff=verified_handoff)

    if post_audit is None:
        record = make_decision_record(
            session_id=session["session_id"],
            iteration_index=iteration,
            input_snapshot_sha256=snapshot.snapshot_sha256,
            output_snapshot_sha256=snapshot.snapshot_sha256,
            finding_ids=sorted(normalized_repair["target_finding_ids"]),
            neural_handoff_sha256=verified_handoff["handoff_sha256"],
            repair_sha256=normalized_repair["repair_sha256"],
            verification_sha256=verified["verification_sha256"],
            decision="await_post_audit",
            reason_code="post_repair_audit_required_before_state_change",
            remaining_finding_ids=sorted(open_ids),
            lesson_codes=("post_repair_audit_required",),
            finding_context=finding_context,
            repair_kind=normalized_repair["kind"],
        )
        return _result(record, snapshot, current_audit, normalized_repair, verified, candidate, memory, input_snapshot=snapshot, handoff=verified_handoff)

    after_audit = validate_audit_report(candidate, post_audit)
    remaining_targeted = sorted(
        set(normalized_repair["target_finding_ids"]) & _open_finding_ids(after_audit)
    )
    if remaining_targeted:
        record = make_decision_record(
            session_id=session["session_id"],
            iteration_index=iteration,
            input_snapshot_sha256=snapshot.snapshot_sha256,
            output_snapshot_sha256=snapshot.snapshot_sha256,
            finding_ids=sorted(normalized_repair["target_finding_ids"]),
            neural_handoff_sha256=verified_handoff["handoff_sha256"],
            repair_sha256=normalized_repair["repair_sha256"],
            verification_sha256=verified["verification_sha256"],
            decision="reject_repair",
            reason_code="post_repair_audit_finding_persists",
            remaining_finding_ids=sorted(_open_finding_ids(after_audit)),
            lesson_codes=("post_audit_finding_persists",),
            finding_context=finding_context,
            repair_kind=normalized_repair["kind"],
        )
        return _result(record, snapshot, current_audit, normalized_repair, verified, candidate, memory,
                       input_snapshot=snapshot, handoff=verified_handoff,
                       post_audit=after_audit, candidate_rejected=True)

    decision = "accept_repair"
    reason = "verification_and_post_audit_passed"
    remaining = sorted(_open_finding_ids(after_audit))
    lessons = ("verified_repair", "post_audit_confirmed")
    if remaining:
        lessons = lessons + ("additional_findings_remain",)
    record = make_decision_record(
        session_id=session["session_id"],
        iteration_index=iteration,
        input_snapshot_sha256=snapshot.snapshot_sha256,
        output_snapshot_sha256=candidate.snapshot_sha256,
        finding_ids=sorted(normalized_repair["target_finding_ids"]),
        neural_handoff_sha256=verified_handoff["handoff_sha256"],
        repair_sha256=normalized_repair["repair_sha256"],
        verification_sha256=verified["verification_sha256"],
        decision=decision,
        reason_code=reason,
        remaining_finding_ids=remaining,
        lesson_codes=lessons,
        finding_context=finding_context,
        repair_kind=normalized_repair["kind"],
    )
    return _result(record, candidate, current_audit, normalized_repair, verified, candidate, memory,
                   input_snapshot=snapshot, handoff=verified_handoff,
                   post_audit=after_audit)


def _result(
    record: dict[str, Any],
    state: RepositorySnapshot,
    audit: Mapping[str, Any],
    repair: Mapping[str, Any] | None,
    verification: Mapping[str, Any] | None,
    candidate: RepositorySnapshot | None,
    memory: "DecisionMemory | None",
    *,
    input_snapshot: RepositorySnapshot,
    handoff: Mapping[str, Any] | None = None,
    post_audit: Mapping[str, Any] | None = None,
    candidate_rejected: bool = False,
) -> dict[str, Any]:
    if memory is not None:
        memory.add(record)
    return {
        "decision": record["decision"],
        "decision_record": record,
        "state_changed": record["output_snapshot_sha256"] != record["input_snapshot_sha256"],
        "input_snapshot": input_snapshot,
        "snapshot": state,
        "candidate_snapshot": candidate,
        "audit": copy.deepcopy(dict(audit)),
        "handoff": copy.deepcopy(dict(handoff)) if handoff is not None else None,
        "repair": copy.deepcopy(dict(repair)) if repair is not None else None,
        "verification": copy.deepcopy(dict(verification)) if verification is not None else None,
        "post_audit": copy.deepcopy(dict(post_audit)) if post_audit is not None else None,
        "candidate_rejected": candidate_rejected,
    }

def _validate_session(session: Mapping[str, Any], snapshot: RepositorySnapshot) -> None:
    if not isinstance(session, Mapping):
        raise IterativeAuditError("Session must be an object")
    allowed = {
        "schema_version", "session_id", "initial_snapshot_sha256",
        "current_snapshot_sha256", "max_iterations", "iteration_index",
        "status", "decision_ids", "authority", "session_sha256",
    }
    if set(session) != allowed or session["schema_version"] != SESSION_SCHEMA:
        raise IterativeAuditError("Invalid session envelope")
    _require_id(session["session_id"], "session identity")
    _require_digest(session["initial_snapshot_sha256"], "initial snapshot digest")
    if session["current_snapshot_sha256"] != snapshot.snapshot_sha256:
        raise IterativeAuditError("Session is stale for repository snapshot")
    if type(session["max_iterations"]) is not int or not 1 <= session["max_iterations"] <= MAX_ITERATIONS:
        raise IterativeAuditError("Invalid session iteration budget")
    if type(session["iteration_index"]) is not int or not 0 <= session["iteration_index"] <= session["max_iterations"]:
        raise IterativeAuditError("Invalid session iteration")
    if session["status"] not in {"active", "complete", "exhausted"}:
        raise IterativeAuditError("Invalid session status")
    if not isinstance(session["decision_ids"], list) or len(session["decision_ids"]) > MAX_DECISIONS:
        raise IterativeAuditError("Invalid session decision list")
    for ident in session["decision_ids"]:
        _require_id(ident, "decision identity")
    if len(set(session["decision_ids"])) != len(session["decision_ids"]):
        raise IterativeAuditError("Duplicate session decision")
    if session["authority"] != {
        "automatic_authoritative_checkout_mutation_permitted": False,
        "decision_memory_authorizes_repairs": False,
    }:
        raise IterativeAuditError("Session authority boundary violated")
    expected = _digest_json(_body_without_digest(session, "session_sha256"))
    if session["session_sha256"] != expected:
        raise IterativeAuditError("Session digest mismatch")


def _validate_transition_result(
    session: Mapping[str, Any],
    result: Mapping[str, Any],
) -> tuple[dict[str, Any], "RepositorySnapshot", "RepositorySnapshot | None"]:
    """Re-validate the complete controller result before sealing a session."""
    if not isinstance(result, Mapping):
        raise IterativeAuditError("Controller result must be an object")
    required = {
        "decision", "decision_record", "state_changed", "snapshot",
        "candidate_snapshot", "audit", "handoff", "repair", "verification",
        "post_audit", "candidate_rejected", "input_snapshot",
    }
    if set(result) != required:
        raise IterativeAuditError("Invalid controller result envelope")
    input_snapshot = result["input_snapshot"]
    if not isinstance(input_snapshot, RepositorySnapshot):
        raise IterativeAuditError("Controller result input snapshot is missing")
    if input_snapshot.snapshot_sha256 != session.get("current_snapshot_sha256"):
        raise IterativeAuditError("Controller result input snapshot is stale")
    if not isinstance(result["snapshot"], RepositorySnapshot):
        raise IterativeAuditError("Controller result snapshot is invalid")
    if result["candidate_snapshot"] is not None and not isinstance(
        result["candidate_snapshot"], RepositorySnapshot
    ):
        raise IterativeAuditError("Controller result candidate snapshot is invalid")

    record = validate_decision_record(result["decision_record"])
    if result["decision"] != record["decision"]:
        raise IterativeAuditError("Controller result decision mismatch")
    if record["session_id"] != session.get("session_id"):
        raise IterativeAuditError("Decision belongs to a different session")
    if record["iteration_index"] != session.get("iteration_index", 0) + 1:
        raise IterativeAuditError("Decision is not the next session iteration")
    if record["input_snapshot_sha256"] != input_snapshot.snapshot_sha256:
        raise IterativeAuditError("Decision input snapshot mismatch")
    if record["output_snapshot_sha256"] != result["snapshot"].snapshot_sha256:
        raise IterativeAuditError("Result snapshot does not match decision record")
    expected_state_changed = (
        record["output_snapshot_sha256"] != record["input_snapshot_sha256"]
    )
    if result["state_changed"] is not expected_state_changed:
        raise IterativeAuditError("Controller state-change flag mismatch")

    audit = validate_audit_report(input_snapshot, result["audit"])
    findings = {item["finding_id"]: item for item in audit["findings"]}
    open_ids = _open_finding_ids(audit)

    repair = result["repair"]
    handoff = result["handoff"]
    if repair is None:
        if result["candidate_snapshot"] is not None:
            raise IterativeAuditError("Candidate snapshot exists without repair")
        if handoff is not None:
            handoff = validate_neural_handoff(input_snapshot, handoff)
            if record["neural_handoff_sha256"] != handoff["handoff_sha256"]:
                raise IterativeAuditError("Decision and neural handoff mismatch")
        elif record["neural_handoff_sha256"] is not None:
            raise IterativeAuditError("Decision contains handoff binding without handoff")
        if record["repair_sha256"] is not None:
            raise IterativeAuditError("Decision contains repair binding without repair")
    else:
        repair = validate_repair(
            input_snapshot,
            repair,
            finding_ids=findings.keys(),
            finding_fingerprints={
                key: findings[key]["finding_fingerprint"] for key in findings
            },
        )
        if handoff is None:
            raise IterativeAuditError("Repair result is missing neural handoff")
        handoff = validate_neural_handoff(input_snapshot, handoff)
        if repair["neural_handoff_sha256"] != handoff["handoff_sha256"]:
            raise IterativeAuditError("Repair and neural handoff mismatch")
        if record["neural_handoff_sha256"] != handoff["handoff_sha256"]:
            raise IterativeAuditError("Decision and neural handoff mismatch")
        if record["repair_sha256"] != repair["repair_sha256"]:
            raise IterativeAuditError("Decision and repair mismatch")
        candidate = result["candidate_snapshot"]
        if candidate is None:
            raise IterativeAuditError("Repair result is missing candidate snapshot")
        expected_candidate = input_snapshot.apply(repair)
        if expected_candidate.snapshot_sha256 != candidate.snapshot_sha256:
            raise IterativeAuditError("Candidate snapshot does not match repair")

    verification = result["verification"]
    if verification is None:
        if record["verification_sha256"] is not None:
            raise IterativeAuditError("Decision contains verification binding without verification")
    else:
        if repair is None or result["candidate_snapshot"] is None:
            raise IterativeAuditError("Verification lacks repair candidate")
        verification = validate_verification(
            input_snapshot, result["candidate_snapshot"], repair, verification
        )
        if record["verification_sha256"] != verification["verification_sha256"]:
            raise IterativeAuditError("Decision and verification mismatch")

    post_audit = result["post_audit"]
    if post_audit is not None:
        if repair is None or result["candidate_snapshot"] is None:
            raise IterativeAuditError("Post-audit lacks candidate snapshot")
        post_audit = validate_audit_report(result["candidate_snapshot"], post_audit)

    decision = record["decision"]
    if decision == "accept_repair":
        if repair is None or verification is None or post_audit is None:
            raise IterativeAuditError("Accepted transition lacks complete repair evidence")
        if verification["status"] != "passed":
            raise IterativeAuditError("Accepted transition has non-passed verification")
        if result["candidate_rejected"]:
            raise IterativeAuditError("Accepted transition marks candidate rejected")
        if not result["state_changed"]:
            raise IterativeAuditError("Accepted repair must change controller state")
        targeted = set(repair["target_finding_ids"])
        if targeted & _open_finding_ids(post_audit):
            raise IterativeAuditError("Accepted repair leaves targeted finding open")
        if record["output_snapshot_sha256"] != result["candidate_snapshot"].snapshot_sha256:
            raise IterativeAuditError("Accepted transition output is not candidate state")
        if record["remaining_finding_ids"] != sorted(_open_finding_ids(post_audit)):
            raise IterativeAuditError("Accepted transition remaining findings mismatch")
    elif decision == "reject_repair":
        if result["state_changed"]:
            raise IterativeAuditError("Rejected transition changed controller state")
        if record["output_snapshot_sha256"] != input_snapshot.snapshot_sha256:
            raise IterativeAuditError("Rejected transition output mismatch")
        if result["candidate_rejected"]:
            if repair is None or post_audit is None:
                raise IterativeAuditError("Rejected candidate lacks post-audit")
            if not (set(repair["target_finding_ids"]) & _open_finding_ids(post_audit)):
                raise IterativeAuditError("Rejected candidate lacks persistent targeted finding")
    elif decision == "defer":
        if result["state_changed"]:
            raise IterativeAuditError("Deferred transition changed controller state")
        if record["output_snapshot_sha256"] != input_snapshot.snapshot_sha256:
            raise IterativeAuditError("Deferred transition output mismatch")
    elif decision == "await_verification":
        if repair is None or verification is not None or result["candidate_snapshot"] is None:
            raise IterativeAuditError("Await-verification transition is inconsistent")
        if result["state_changed"]:
            raise IterativeAuditError("Await-verification transition changed controller state")
    elif decision == "await_post_audit":
        if repair is None or verification is None or verification["status"] != "passed":
            raise IterativeAuditError("Await-post-audit transition lacks passed verification")
        if post_audit is not None:
            raise IterativeAuditError("Await-post-audit transition already has post-audit")
        if result["state_changed"]:
            raise IterativeAuditError("Await-post-audit transition changed controller state")
    else:
        raise IterativeAuditError("Unsupported controller transition")

    if record["remaining_finding_ids"] != (
        sorted(_open_finding_ids(post_audit)) if post_audit is not None
        and decision in {"accept_repair", "reject_repair"}
        else record["remaining_finding_ids"]
    ):
        raise IterativeAuditError("Decision remaining findings are inconsistent")
    return record, input_snapshot, result["snapshot"]


def advance_session(
    session: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal one fully revalidated decision into session state.

    The transition boundary rechecks the artifact chain produced by
    ``evaluate_iteration`` so a caller cannot manufacture a validly digested
    accept decision and bypass the repair/verification/post-audit gates.
    """
    if not isinstance(session, Mapping):
        raise IterativeAuditError("Session must be an object")
    if not isinstance(result, Mapping):
        raise IterativeAuditError("Controller result must be an object")
    input_snapshot = result.get("input_snapshot")
    if not isinstance(input_snapshot, RepositorySnapshot):
        raise IterativeAuditError("Controller result input snapshot is missing")
    _validate_session(session, input_snapshot)
    record, input_snapshot, output_snapshot = _validate_transition_result(session, result)

    decision_ids = list(session["decision_ids"]) + [record["decision_id"]]
    if len(decision_ids) > MAX_DECISIONS:
        raise IterativeAuditError("Session decision budget exceeded")

    current_digest = record["output_snapshot_sha256"]
    if record["decision"] == "accept_repair":
        status = "complete" if not record["remaining_finding_ids"] else "active"
    elif record["iteration_index"] >= session["max_iterations"]:
        status = "exhausted"
    else:
        status = "active"

    body = {
        "schema_version": SESSION_SCHEMA,
        "session_id": session["session_id"],
        "initial_snapshot_sha256": session["initial_snapshot_sha256"],
        "current_snapshot_sha256": current_digest,
        "max_iterations": session["max_iterations"],
        "iteration_index": record["iteration_index"],
        "status": status,
        "decision_ids": decision_ids,
        "authority": session["authority"],
    }
    body["session_sha256"] = _digest_json(body)
    return body

def _snapshot_stub(digest: str) -> RepositorySnapshot:
    # Session validation only needs a matching digest, but RepositorySnapshot
    # computes its digest from bytes. This helper is therefore intentionally
    # not used to authorize state changes; advance_session validates the result
    # snapshot independently. Kept private to avoid public fake-snapshot use.
    class Stub(RepositorySnapshot):
        @property
        def snapshot_sha256(self):  # type: ignore[override]
            return digest
    return Stub({})


class DecisionMemory:
    """Bounded, content-addressed historical decision store.

    Records are never interpreted as executable instructions or authorization.
    Retrieval is deterministic exact-key matching only.
    """

    def __init__(self, records: Sequence[Mapping[str, Any]] = ()) -> None:
        if len(records) > MAX_MEMORY_RECORDS:
            raise IterativeAuditError("Decision memory budget exceeded")
        self._records: list[dict[str, Any]] = []
        for record in records:
            self.add(record)

    @property
    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(self._records))

    def add(self, record: Mapping[str, Any]) -> None:
        normalized = validate_decision_record(record)
        if any(item["decision_id"] == normalized["decision_id"] for item in self._records):
            raise IterativeAuditError("Duplicate decision memory record")
        if len(self._records) >= MAX_MEMORY_RECORDS:
            raise IterativeAuditError("Decision memory budget exceeded")
        self._records.append(normalized)
        self._records.sort(key=lambda item: item["decision_id"])

    def recall(
        self,
        *,
        rule_id: str,
        category: str,
        repair_kind: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        _require_id(rule_id, "rule identity")
        _require_id(category, "finding category")
        if repair_kind is not None and repair_kind not in REPAIR_KINDS:
            raise IterativeAuditError("Unsupported repair kind")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise IterativeAuditError("Invalid memory retrieval limit")
        hits = []
        for record in self._records:
            # Exact-key retrieval is intentionally weak and deterministic. A
            # historical match is a planning hint, never a repair authorization.
            score = 0
            contexts = {(x["rule_id"], x["category"]) for x in record["finding_context"]}
            if (rule_id, category) in contexts:
                score += 5
            elif any(x[0] == rule_id for x in contexts):
                score += 3
            elif any(x[1] == category for x in contexts):
                score += 2
            if repair_kind and record["repair_kind"] == repair_kind:
                score += 2
            if score:
                hits.append({
                    "decision_id": record["decision_id"],
                    "decision": record["decision"],
                    "reason_code": record["reason_code"],
                    "lesson_codes": list(record["lesson_codes"]),
                    "repair_kind": record["repair_kind"],
                    "match_score": score,
                    "authority": "non_authoritative_historical_guidance",
                })
        hits.sort(key=lambda item: (-item["match_score"], item["decision_id"]))
        return hits[:limit]

    def learning_signal(
        self,
        *,
        rule_id: str,
        category: str,
        repair_kind: str,
    ) -> dict[str, Any]:
        hits = self.recall(rule_id=rule_id, category=category, repair_kind=repair_kind, limit=20)
        accepted = sum(item["decision"] == "accept_repair" for item in hits)
        rejected = sum(item["decision"] == "reject_repair" for item in hits)
        return {
            "rule_id": rule_id,
            "category": category,
            "repair_kind": repair_kind,
            "matched_decisions": len(hits),
            "accepted_repairs": accepted,
            "rejected_repairs": rejected,
            "recommendation": (
                "historical_pattern_supports_review"
                if hits else
                "no_historical_pattern"
            ),
            "authorization": {
                "may_authorize_repair": False,
                "may_modify_policy": False,
            },
            "matches": hits,
        }


def materialize_accepted_snapshot(
    snapshot: RepositorySnapshot,
    destination: str | os.PathLike[str],
) -> Path:
    """Materialize an already accepted snapshot into a new staging directory.

    This function never writes into the source checkout. Destination must not
    exist. The caller is responsible for deciding whether a later Git operation
    is appropriate.
    """
    if len(snapshot.files) > MAX_MATERIALIZE_FILES:
        raise IterativeAuditError("Materialization file-count budget exceeded")
    dest = Path(destination)
    if dest.exists() or dest.is_symlink():
        raise IterativeAuditError("Materialization destination must not already exist")
    parent = dest.parent
    if not parent.is_dir() or parent.is_symlink():
        raise IterativeAuditError("Materialization parent must be a real directory")
    cursor = parent
    while True:
        if cursor.is_symlink():
            raise IterativeAuditError("Materialization path contains a symlinked ancestor")
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    temp = Path(tempfile.mkdtemp(prefix=".ae29-stage-", dir=str(parent)))
    try:
        for path, data in snapshot.files.items():
            target = temp / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                raise IterativeAuditError("Materialization encountered symlink")
            with open(target, "xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temp, dest)
        return dest
    except Exception:
        import shutil
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _validate_external_replay_inputs(
    *,
    snapshot: RepositorySnapshot,
    audit: Mapping[str, Any],
    handoff: Mapping[str, Any],
    repair: Mapping[str, Any] | None,
) -> None:
    validate_audit_report(snapshot, audit)
    validate_neural_handoff(snapshot, handoff)
    if repair is not None:
        validate_repair(snapshot, repair)


__all__ = [
    "SESSION_SCHEMA",
    "FINDING_SCHEMA",
    "AUDIT_SCHEMA",
    "HANDOFF_SCHEMA",
    "REPAIR_SCHEMA",
    "VERIFICATION_SCHEMA",
    "DECISION_SCHEMA",
    "AE29_REPOSITORY_MANIFEST_ID",
    "MAX_ITERATIONS",
    "IterativeAuditError",
    "RepositorySnapshot",
    "DecisionMemory",
    "make_finding",
    "validate_finding",
    "make_audit_report",
    "validate_audit_report",
    "make_neural_handoff",
    "bind_ae28_interpretation",
    "validate_neural_handoff",
    "make_repair_proposal",
    "validate_repair",
    "make_verification",
    "validate_verification",
    "make_decision_record",
    "validate_decision_record",
    "start_session",
    "evaluate_iteration",
    "advance_session",
    "materialize_accepted_snapshot",
]

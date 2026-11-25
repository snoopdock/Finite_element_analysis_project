"""Freshness-guarded, append-only AE-32C result publication."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib, json, os, tempfile, time
from pathlib import Path
from typing import Any, Iterator, Mapping

SCHEMA = "ae32c/result-publication-state/v1"
RECORD_SCHEMA = "ae32c/immutable-run-result/v1"
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "INCOMPLETE"}

class PublicationError(RuntimeError):
    """Publication state or run record is invalid."""

def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()

def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def build_run_record(*, repository: str, source_revision: str, source_snapshot_id: str,
                     graph_snapshot_id: str, rule_registry_sha256: str,
                     finding_ledger_sha256: str, configuration_sha256: str,
                     workflow_run_id: int, run_number: int, run_attempt: int,
                     outcome: str) -> dict[str, Any]:
    if outcome not in TERMINAL:
        raise PublicationError("run_outcome_not_terminal")
    fields = (repository, source_revision, source_snapshot_id, graph_snapshot_id,
              rule_registry_sha256, finding_ledger_sha256, configuration_sha256)
    if any(not isinstance(x, str) or not x.strip() for x in fields):
        raise PublicationError("run_record_field_missing")
    if min(workflow_run_id, run_number, run_attempt) < 1:
        raise PublicationError("run_generation_invalid")
    payload = {"schema": RECORD_SCHEMA, "repository": repository,
        "source_revision": source_revision, "source_snapshot_id": source_snapshot_id,
        "graph_snapshot_id": graph_snapshot_id, "rule_registry_sha256": rule_registry_sha256,
        "finding_ledger_sha256": finding_ledger_sha256, "configuration_sha256": configuration_sha256,
        "workflow_run_id": workflow_run_id, "generation": [run_number, run_attempt],
        "outcome": outcome}
    return {**payload, "record_sha256": digest(payload)}

def verify_run_record(record: Mapping[str, Any]) -> None:
    payload = {k: v for k, v in record.items() if k != "record_sha256"}
    if record.get("schema") != RECORD_SCHEMA or record.get("record_sha256") != digest(payload):
        raise PublicationError("run_record_integrity_invalid")
    generation = record.get("generation")
    if not isinstance(generation, list) or len(generation) != 2 or any(not isinstance(x, int) or x < 1 for x in generation):
        raise PublicationError("run_generation_invalid")
    if record.get("outcome") not in TERMINAL:
        raise PublicationError("run_outcome_invalid")

def _empty(repository: str) -> dict[str, Any]:
    payload = {"schema": SCHEMA, "repository": repository, "last_generation": None, "current": None, "history": []}
    return {**payload, "state_sha256": digest(payload)}

def _verify_state(state: Mapping[str, Any], repository: str) -> None:
    payload = {k: v for k, v in state.items() if k != "state_sha256"}
    if state.get("schema") != SCHEMA or state.get("repository") != repository:
        raise PublicationError("publication_state_identity_invalid")
    if state.get("state_sha256") != digest(payload) or not isinstance(state.get("history"), list):
        raise PublicationError("publication_state_integrity_invalid")
    if state.get("current") is not None:
        verify_run_record(state["current"])

@contextmanager
def _lock(path: Path, timeout: float = 10.0) -> Iterator[None]:
    deadline = time.monotonic() + timeout
    while True:
        try:
            path.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise PublicationError("publication_lock_timeout")
            time.sleep(0.025)
    try:
        yield
    finally:
        try:
            path.rmdir()
        except FileNotFoundError:
            pass

def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def publish_result(state_path: str | Path, record: Mapping[str, Any], *,
                   authorized_source_revision: str, event_name: str = "push") -> dict[str, Any]:
    """Serialize updates; caller supplies a live authoritative source-ref SHA.

    Only successful push runs matching that SHA can advance current. All other
    outcomes are retained as history. State storage must be shared by publishers.
    """
    verify_run_record(record)
    if not authorized_source_revision:
        raise PublicationError("authorized_source_revision_missing")
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock(path.with_name(path.name + ".lock")):
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else _empty(str(record["repository"]))
        _verify_state(state, str(record["repository"]))
        generation, previous = record["generation"], state["last_generation"]
        decision, reason = "PUBLISHED", "fresh_successful_run"
        if event_name != "push":
            decision, reason = "HISTORICAL_ONLY", "event_not_authorized_for_current_publication"
        elif record["outcome"] != "SUCCEEDED":
            decision, reason = "HISTORICAL_ONLY", "run_not_successful"
        elif record["source_revision"] != authorized_source_revision:
            decision, reason = "HISTORICAL_ONLY", "source_revision_superseded_or_unverified"
        elif previous is not None and generation <= previous:
            decision, reason = "REJECTED", "generation_not_strictly_monotonic"
        next_state = {k: v for k, v in state.items() if k != "state_sha256"}
        next_state["history"] = [*state["history"], {"record": dict(record), "decision": decision, "reason": reason}]
        if decision == "PUBLISHED":
            next_state["current"], next_state["last_generation"] = dict(record), list(generation)
        next_state["state_sha256"] = digest(next_state)
        _atomic_write(path, canonical_bytes(next_state))
        return {"decision": decision, "reason": reason,
                "current_record_sha256": (next_state["current"] or {}).get("record_sha256"),
                "state_sha256": next_state["state_sha256"], "history_count": len(next_state["history"])}

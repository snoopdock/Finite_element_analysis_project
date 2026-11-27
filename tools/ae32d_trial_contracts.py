"""Allowlisted AE-32D task projection builder for A/B condition runners."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TASK_SCHEMA_PATH = ROOT / "evaluation" / "ae32d" / "sanitized-task-projection.schema.json"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _safe_repository_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def build_sanitized_task_projection(
    case_record: Mapping[str, Any], *, experiment_id: str, condition: str,
) -> dict[str, Any]:
    """Project only allowlisted fields; hidden benchmark fields are never read or copied."""
    if not isinstance(case_record, Mapping):
        raise TypeError("case_record_must_be_mapping")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id_required")
    if condition not in {"A_deterministic", "B_graph"}:
        raise ValueError("unsupported_deterministic_condition")
    source, task = case_record.get("source"), case_record.get("task")
    if not isinstance(source, Mapping) or not isinstance(task, Mapping):
        raise ValueError("case_source_and_task_required")
    repository, source_sha, fixture_path = (
        source.get("repository"), source.get("source_commit_sha"), source.get("fixture_path")
    )
    if not isinstance(repository, str) or not repository.strip():
        raise ValueError("source_repository_required")
    if not isinstance(source_sha, str) or not _SHA40.fullmatch(source_sha):
        raise ValueError("exact_lowercase_source_commit_sha_required")
    if not _safe_repository_path(fixture_path):
        raise ValueError("source_fixture_path_must_be_safe_relative_path")
    title, statement = task.get("title"), task.get("problem_statement")
    scope, constraints = task.get("declared_scope"), task.get("constraints", [])
    if not isinstance(title, str) or not title.strip():
        raise ValueError("task_title_required")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("task_problem_statement_required")
    if (not isinstance(scope, list) or not scope
            or any(not _safe_repository_path(path) for path in scope)
            or len(set(scope)) != len(scope)):
        raise ValueError("task_declared_scope_must_be_nonempty_unique_paths")
    if not isinstance(constraints, list) or any(not isinstance(item, str) for item in constraints):
        raise ValueError("task_constraints_must_be_strings")
    case_id = case_record.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id_required")
    source_projection = {"repository": repository, "source_commit_sha": source_sha, "fixture_path": fixture_path}
    task_projection = {"title": title, "problem_statement": statement, "declared_scope": list(scope), "constraints": list(constraints)}
    digest_payload = {"case_id": case_id, "source": source_projection, "task": task_projection}
    projection = {
        "schema_version": "ae32d/sanitized-task-projection/v1", "case_id": case_id,
        "source": source_projection, "task": task_projection, "experiment_id": experiment_id,
        "condition": condition, "task_contract_digest": sha256_json(digest_payload),
    }
    schema = json.loads(TASK_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(projection)
    return projection

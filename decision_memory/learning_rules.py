"""Conservative, read-only verification for proposed SAT learning rules.

G3.4.17 is a candidate-memory layer, not an autonomous decision or promotion
mechanism. Validation never turns observed contract-test success into evidence
of engineering impact. It performs no filesystem writes unless --output is
explicitly requested by an operator.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = "decision-learning-rule/v1"
REQUIRED_RULE_FIELDS = [
    "id", "schema_version", "status", "statement", "applicability",
    "sources", "observations", "limitations", "evidence_assessment", "review",
]
SUPPORTED_BASIS = {"contract_validation_only", "human_hypothesis"}
_ID = re.compile(r"^RULE-G[0-9]+(?:\.[0-9]+)+-[0-9]{3,}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class RuleValidationError(ValueError):
    """An unsafe, incomplete, or semantically unsupported candidate rule."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict:
    mapping = {}
    for key, value in node.value:
        k = loader.construct_object(key)
        if not isinstance(k, str) or k in mapping:
            raise RuleValidationError(f"Duplicate or non-string YAML key: {k!r}")
        mapping[k] = loader.construct_object(value)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise RuleValidationError(f"{label} must be a mapping")
    return value


def _fields(obj: dict, required: list[str], optional: list[str], label: str) -> None:
    missing = set(required).difference(obj)
    unknown = set(obj).difference(required).difference(optional)
    if missing or unknown:
        raise RuleValidationError(f"{label}: missing={sorted(missing)} unknown={sorted(unknown)}")


def _string(value: Any, label: str, min_length: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < min_length:
        raise RuleValidationError(f"{label} must be a nonempty string")
    return value


def _ids(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x.strip() for x in value):
        raise RuleValidationError(f"{label} must be a nonempty list of identifiers")
    if len(value) != len(set(value)):
        raise RuleValidationError(f"{label} must not contain duplicates")
    return value


def _read_yaml(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise RuleValidationError(f"Unsafe or missing record: {path}")
    try:
        return _object(yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader), str(path))
    except (yaml.YAMLError, UnicodeError) as exc:
        raise RuleValidationError(f"Invalid YAML {path}: {exc}") from exc


def _collection(root: Path, subdir: str) -> dict[str, dict]:
    directory = root / "decision_memory" / subdir
    if directory.is_symlink() or not directory.is_dir():
        raise RuleValidationError(f"Missing or unsafe decision-memory directory: {subdir}")
    found = {}
    for path in sorted(directory.iterdir()):
        if path.suffix not in {".yaml", ".yml"}:
            continue
        record = _read_yaml(path)
        ident = _string(record.get("id"), f"{subdir}.id")
        if ident != path.stem or ident in found:
            raise RuleValidationError(f"Filename/ID mismatch or duplicate: {path}")
        found[ident] = record
    return found


def _schema(root: Path) -> dict:
    path = root / "decision_memory" / "learning_rule_schema.json"
    if path.is_symlink() or not path.is_file():
        raise RuleValidationError("Missing or unsafe decision_memory/learning_rule_schema.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        config = _object(value, "schema")
        if config.get("schema_version") != SCHEMA_VERSION:
            raise RuleValidationError("Unsupported learning-rule schema version")
        for key in ["required_fields", "allowed_statuses", "allowed_basis_kinds"]:
            _ids(config.get(key), f"schema.{key}")
        if config.get("required_fields") != REQUIRED_RULE_FIELDS:
            raise RuleValidationError("Unsupported or weakened required-field contract")
        if set(config.get("allowed_basis_kinds", [])) != SUPPORTED_BASIS:
            raise RuleValidationError("Unsupported or weakened evidence-basis contract")
        if config.get("allowed_statuses") != ["candidate"]:
            raise RuleValidationError("This milestone supports candidate rules only")
        return config
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, RuleValidationError):
            raise
        raise RuleValidationError(f"Invalid rule schema: {exc}") from exc


def verify_candidate(rule: dict, root: Path, schema: dict, graph: dict[str, dict[str, dict]]) -> dict:
    rule = _object(rule, "rule")
    required = schema["required_fields"]
    _fields(rule, required, [], "rule")
    rule_id = _string(rule["id"], "id")
    if not _ID.fullmatch(rule_id):
        raise RuleValidationError("Invalid rule ID format")
    if rule["schema_version"] != SCHEMA_VERSION:
        raise RuleValidationError("Rule schema version mismatch")
    if rule["status"] not in schema["allowed_statuses"]:
        raise RuleValidationError("Rule cannot be promoted or activated by this subsystem")
    _string(rule["statement"], "statement", 20)
    _string(rule["applicability"], "applicability", 10)
    _ids(rule["observations"], "observations")
    _ids(rule["limitations"], "limitations")

    refs = _object(rule["sources"], "sources")
    _fields(refs, ["decision_ids", "action_ids", "outcome_ids", "validation_reports"], [], "sources")
    decision_ids = _ids(refs["decision_ids"], "decision_ids")
    action_ids = _ids(refs["action_ids"], "action_ids")
    outcome_ids = _ids(refs["outcome_ids"], "outcome_ids")
    for label, values, items in [
        ("decision", decision_ids, graph["decisions"]),
        ("action", action_ids, graph["actions"]),
        ("outcome", outcome_ids, graph["outcomes"]),
    ]:
        for item in values:
            if item not in items:
                raise RuleValidationError(f"Dangling {label} reference: {item}")
    for action_id in action_ids:
        action_decisions = graph["actions"][action_id].get("decision_refs", [])
        if not isinstance(action_decisions, list) or not set(decision_ids).intersection(action_decisions):
            raise RuleValidationError(f"Action {action_id} does not cite a declared decision")

    reports = refs["validation_reports"]
    if not isinstance(reports, list) or not reports:
        raise RuleValidationError("validation_reports must be a nonempty list")
    for item in reports:
        entry = _object(item, "validation_report")
        _fields(entry, ["profile_id", "report_sha256", "source_commit_sha"], [], "validation_report")
        profile_id = _string(entry["profile_id"], "validation_report.profile_id")
        if not re.fullmatch(r"G[0-9]+(?:\.[0-9]+)+", profile_id):
            raise RuleValidationError("Invalid profile identifier")
        profile_file = root / "validation" / "profiles" / (profile_id + ".yaml")
        profile_record = _read_yaml(profile_file)
        if profile_record.get("id") != profile_id:
            raise RuleValidationError(f"Profile identity mismatch: {profile_id}")
        if not isinstance(entry["report_sha256"], str) or not _SHA.fullmatch(entry["report_sha256"]):
            raise RuleValidationError("Invalid report SHA-256")
        if not isinstance(entry["source_commit_sha"], str) or not _COMMIT.fullmatch(entry["source_commit_sha"]):
            raise RuleValidationError("Invalid source commit SHA")

    for oid in outcome_ids:
        outcome = graph["outcomes"][oid]
        linked = outcome.get("action_id", [])
        linked = [linked] if isinstance(linked, str) else linked
        if not isinstance(linked, list) or not set(linked).intersection(action_ids):
            raise RuleValidationError(f"Outcome {oid} is not linked to a declared action")

    assessment = _object(rule["evidence_assessment"], "evidence_assessment")
    _fields(assessment, ["basis_kind", "engineering_impact_verified", "external_bundle_checked", "discrepancies"], [], "evidence_assessment")
    if assessment["basis_kind"] not in schema["allowed_basis_kinds"]:
        raise RuleValidationError("Unsupported evidence basis")
    if assessment["engineering_impact_verified"] is not False:
        raise RuleValidationError("G3.4.17 does not verify real-world engineering outcomes")
    if assessment["external_bundle_checked"] is not False:
        raise RuleValidationError("A referenced digest is not an independently checked live archive")
    discrepancies = assessment["discrepancies"]
    if not isinstance(discrepancies, list) or any(not isinstance(x, str) for x in discrepancies) or len(set(discrepancies)) != len(discrepancies):
        raise RuleValidationError("discrepancies must be unique string codes")

    conflict = False
    for action_id in action_ids:
        status = graph["actions"][action_id].get("outcome", {}).get("status")
        if status == "pending":
            for outcome_id in outcome_ids:
                outcome = graph["outcomes"][outcome_id]
                linked = outcome.get("action_id", [])
                linked = [linked] if isinstance(linked, str) else linked
                if action_id in linked and outcome.get("result", {}).get("status") == "successful":
                    conflict = True
    if conflict and "pending_action_with_successful_feedback" not in discrepancies:
        raise RuleValidationError("Unacknowledged pending-action/successful-feedback discrepancy")

    review = _object(rule["review"], "review")
    _fields(review, ["human_review_required", "approved", "reason"], [], "review")
    if review["human_review_required"] is not True or review["approved"] is not False:
        raise RuleValidationError("Unreviewed candidate must require human review and remain unapproved")
    _string(review["reason"], "review.reason", 10)
    return {
        "rule_id": rule_id,
        "status": "candidate",
        "source_decisions": decision_ids,
        "source_actions": action_ids,
        "source_outcomes": outcome_ids,
        "source_validation_profiles": [e["profile_id"] for e in reports],
        "source_validation_report_sha256": [e["report_sha256"] for e in reports],
        "source_validation_commits": [e["source_commit_sha"] for e in reports],
        "conflicts_acknowledged": discrepancies,
        "eligible_for_automatic_sat_execution": False,
        "evidence_limit": "Schema/contract validation is not proof of engineering effectiveness",
    }


def inspect_repository(repository: Path) -> dict:
    root = Path(repository).resolve(strict=True)
    schema = _schema(root)
    graph = {key: _collection(root, key) for key in ("decisions", "actions", "outcomes", "rules")}
    if not graph["rules"]:
        raise RuleValidationError("No learning-rule candidates found")
    result = [verify_candidate(r, root, schema, graph) for r in graph["rules"].values()]
    return {"schema_version": SCHEMA_VERSION, "status": "candidate_only", "rules": sorted(result, key=lambda v:v["rule_id"])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only inspection of candidate learning rules")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", help="Optional JSON audit summary output")
    args = parser.parse_args()
    try:
        report = inspect_repository(Path(args.repository))
        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            target = Path(args.output)
            if target.is_symlink():
                raise RuleValidationError("Refusing to overwrite symlinked output")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
    except (RuleValidationError, FileNotFoundError, OSError) as exc:
        parser.exit(status=2, message=f"Rule validation error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

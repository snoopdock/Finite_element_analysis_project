"""Validate the AE-32D deterministic rule catalog without executing any rule."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "evaluation" / "ae32d" / "deterministic-rule-catalog.json"
SCHEMA_PATH = ROOT / "evaluation" / "ae32d" / "deterministic-rule-catalog.schema.json"


def validate_catalog() -> dict:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(catalog)
    rule_ids = [rule["rule_id"] for rule in catalog["rules"]]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("duplicate_rule_id")
    seen_fixtures = set()
    for rule in catalog["rules"]:
        for fixture in rule["exercise_fixtures"]:
            path = PurePosixPath(fixture["path"])
            if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                raise ValueError("unsafe_fixture_path")
            key = (fixture["source_commit_sha"], path.as_posix(), fixture["exercise"])
            if key in seen_fixtures:
                raise ValueError("duplicate_rule_fixture_reference")
            seen_fixtures.add(key)
    return {
        "status": "valid_specification_only",
        "rule_count": len(rule_ids),
        "rule_ids": sorted(rule_ids),
        "fixture_reference_count": len(seen_fixtures),
        "ground_truth_read_allowed": False,
        "primary_benchmark_promotion_allowed": False,
        "rules_executed": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate AE-32D deterministic rule catalog")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    report = validate_catalog()
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

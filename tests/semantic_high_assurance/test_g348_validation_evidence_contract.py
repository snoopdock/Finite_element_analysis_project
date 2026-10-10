"""Branch-side validation contract tests for G3.4.8 (not placeholder assertions)."""
import json
from pathlib import Path
import re

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def test_g348_profile_conforms_to_branch_schema():
    schema = json.loads((ROOT / "validation/schema.json").read_text(encoding="utf-8"))
    profile = yaml.safe_load((ROOT / "validation/profiles/G3.4.8.yaml").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(profile)
    assert profile["id"] == "G3.4.8"
    assert profile["regression"]["enabled"] is True
    assert (ROOT / profile["regression"]["path"]).is_dir()


def test_all_profile_targets_exist_under_tests_without_traversal():
    for profile_path in (ROOT / "validation/profiles").glob("G*.yaml"):
        data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not re.fullmatch(r"G\d+(?:\.\d+)+", profile_path.stem):
            continue
        for target in data.get("target_tests", []):
            path = Path(target)
            assert path.parts[0] == "tests" and not path.is_absolute()
            assert ".." not in path.parts
            assert (ROOT / path).resolve().is_relative_to((ROOT / "tests").resolve())
            assert (ROOT / path).exists(), f"Missing target in {profile_path.name}: {target}"


def test_evidence_profile_declares_actual_pytest_targets():
    p = yaml.safe_load((ROOT / "validation/profiles/G3.4.8.yaml").read_text())
    assert len(p["target_tests"]) >= 1
    assert all((ROOT / t).suffix == ".py" for t in p["target_tests"])

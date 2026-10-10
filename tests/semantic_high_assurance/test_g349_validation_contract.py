"""G3.4.9 development-branch policy and validation profile tests."""
from pathlib import Path
import json
import re
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "validation/profiles/G3.4.9.yaml"


def test_g349_profile_matches_branch_schema():
    schema = json.loads((ROOT / "validation/schema.json").read_text(encoding="utf-8"))
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(profile)
    assert profile["id"] == PROFILE.stem
    assert profile["name"]


def test_g349_targets_are_real_regular_tests_beneath_repository():
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    assert profile["target_tests"]
    for candidate in profile["target_tests"]:
        path = Path(candidate)
        assert not path.is_absolute() and ".." not in path.parts
        assert path.parts[0] == "tests"
        assert path.suffix == ".py"
        target = ROOT / path
        assert target.exists() and target.is_file()
        assert not any((ROOT / Path(*path.parts[:index])).is_symlink()
                       for index in range(1, len(path.parts) + 1))
        assert target.resolve().is_relative_to((ROOT / "tests").resolve())


def test_g349_declares_full_regression():
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    regression = profile["regression"]
    assert regression["enabled"] is True
    assert (ROOT / regression["path"]).resolve() == (ROOT / "tests").resolve()
    assert (ROOT / regression["path"]).is_dir()


def test_validation_profile_versioning_is_unambiguous():
    folder = ROOT / "validation/profiles"
    ids = []
    for path in folder.glob("G*.yaml"):
        match = re.fullmatch(r"G\d+(?:\.\d+)+", path.stem)
        if match:
            ids.append(tuple(int(part) for part in path.stem[1:].split(".")))
    assert len(ids) == len(set(ids))
    assert (3, 4, 9) in ids

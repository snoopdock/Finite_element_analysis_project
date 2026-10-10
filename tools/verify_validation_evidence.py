"""Independent verification of manual validation evidence and observed pytest outcomes.

The detached digest establishes *self-consistency*, not authenticity. Passing
--repository/--engine-repository/--expected-* binds a report to the checked-out
source, engine, and GitHub Actions run context during the trusted workflow.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import yaml

_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{40,64}\Z")
_PROFILE_RE = re.compile(r"G\d+(?:\.\d+)+\Z")
_ALLOWED_STAGES = ("targeted", "regression")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _regular_file(root: Path, name: str) -> Path:
    _require(isinstance(name, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name))
             and name not in (".", ".."), "Unsafe evidence filename")
    path = root / name
    _require(path.is_file() and not path.is_symlink() and
             path.resolve().parent == root, f"Missing or unsafe evidence file: {name}")
    return path


def _check_file_record(root: Path, record: dict, *, expected_name: str | None = None) -> Path:
    _require(isinstance(record, dict), "Invalid file record")
    name = record.get("path")
    if expected_name is not None:
        _require(name == expected_name, f"Unexpected evidence file: {name}")
    path = _regular_file(root, name)
    digest = record.get("sha256")
    _require(isinstance(digest, str) and _DIGEST_RE.fullmatch(digest) is not None,
             "Invalid declared artifact SHA-256")
    size = record.get("size_bytes")
    _require(type(size) is int and size >= 0 and size == path.stat().st_size,
             f"Artifact size mismatch: {name}")
    _require(sha256_file(path) == digest, f"Artifact digest mismatch: {name}")
    return path


def _counts_from_junit(path: Path) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = list(root)
        _require(all(s.tag == "testsuite" for s in suites), "Unexpected JUnit XML child")
    else:
        raise ValueError("Unexpected JUnit XML root")
    _require(bool(suites), "JUnit XML has no test suites")
    totals = dict.fromkeys(("tests", "failures", "errors", "skipped"), 0)
    actual = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for field in totals:
            token = suite.attrib.get(field)
            _require(token is not None and re.fullmatch(r"\d+", token) is not None,
                     f"Missing/invalid JUnit {field}")
            totals[field] += int(token)
        cases = list(suite.iter("testcase"))
        actual["tests"] += len(cases)
        for case in cases:
            for label in ("failures", "errors", "skipped"):
                tag = {"failures": "failure", "errors": "error", "skipped": "skipped"}[label]
                actual[label] += len(case.findall(tag))
    _require(totals == actual, "JUnit suite counts disagree with testcase outcomes")
    _require(totals["tests"] > 0, "Zero-test evidence cannot count as validated")
    _require(totals["failures"] + totals["errors"] + totals["skipped"] <= totals["tests"],
             "JUnit outcomes exceed test count")
    return totals


def _git_commit(root: Path) -> str:
    output = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
    _require(output.returncode == 0 and _SHA_RE.fullmatch(output.stdout.strip()) is not None,
             f"Cannot establish checkout commit: {root}")
    return output.stdout.strip()


def _checked_out_profile(root: Path, report: dict) -> dict:
    profile_id = report.get("profile_id")
    _require(isinstance(profile_id, str) and _PROFILE_RE.fullmatch(profile_id) is not None,
             "Invalid profile identifier")
    matches = [root / "validation" / "profiles" / (profile_id + ext)
               for ext in (".yaml", ".yml")]
    matches = [f for f in matches if f.exists() or f.is_symlink()]
    _require(len(matches) == 1 and matches[0].is_file() and not matches[0].is_symlink(),
             "Profile missing or ambiguous in target checkout")
    f = matches[0]
    _require(sha256_file(f) == report.get("profile_sha256"), "Profile digest mismatch")
    # Bound to git commit, not only potentially modified worktree bytes.
    relative = f.relative_to(root).as_posix()
    git_content = subprocess.run(["git", "-C", str(root), "show",
                                  f"{report['target_commit_sha']}:{relative}"],
                                 capture_output=True, check=False)
    _require(git_content.returncode == 0 and
             hashlib.sha256(git_content.stdout).hexdigest() == report.get("profile_sha256"),
             "Profile does not match committed content")
    requested = report.get("requested_profile")
    if requested == "latest":
        available = []
        for item in (root / "validation/profiles").iterdir():
            if item.suffix in (".yaml", ".yml") and _PROFILE_RE.fullmatch(item.stem):
                available.append((tuple(int(x) for x in item.stem[1:].split(".")), item.stem))
        _require(available and max(available)[1] == profile_id,
                 "Reported latest profile is not newest numeric version")
    else:
        _require(requested == profile_id, "Requested and executed profiles differ")
    profile = yaml.safe_load(f.read_text(encoding="utf-8"))
    _require(isinstance(profile, dict) and profile.get("id") == profile_id, "Profile content invalid")
    tests = profile.get("target_tests")
    _require(isinstance(tests, list) and bool(tests) and all(isinstance(t, str) for t in tests),
             "Profile test targets invalid")
    return profile


def _check_argv(stage: str, argv: object, report: dict, profile: dict) -> None:
    _require(isinstance(argv, list) and all(isinstance(arg, str) for arg in argv),
             f"Invalid {stage} command record")
    targets = (profile["target_tests"] if stage == "targeted" else
               [Path(profile.get("regression", {}).get("path", "tests/")).as_posix()])
    _require(len(argv) == len(targets) + 6 and argv[:2] == ["-m", "pytest"] and
             argv[2:2 + len(targets)] == targets and
             argv[-4:-1] == ["-q", "-ra", "--junitxml"] and
             Path(argv[-1]).name == stage + ".xml",
             f"Command does not match declared {stage} test targets")


def _check_stage(stage: str, entry: dict, root: Path, profile: dict | None) -> None:
    _require(isinstance(entry, dict), f"Invalid {stage} result")
    status = entry.get("status")
    _require(status in ("passed", "failed", "error", "timeout", "not_run"),
             f"Invalid {stage} status")
    if status == "not_run":
        _require(stage == "regression" and not any(k in entry for k in ("exit_code", "junit", "log", "counts")),
                 "Invalid not_run stage")
        return
    _check_file_record(root, entry.get("log"), expected_name=stage + ".log")
    exit_code = entry.get("exit_code")
    _require((type(exit_code) is int or exit_code is None), "Invalid exit code")
    if profile is not None:
        _check_argv(stage, entry.get("argv"), {}, profile)
    if status == "passed":
        _require(exit_code == 0, "Successful result requires zero exit code")
    if status == "failed":
        _require(exit_code is not None and exit_code != 0 or entry.get("error") is not None,
                 "Failed stage has no failure explanation")
    if status == "timeout":
        _require(exit_code is None, "Timeout stage must lack exit code")
    junit = entry.get("junit")
    if junit is None:
        _require(status != "passed", "Passed stage lacks JUnit evidence")
        _require("counts" not in entry, "Counts reported without JUnit")
        return
    xml = _check_file_record(root, junit, expected_name=stage + ".xml")
    actual = _counts_from_junit(xml)
    _require(entry.get("counts") == actual, f"JUnit and report counts disagree: {stage}")
    if status == "passed":
        _require(actual["failures"] == actual["errors"] == 0 and
                 actual["skipped"] < actual["tests"],
                 f"{stage} claims pass despite failing or entirely skipped suite")
    elif status == "failed" and exit_code == 0:
        # Runners are permitted to invalidate a successful process if JUnit violates policy.
        _require(actual["failures"] or actual["errors"] or actual["skipped"] == actual["tests"],
                 "Failed stage has no detectable failed test/policy violation")


def verify(evidence: Path, *, require_pass: bool = False,
           repository: Path | None = None, engine_repository: Path | None = None,
           expected_branch: str | None = None, expected_run_id: str | None = None,
           expected_run_attempt: str | None = None,
           require_engine_tests: bool = False) -> dict:
    root = evidence.resolve(strict=True)
    _require(root.is_dir(), "Evidence directory missing")
    report_file = _regular_file(root, "validation_report.json")
    checksum = _regular_file(root, "validation_report.sha256")
    text = checksum.read_text(encoding="utf-8").strip()
    m = re.fullmatch(r"([0-9a-f]{64})  validation_report\.json", text)
    _require(m is not None and sha256_file(report_file) == m.group(1),
             "Report digest mismatch or invalid detached digest")
    report = json.loads(report_file.read_text(encoding="utf-8"))
    _require(isinstance(report, dict) and report.get("schema_version") in ("1.0", "1.1"),
             "Unsupported evidence schema version")
    _require(report.get("status") in ("passed", "failed", "error"), "Invalid summary status")
    results = report.get("results")
    _require(isinstance(results, dict) and set(results).issubset(_ALLOWED_STAGES),
             "Invalid results")
    for stamp in ("started_at", "finished_at"):
        ts = report.get(stamp)
        _require(isinstance(ts, str) and datetime.fromisoformat(ts).tzinfo is not None,
                 f"Invalid timestamp: {stamp}")
    _require(datetime.fromisoformat(report["started_at"]) <=
             datetime.fromisoformat(report["finished_at"]), "Inverted timestamps")
    if expected_branch is not None:
        _require(report.get("target_branch") == expected_branch, "Target branch mismatch")
    if expected_run_id is not None:
        _require(report.get("github_run_id") == expected_run_id, "GitHub run ID mismatch")
    if expected_run_attempt is not None:
        _require(report.get("github_run_attempt") == expected_run_attempt,
                 "GitHub run attempt mismatch")
    for path_arg, field in ((repository, "target_commit_sha"),
                            (engine_repository, "engine_commit_sha")):
        if path_arg is not None:
            root_path = Path(path_arg).resolve(strict=True)
            _require(_git_commit(root_path) == report.get(field), f"{field} mismatch")
    unit = report.get("engine_unit_tests")
    if require_engine_tests:
        _require(isinstance(unit, dict), "Missing engine unit-test provenance")
    if unit is not None:
        _require(isinstance(unit, dict) and unit.get("status") == "passed" and
                 type(unit.get("count")) is int and unit["count"] > 0,
                 "Invalid engine unit-test outcome")
        unit_log = _check_file_record(root, unit.get("log"), expected_name="engine-unit-tests.log")
        contents = unit_log.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"(?m)^Ran (\d+) tests? in ", contents)
        _require(match is not None and int(match.group(1)) == unit["count"] and
                 re.search(r"(?m)^OK\s*$", contents) is not None,
                 "Engine unit-test log lacks matching successful unittest summary")
    profile = _checked_out_profile(Path(repository).resolve(strict=True), report) if (
        repository is not None and report.get("profile_id") is not None) else None
    for name, entry in results.items():
        _check_stage(name, entry, root, profile)
    if report["status"] == "passed":
        _require(set(results) == set(_ALLOWED_STAGES), "Passed report lacks complete test stages")
        _require(results["targeted"]["status"] == "passed" and
                 results["regression"]["status"] in ("passed", "not_run"),
                 "Passed report conflicts with stage results")
        _require(report.get("error") is None and report.get("profile_id") is not None,
                 "Passed report contains error or missing profile")
        mode = report.get("regression_mode")
        _require(mode in ("profile", "skip", "force"), "Invalid regression mode")
        if profile is not None:
            desired = mode == "force" or (mode == "profile" and
                      profile.get("regression", {}).get("enabled", False))
            _require((results["regression"]["status"] == "passed") == desired,
                     "Regression execution contradicts selected profile/mode")
    elif report["status"] == "failed":
        _require(any(v["status"] not in ("passed", "not_run") for v in results.values()),
                 "Failed report contains no failing stage")
    else:
        _require(isinstance(report.get("error"), str) and bool(report["error"]),
                 "Error report lacks reason")
    if require_pass:
        _require(report["status"] == "passed", f"Tests did not pass: {report['status']}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--require-pass", action="store_true")
    parser.add_argument("--repository")
    parser.add_argument("--engine-repository")
    parser.add_argument("--expected-branch")
    parser.add_argument("--expected-run-id")
    parser.add_argument("--expected-run-attempt")
    parser.add_argument("--require-engine-tests", action="store_true")
    args = parser.parse_args()
    try:
        info = verify(Path(args.evidence_dir), require_pass=args.require_pass,
                      repository=Path(args.repository) if args.repository else None,
                      engine_repository=Path(args.engine_repository) if args.engine_repository else None,
                      expected_branch=args.expected_branch, expected_run_id=args.expected_run_id,
                      expected_run_attempt=args.expected_run_attempt,
                      require_engine_tests=args.require_engine_tests)
    except (ValueError, OSError, KeyError, json.JSONDecodeError, ET.ParseError) as exc:
        print(f"Evidence invalid: {exc}", file=sys.stderr)
        return 1
    print(f"Evidence verified (integrity + outcomes): {info['status']}, "
          f"profile={info['profile_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Manual validation engine: execute declared pytest targets and bind evidence to results.

The dispatcher uses two checkouts: a trusted engine from main and a target
branch. The target branch's profiles describe what to validate; they are not
interpreted as shell or arbitrary Python commands.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import yaml
from jsonschema import Draft202012Validator

PROFILE_RE = re.compile(r"G(?:\d+)(?:\.\d+)+\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(data: object) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def read_commit(path: Path) -> str | None:
    p = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                       capture_output=True, text=True, check=False)
    sha = p.stdout.strip()
    return sha if p.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", sha) else None


def _is_safe_regular_file(path: Path, anchor: Path) -> bool:
    # Check path components so a symlink to another in-tree location is rejected.
    try:
        relative = path.relative_to(anchor)
    except ValueError:
        return False
    cursor = anchor
    for component in relative.parts:
        cursor = cursor / component
        if cursor.is_symlink():
            return False
    return path.is_file() and path.resolve().is_relative_to(anchor.resolve())


def discover_profile(root: Path, requested: str) -> Path:
    folder = root / "validation" / "profiles"
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("Validation profiles directory missing or unsafe")
    if requested == "latest":
        candidates = [f for f in folder.iterdir()
                      if f.suffix in (".yaml", ".yml")
                      and PROFILE_RE.fullmatch(f.stem)]
        if not candidates:
            raise ValueError("No versioned validation profiles found")
        versions = {}
        for f in candidates:
            if not _is_safe_regular_file(f, folder):
                raise ValueError(f"Unsafe profile: {f.name}")
            version = tuple(map(int, f.stem[1:].split(".")))
            if version in versions:
                raise ValueError(f"Ambiguous duplicate profile version: {f.stem}")
            versions[version] = f
        return versions[max(versions)]
    if not PROFILE_RE.fullmatch(requested):
        raise ValueError("Invalid profile ID; use G<major>.<minor>... or latest")
    found = [folder / (requested + ext) for ext in (".yaml", ".yml")
             if (folder / (requested + ext)).exists() or (folder / (requested + ext)).is_symlink()]
    if len(found) != 1 or not _is_safe_regular_file(found[0], folder):
        raise ValueError(f"Missing, duplicate or unsafe validation profile: {requested}")
    return found[0]


def _relative_test_path(root: Path, spec: str, *, allow_dir: bool) -> str:
    if not isinstance(spec, str) or not spec or any(c in spec for c in ("\\", ":", "\x00")):
        raise ValueError("Test path must be a plain relative path without node selectors")
    relative = Path(spec)
    if (relative.is_absolute() or relative.parts[0] != "tests" or
            ".." in relative.parts or "." in relative.parts):
        raise ValueError(f"Test path must stay inside tests/: {spec}")
    absolute = root / relative
    if not absolute.resolve().is_relative_to((root / "tests").resolve()):
        raise ValueError(f"Test path escapes tests/: {spec}")
    cursor = root
    for piece in relative.parts:
        cursor /= piece
        if cursor.is_symlink():
            raise ValueError(f"Symlink in test path: {spec}")
    if not (absolute.is_file() or (allow_dir and absolute.is_dir())):
        raise ValueError(f"Test target does not exist: {spec}")
    if absolute.is_file() and absolute.suffix != ".py":
        raise ValueError(f"Test target is not a Python test file: {spec}")
    return relative.as_posix()


def load_profile(root: Path, profile_file: Path) -> dict:
    data = yaml.safe_load(profile_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Validation profile must be an object")
    schema_path = root / "validation" / "schema.json"
    if not _is_safe_regular_file(schema_path, root):
        raise ValueError("Validation schema missing or unsafe")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)
    if data.get("id") != profile_file.stem:
        raise ValueError("Profile ID must equal its filename")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise ValueError("Profile name is required")
    targets = data.get("target_tests")
    if not isinstance(targets, list) or not targets:
        raise ValueError("target_tests must be a nonempty array")
    if len(targets) != len(set(map(str, targets))):
        raise ValueError("Duplicate test targets")
    data["target_tests"] = [_relative_test_path(root, spec, allow_dir=True) for spec in targets]
    regression = data.get("regression", {"enabled": False, "path": "tests/"})
    if not isinstance(regression, dict) or not isinstance(regression.get("enabled", False), bool):
        raise ValueError("regression.enabled must be a boolean")
    regression_path = regression.get("path", "tests/")
    data["regression"] = {
        "enabled": regression.get("enabled", False),
        "path": _relative_test_path(root, regression_path, allow_dir=True),
    }
    return data


def junit_counts(path: Path) -> dict | None:
    if not path.is_file():
        return None
    tree = ET.parse(path)
    suites = [tree.getroot()] if tree.getroot().tag == "testsuite" else list(tree.getroot().iter("testsuite"))
    # The top-level testsuites node may have aggregate counts: avoid double-counting.
    suites = [s for s in suites if not any(a is not s and s in list(a) for a in suites)]
    return {key: sum(int(s.attrib.get(key, 0)) for s in suites)
            for key in ("tests", "failures", "errors", "skipped")}


def file_record(path: Path, evidence: Path) -> dict:
    return {"path": path.relative_to(evidence).as_posix(),
            "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def run_command(label: str, command: list[str], cwd: Path, evidence: Path) -> dict:
    log_path = evidence / f"{label}.log"
    result = {"status": "error", "exit_code": None, "argv": command[1:], "junit": None}
    with log_path.open("w", encoding="utf-8") as log:
        try:
            process = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                     check=False, timeout=1800)
            result["exit_code"] = process.returncode
            result["status"] = "passed" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            log.write("\nTIMEOUT: validation command exceeded 1800 seconds\n")
            result["status"] = "timeout"
        except OSError as exc:
            log.write(f"\nCannot start command: {exc}\n")
    print(f"{label}: {result['status']} (exit={result['exit_code']})", flush=True)
    if result["status"] != "passed":
        print(log_path.read_text(encoding="utf-8", errors="replace")[-12000:], flush=True)
    result["log"] = file_record(log_path, evidence)
    xml = evidence / f"{label}.xml"
    if xml.is_file():
        result["junit"] = file_record(xml, evidence)
        result["counts"] = junit_counts(xml)
        counts = result["counts"]
        if result["status"] == "passed" and (counts["tests"] < 1 or
                counts["errors"] > 0 or counts["failures"] > 0 or
                counts["skipped"] >= counts["tests"]):
            result["status"] = "failed"
            result["error"] = "JUnit reports no executed passing tests or nonzero failures/errors"
    elif result["status"] == "passed":
        result["status"] = "failed"
        result["error"] = "pytest returned 0 but produced no JUnit XML"
    return result


def emit_report(report: dict, evidence: Path) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    report_file = evidence / "validation_report.json"
    report_file.write_bytes(canonical_json(report))
    digest = sha256_file(report_file)
    (evidence / "validation_report.sha256").write_text(
        f"{digest}  validation_report.json\n", encoding="utf-8")
    print(f"Final validation status: {report['status']}")
    print(f"Evidence SHA-256: {digest}")
    print(f"Report: {report_file}")


def run(args: argparse.Namespace) -> int:
    root = Path(args.repository).resolve(strict=True)
    engine_root = Path(__file__).resolve().parent.parent
    evidence = Path(args.evidence_dir).resolve()
    if evidence == root or evidence.is_relative_to(root) or evidence.is_relative_to(engine_root):
        raise ValueError("Evidence must be written outside the target and engine checkouts")
    evidence.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "1.1",
        "started_at": utc_now(),
        "finished_at": None,
        "status": "error",
        "requested_profile": args.profile,
        "profile_id": None,
        "profile_sha256": None,
        "target_branch": args.branch,
        "target_commit_sha": read_commit(root),
        "engine_commit_sha": read_commit(engine_root),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        "python_version": sys.version.split()[0],
        "regression_mode": args.regression_mode,
        "results": {},
        "engine_unit_tests": None,
        "error": None,
    }
    try:
        if args.require_provenance and (not report["target_commit_sha"] or not report["engine_commit_sha"]):
            raise ValueError("Commit SHA unavailable for one or both checkouts")
        if getattr(args, "engine_unit_log", None):
            raw_engine_log = Path(args.engine_unit_log)
            if raw_engine_log.is_symlink():
                raise ValueError("Symlinked engine unit-test log is not allowed")
            engine_log = raw_engine_log.resolve(strict=True)
            if (engine_log.parent != evidence or engine_log.is_symlink() or
                    not engine_log.is_file()):
                raise ValueError("Engine unit-test log must be a regular file in evidence directory")
            log_content = engine_log.read_text(encoding="utf-8", errors="replace")
            ran = re.search(r"(?m)^Ran (\d+) tests? in ", log_content)
            if not ran or int(ran.group(1)) < 1 or not re.search(r"(?m)^OK\s*$", log_content):
                raise ValueError("Engine unit-test log lacks a successful unittest summary")
            report["engine_unit_tests"] = {"status": "passed", "count": int(ran.group(1)),
                                           "log": file_record(engine_log, evidence)}
        file = discover_profile(root, args.profile)
        data = load_profile(root, file)
        report["profile_id"] = data["id"]
        report["profile_sha256"] = sha256_file(file)
        print(f"Selected profile: {data['id']} ({file.name})", flush=True)
        target_cmd = [sys.executable, "-m", "pytest", *data["target_tests"],
                      "-q", "-ra", "--junitxml", str(evidence / "targeted.xml")]
        report["results"]["targeted"] = run_command("targeted", target_cmd, root, evidence)
        regression_enabled = (args.regression_mode == "force" or
                              (args.regression_mode == "profile" and data["regression"]["enabled"]))
        if regression_enabled:
            regression_cmd = [sys.executable, "-m", "pytest", data["regression"]["path"],
                              "-q", "-ra", "--junitxml", str(evidence / "regression.xml")]
            report["results"]["regression"] = run_command("regression", regression_cmd, root, evidence)
        else:
            report["results"]["regression"] = {"status": "not_run", "reason": "not requested"}
        report["status"] = "passed" if all(r["status"] in ("passed", "not_run")
                                              for r in report["results"].values()) else "failed"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"Validation error: {report['error']}", file=sys.stderr, flush=True)
    finally:
        report["finished_at"] = utc_now()
        emit_report(report, evidence)
    return 0 if report["status"] == "passed" else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repository", required=True)
    p.add_argument("--profile", default="latest")
    p.add_argument("--evidence-dir", required=True)
    p.add_argument("--branch", default=None)
    p.add_argument("--regression-mode", choices=("profile", "skip", "force"), default="profile")
    p.add_argument("--require-provenance", action="store_true")
    p.add_argument("--engine-unit-log", default=None)
    return run(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())

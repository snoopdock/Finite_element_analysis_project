#!/usr/bin/env python3
"""Deterministically verify the AE-32D branch-unbound candidate."""
from __future__ import annotations
import argparse, ast, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def verify(fixture: Path) -> dict:
    src = fixture / "branch_logic.py"
    incident = fixture / "incident.md"
    expected = fixture / "expected_behavior.json"
    errors, findings = [], []
    for p in (src, incident, expected):
        if not p.is_file():
            errors.append("required_file_missing:" + p.name)
    if errors:
        return {"passed": False, "errors": errors, "findings": findings}
    text = src.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename="branch_logic.py")
        contract = json.loads(expected.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors": ["source_or_contract_parse_failed:" + type(exc).__name__], "findings": findings}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == contract.get("function")]
    if len(functions) != 1:
        errors.append("expected_work_function_not_found")
    else:
        fn = functions[0]
        assigned_in_if = any(
            isinstance(n, ast.If) and any(
                isinstance(x, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "result"
                    for target in x.targets for t in ast.walk(target)
                ) for x in ast.walk(n)
            )
            for n in fn.body
        )
        return_result = any(
            isinstance(n, ast.Return) and isinstance(n.value, ast.Name) and n.value.id == "result"
            for n in ast.walk(fn)
        )
        if assigned_in_if and return_result:
            findings.append({"check":"conditional_assignment_then_return", "status":"pass",
                "file":"branch_logic.py", "lines":[fn.lineno, max(getattr(n,"lineno",fn.lineno) for n in ast.walk(fn) if isinstance(n, ast.Return))],
                "evidence":"AST confirms result is assigned inside a conditional and returned by the function."})
        else:
            errors.append("expected_conditional_result_pattern_not_found")
    if contract.get("input_cases") != [
        {"arguments":[True], "expected":{"kind":"return","value":5}},
        {"arguments":[False], "expected":{"kind":"return","value":0}},
    ]:
        errors.append("unexpected_expected_behavior_contract")
    else:
        findings.append({"check":"expected_behavior_contract_present", "status":"pass",
            "file":"expected_behavior.json", "lines":[],
            "evidence":"Contract specifies work(True) -> 5 and work(False) -> 0."})
    proc = subprocess.run(
        [sys.executable, "-c", "import branch_logic; print(branch_logic.work(False))"],
        cwd=fixture, capture_output=True, text=True, timeout=10,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE":"1"},
    )
    runtime_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    observed = proc.returncode != 0 and "UnboundLocalError" in runtime_text and "result" in runtime_text
    if observed:
        findings.append({"check":"runtime_reproduces_unbound_local_error", "status":"pass",
            "file":"branch_logic.py", "lines":[],
            "evidence":"Executing work(False) raises UnboundLocalError mentioning result.",
            "exit_code":proc.returncode})
    else:
        errors.append("expected_unbound_local_error_not_reproduced")
        findings.append({"check":"runtime_reproduces_unbound_local_error", "status":"fail",
            "file":"branch_logic.py", "lines":[],
            "evidence":"Expected UnboundLocalError was not observed.", "exit_code":proc.returncode,
            "stderr_tail":(proc.stderr or "")[-1000:]})
    manifest = [{"path":p.name, "sha256":sha256(p)} for p in (src, incident, expected)]
    return {"passed":not errors, "errors":errors, "findings":findings, "fixture_manifest":manifest,
            "runtime":{"exit_code":proc.returncode,"expected_unbound_local_error_observed":observed,
                       "stdout":(proc.stdout or "")[-500:],"stderr_tail":(proc.stderr or "")[-1000:]}}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args=ap.parse_args()
    fixture=args.fixture.resolve()
    result=verify(fixture)
    report={
        "schema_version":"ae32d/machine-verification/v1",
        "case_id":"AE32D-CANDIDATE-BRANCH-UNBOUND-001",
        "verification_mode":"deterministic_static_checks_plus_controlled_runtime_reproduction",
        "status":"machine_verified_candidate" if result["passed"] else "machine_verification_failed",
        "primary_benchmark_eligible":False,
        "human_independent_adjudication":"not_performed",
        "source_revision":os.environ.get("GITHUB_SHA") or os.environ.get("SOURCE_REVISION") or "local-unset",
        "workflow_run_id":os.environ.get("GITHUB_RUN_ID") or "local-run",
        "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "limitations":[
            "This verifies one local synthetic branch-control fixture only.",
            "It is not independent human adjudication or a general AE-32C accuracy result.",
            "The case is exploratory and excluded from primary benchmark scoring."
        ],
        **result
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"checks_passed":sum(x.get("status")=="pass" for x in result["findings"]),
                      "errors":result["errors"],"report":str(args.output)},indent=2))
    return 0 if result["passed"] else 1
if __name__=="__main__":
    raise SystemExit(main())

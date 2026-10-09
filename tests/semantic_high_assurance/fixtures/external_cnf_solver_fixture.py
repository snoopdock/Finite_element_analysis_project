#!/usr/bin/env python3
"""Test-only external CNF protocol fixture; never registered as a production verifier."""
from __future__ import annotations

from itertools import product
import json
import sys
import time

SOLVER_ID = "fixture-cnf-solver"
SOLVER_VERSION = "0.1.0"
PROTOCOL = "semantic_external_solver/v1"
TRANSPORT = "semantic_external_json_process/v1"


def clause_true(clause, assignment):
    for literal in clause:
        value = assignment[abs(literal) - 1]
        if literal < 0:
            value = not value
        if value:
            return True
    return False


def solve(variable_count, clauses):
    for assignment in product((False, True), repeat=variable_count):
        if all(clause_true(clause, assignment) for clause in clauses):
            return assignment
    return None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "solve"
    if mode == "sleep":
        time.sleep(2.0)
    if mode == "malformed":
        sys.stdout.write("not-json")
        return
    request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if request["transport_protocol"] != TRANSPORT:
        raise SystemExit(2)
    payload = request["payload"]
    if mode == "oversize":
        sys.stdout.write(json.dumps({"transport_protocol": TRANSPORT, "payload": {"padding": "x" * 100000}}))
        return
    variable_count = payload["variable_count"]
    clauses = payload["clauses"]
    model = solve(variable_count, clauses)
    verdict = "sat" if model is not None else "unsat"
    if mode == "false-unsat":
        verdict = "unsat"
        model = None
    elif mode == "unknown":
        verdict = "unknown"
        model = None
    certificate = None
    if verdict == "sat":
        certificate = {
            "kind": "sat_model",
            "assignment": {str(i + 1): value for i, value in enumerate(model)},
        }
    elif verdict == "unsat":
        certificate = {"kind": "unsat_claim"}
    response = {
        "protocol_version": PROTOCOL,
        "request_id": payload["request_id"],
        "input_digest": payload["input_digest"],
        "solver_id": SOLVER_ID,
        "solver_version": SOLVER_VERSION,
        "verdict": verdict,
        "certificate": certificate,
        "diagnostics": [f"fixture_mode={mode}"],
    }
    if mode == "wrong-binding":
        response["request_id"] = "wrong-request"
    sys.stdout.write(json.dumps({"transport_protocol": TRANSPORT, "payload": response}, sort_keys=True))


if __name__ == "__main__":
    main()

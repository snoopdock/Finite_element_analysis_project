#!/usr/bin/env python3
"""Test-only external CNF protocol fixture; never registered as a production verifier."""
from __future__ import annotations

from itertools import product
import hashlib
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


def cnf_digest(variable_count, clauses):
    payload = {"variable_count": variable_count, "clauses": clauses}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def rup_certificate(variable_count, clauses, *, valid=True):
    digest = cnf_digest(variable_count, clauses)
    if valid:
        clause_set = {tuple(clause) for clause in clauses}
        if (1,) in clause_set and (-1,) in clause_set:
            steps = [[]]
        else:
            # Standard four-clause XOR contradiction used by G3.4.3 tests.
            steps = [[1], [-1], []]
    else:
        steps = [[]]
    return {
        "kind": "unsat_proof",
        "proof_format": "cnf-rup/v1",
        "cnf_digest": digest,
        "steps": steps,
    }


def drat_certificate(variable_count, clauses):
    digest = cnf_digest(variable_count, clauses)
    clause_set = {tuple(clause) for clause in clauses}
    if (1,) in clause_set and (-1,) in clause_set:
        steps = [{"op": "add", "clause": []}]
    else:
        # Four-clause XOR contradiction.  Exercise a genuine RAT addition on
        # the highest declared variable, delete it, then finish with RUP steps.
        steps = [
            {"op": "add", "clause": [variable_count]},
            {"op": "delete", "clause": [variable_count]},
            {"op": "add", "clause": [1]},
            {"op": "add", "clause": [-1]},
            {"op": "add", "clause": []},
        ]
    return {
        "kind": "unsat_proof",
        "proof_format": "cnf-drat/v1",
        "cnf_digest": digest,
        "steps": steps,
    }

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
        if mode == "rup-unsat":
            certificate = rup_certificate(variable_count, clauses, valid=True)
        elif mode == "drat-unsat":
            certificate = drat_certificate(variable_count, clauses)
        elif mode == "invalid-rup":
            certificate = rup_certificate(variable_count, clauses, valid=False)
        else:
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

"""CLI for the controlled, language-agnostic AE-27 proposal gateway.

The CLI reads canonical JSON contracts/proposals/reviews and bounded evidence
files. It never invokes a model, executes repository source, mutates the
authoritative SemanticGraph, or promotes a candidate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat

from audit_engine.semantic_audit.ae24.contracts import (
    canonical,
    ContractError,
    MAX_BYTES,
    MAX_SOURCE_BYTES,
)
from .bridge import (
    validate_proposal,
    symbolic_probe_set,
    adjudicate,
    verify_adjudication,
)

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _read(path: Path, limit: int) -> bytes:
    path = Path(path)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ContractError("Symlink input forbidden")
    try:
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError as exc:
        raise ContractError("Unable to open input") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ContractError("Input must be a bounded regular file")
        data = os.read(fd, limit + 1)
        if len(data) != info.st_size:
            raise ContractError("Input changed during read")
        return data
    finally:
        os.close(fd)


def _json_value(path: Path) -> object:
    data = _read(path, MAX_BYTES)
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("Malformed JSON") from exc
    if canonical(value) != data:
        raise ContractError("Expected canonical JSON with final newline")
    return value


def _json_object(path: Path) -> dict:
    value = _json_value(path)
    if not isinstance(value, dict):
        raise ContractError("Expected canonical JSON object")
    return value


def _json_list(path: Path) -> list:
    value = _json_value(path)
    if not isinstance(value, list):
        raise ContractError("Expected canonical JSON list")
    return value


def _inputs(contract_path: Path, evidence_dir: Path):
    contract = _json_object(contract_path)
    root = Path(evidence_dir)
    if root.is_symlink() or not root.is_dir():
        raise ContractError("Evidence root must be a real directory")
    sources = contract.get("sources")
    if not isinstance(sources, list):
        raise ContractError("Missing contract sources")
    payload = {}
    for row in sources:
        sid = row.get("id") if isinstance(row, dict) else None
        if not isinstance(sid, str) or not NAME.fullmatch(sid):
            raise ContractError("Unsafe source identity")
        if sid in payload:
            raise ContractError("Duplicate source identity")
        payload[sid] = _read(root / sid, MAX_SOURCE_BYTES)
    return contract, payload


def main(argv=None):
    parser = argparse.ArgumentParser(description="AE-27 controlled neurosymbolic gateway")
    sub = parser.add_subparsers(dest="action", required=True)

    for name in ("validate", "probe", "adjudicate", "verify-adjudication"):
        sub.add_parser(name)

    sub.choices["validate"].add_argument("--contract", type=Path, required=True)
    sub.choices["validate"].add_argument("--evidence-dir", type=Path, required=True)
    sub.choices["validate"].add_argument("--proposal", type=Path, required=True)

    sub.choices["probe"].add_argument("--contract", type=Path, required=True)
    sub.choices["probe"].add_argument("--evidence-dir", type=Path, required=True)
    sub.choices["probe"].add_argument("--proposal", type=Path, required=True)

    for action in ("adjudicate", "verify-adjudication"):
        sub.choices[action].add_argument("--contract", type=Path, required=True)
        sub.choices[action].add_argument("--evidence-dir", type=Path, required=True)
        sub.choices[action].add_argument("--proposal", type=Path, required=True)
        sub.choices[action].add_argument("--reviews", type=Path, required=True)
    sub.choices["verify-adjudication"].add_argument("--result", type=Path, required=True)

    args = parser.parse_args(argv)
    contract, sources = _inputs(args.contract, args.evidence_dir)
    proposal = _json_object(args.proposal)

    if args.action == "validate":
        result = validate_proposal(contract, sources, proposal)
        result = {
            "status": "proposal_admitted_for_analysis_not_authoritative",
            "proposal_sha256": result["proposal_sha256"],
            "base_semantic_fingerprint": result["semantic_snapshot"].semantic_fingerprint,
            "base_hypothesis_fingerprint": result["semantic_snapshot"].hypothesis_fingerprint,
            "context_fingerprint": result["context_fingerprint"],
            "context_semantic_ids": list(result["context_semantic_ids"]),
        }
    elif args.action == "probe":
        meta = validate_proposal(contract, sources, proposal)
        probe = symbolic_probe_set(contract, sources, proposal["candidate_assertions"])
        result = {
            "status": "counterfactual_symbolic_probe",
            "proposal_sha256": meta["proposal_sha256"],
            "base_semantic_fingerprint": meta["semantic_snapshot"].semantic_fingerprint,
            "joint_probe_status": probe["set_status"],
            "candidate_results": probe["candidate_results"],
            "set_issue_ids": probe["set_issue_ids"],
            "set_unknown_ids": probe["set_unknown_ids"],
            "authority": probe["authority"],
        }
    else:
        reviews = _json_list(args.reviews)
        if args.action == "adjudicate":
            result = adjudicate(contract, sources, proposal, reviews)
        else:
            claimed = _json_object(args.result)
            verify_adjudication(contract, sources, proposal, reviews, claimed)
            result = {
                "status": "adjudication_verified_by_exact_replay",
                "adjudication_sha256": claimed["adjudication_sha256"],
            }

    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

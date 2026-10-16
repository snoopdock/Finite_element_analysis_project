"""CLI for AE-28 neural/LLM interpretation intake.

The CLI never invokes a model, network, shell, source program, or repository
mutation. It creates a source-bound request and ingests a separately prepared
structured model response plus its raw output bytes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from audit_engine.semantic_audit.ae24.contracts import (
    canonical,
    ContractError,
    MAX_BYTES,
    MAX_SOURCE_BYTES,
)
from .adapter import (
    NeuralInterpretationError,
    make_request,
    ingest_model_response,
    verify_interpretation,
    response_from_canonical_bytes,
)


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


def _json(path: Path) -> object:
    data = _read(path, MAX_BYTES)
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("Malformed JSON") from exc
    if canonical(value) != data:
        raise ContractError("Expected canonical JSON with final newline")
    return value


def _object(path: Path) -> dict:
    value = _json(path)
    if not isinstance(value, dict):
        raise ContractError("Expected canonical JSON object")
    return value


def _list(path: Path) -> list:
    value = _json(path)
    if not isinstance(value, list):
        raise ContractError("Expected canonical JSON list")
    return value


def _inputs(contract_path: Path, evidence_dir: Path):
    contract = _object(contract_path)
    root = Path(evidence_dir)
    if root.is_symlink() or not root.is_dir():
        raise ContractError("Evidence root must be a real directory")
    sources = contract.get("sources")
    if not isinstance(sources, list):
        raise ContractError("Missing contract sources")
    payload = {}
    for row in sources:
        sid = row.get("id") if isinstance(row, dict) else None
        if not isinstance(sid, str):
            raise ContractError("Unsafe source identity")
        payload[sid] = _read(root / sid, MAX_SOURCE_BYTES)
    return contract, payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AE-28 neural/LLM interpretation boundary")
    sub = parser.add_subparsers(dest="action", required=True)

    request_cmd = sub.add_parser("request")
    request_cmd.add_argument("--contract", type=Path, required=True)
    request_cmd.add_argument("--evidence-dir", type=Path, required=True)
    request_cmd.add_argument("--request-id", required=True)
    request_cmd.add_argument("--context-occurrence", action="append", required=True)
    request_cmd.add_argument("--task-digest", required=True)
    request_cmd.add_argument("--input-manifest", type=Path, required=True)

    ingest_cmd = sub.add_parser("ingest")
    for cmd in (ingest_cmd,):
        cmd.add_argument("--contract", type=Path, required=True)
        cmd.add_argument("--evidence-dir", type=Path, required=True)
        cmd.add_argument("--request", type=Path, required=True)
        cmd.add_argument("--raw-output", type=Path, required=True)
        cmd.add_argument("--response", type=Path, required=True)

    verify_cmd = sub.add_parser("verify")
    for cmd in (verify_cmd,):
        cmd.add_argument("--contract", type=Path, required=True)
        cmd.add_argument("--evidence-dir", type=Path, required=True)
        cmd.add_argument("--request", type=Path, required=True)
        cmd.add_argument("--raw-output", type=Path, required=True)
        cmd.add_argument("--response", type=Path, required=True)
        cmd.add_argument("--interpretation", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.action == "request":
            contract, sources = _inputs(args.contract, args.evidence_dir)
            manifest = _list(args.input_manifest)
            result = make_request(
                contract,
                sources,
                request_id=args.request_id,
                context_occurrences=args.context_occurrence,
                task_digest=args.task_digest,
                input_manifest=manifest,
            )
        else:
            contract, sources = _inputs(args.contract, args.evidence_dir)
            request = _object(args.request)
            raw = _read(args.raw_output, 4_000_000)
            response = _object(args.response)
            if args.action == "ingest":
                result = ingest_model_response(contract, sources, request, raw, response)
            else:
                claimed = _object(args.interpretation)
                verify_interpretation(contract, sources, request, raw, response, claimed)
                result = {
                    "status": "neural_interpretation_verified_by_exact_replay",
                    "interpretation_sha256": claimed["interpretation_sha256"],
                }
        print(canonical(result).decode("utf-8"), end="")
        return 0
    except (
        NeuralInterpretationError,
        ContractError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
        UnicodeError,
    ) as exc:
        parser.exit(2, f"AE-28 interpretation failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

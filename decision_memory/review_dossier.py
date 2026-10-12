"""G3.4.20: fail-closed, deterministic, read-only review dossier for SAT text.

The output is a *request for review*, never a validation of semantic support,
human approval, solver proof, executable action, or authorization to write memory.
A G3.4.19 proposal audit is mandatory; it is independently re-evaluated against
source bytes before any dossier is created or accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from decision_memory import proposal_audit as proposals
except ModuleNotFoundError:  # direct invocation: python source/decision_memory/review_dossier.py
    import proposal_audit as proposals  # type: ignore[no-redef]

SCHEMA_VERSION = "sat-claim-review-dossier/v1"
MAX_INPUT_BYTES = 2 * 1024 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class ReviewDossierError(ValueError):
    """Unsafe review request, invalid audit, or a corrupted dossier."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise ReviewDossierError("JSON contains a duplicate key")
        data[key] = value
    return data


def _reject_json_constant(value: str) -> None:
    raise ReviewDossierError(f"JSON cannot include {value}")


def _read_json(path: Path) -> dict:
    """Bound file size and refuse symlink files and symlinked parent directories."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ReviewDossierError("Missing, symbolic, or oversized input JSON file")
    if any(part.is_symlink() for part in path.parents):
        raise ReviewDossierError("Input directory contains a symlink")
    try:
        value = json.loads(path.read_bytes().decode("utf-8"),
                           object_pairs_hook=_reject_duplicate_keys,
                           parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewDossierError("Invalid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ReviewDossierError("JSON top level must be a mapping")
    return value


def create_dossier(repository: Path, audit: dict) -> dict:
    """Reverify the underlying audit and construct a deterministic review request.

    A complete citation trace does NOT imply evidence sufficiency or entailment.
    No external proof bundle or SAT solver is consulted here.
    """
    if not isinstance(audit, dict):
        raise ReviewDossierError("Audit must be a mapping")
    root = Path(repository).resolve(strict=True)
    try:
        proposals.verify_audit(audit, root)
    except (proposals.ProposalAuditError, proposals.memory.ContextRetrievalError,
            proposals.memory.learning_rules.RuleValidationError, KeyError, TypeError, OSError) as exc:
        raise ReviewDossierError("Original audit failed independent re-verification") from exc

    source_records = {entry["record_id"]: entry for entry in audit["cited_sources"]}
    claims = []
    flags: set[str] = set()
    for item in audit["claims"]:
        refs = list(item["source_ids"])
        unresolved = list(item["unresolved_source_ids"])
        resolved = list(item["resolved_source_ids"])
        caveats = sorted(set(
            flag for ident in resolved
            for flag in source_records[ident]["caveats"]
        ))
        if not refs:
            trace_status = "uncited"
            blockers = ["missing_explicit_citation"]
        elif unresolved:
            trace_status = "unresolved"
            blockers = ["unresolved_citation"]
        else:
            trace_status = "structurally_traced_only"
            blockers = []
        blockers.extend(["semantic_support_not_assessed", "external_evidence_not_reverified", "human_review_pending"])
        if "candidate_not_approved" in caveats:
            blockers.append("unapproved_learning_rule")
        if "pending_action_with_successful_feedback" in caveats or "action_outcome_pending" in caveats:
            blockers.append("historical_outcome_conflict")
        flags.update(caveats)
        claims.append({
            "claim_index": item["line_number"],
            "claim_sha256": hashlib.sha256(item["text_untrusted"].encode("utf-8")).hexdigest(),
            "claim_text_untrusted": item["text_untrusted"],
            "trace_status": trace_status,
            "cited_record_ids": refs,
            "resolved_record_ids": resolved,
            "unresolved_record_ids": unresolved,
            "historical_caveats": caveats,
            "review_blockers": sorted(set(blockers)),
            "semantic_support_assessed": False,
            "reviewer_assessment": "not_assessed",
        })

    cited = [{
        "record_id": entry["record_id"],
        "record_type": entry["record_type"],
        "source_path": entry["source_path"],
        "source_sha256": entry["source_sha256"],
        "provenance_binding": "local_file_hash_only",
        "semantic_support_verified": False,
        "external_evidence_verified": False,
        "caveats": sorted(set(entry["caveats"])),
    } for entry in sorted(source_records.values(), key=lambda x: x["record_id"])]

    incomplete = sum(x["trace_status"] != "structurally_traced_only" for x in claims)
    dossier = {
        "schema_version": SCHEMA_VERSION,
        "proposal_audit_sha256": audit["audit_sha256"],
        "draft_sha256": audit["draft_sha256"],
        "source_commit_sha": audit["source_commit_sha"],
        "retrieval_context_sha256": audit["retrieval_context_sha256"],
        "source_record_count": len(cited),
        "sources": cited,
        "claim_reviews": claims,
        "trace_summary": {
            "claims_total": len(claims),
            "citations_structurally_complete": len(claims) - incomplete,
            "claims_missing_or_unresolved_citations": incomplete,
            "historic_conflict_or_review_flags": sorted(flags),
            "retrieval_truncated": bool(audit["review_issues"]["retrieval_truncated"]),
        },
        "human_review": {
            "status": "pending",
            "required": True,
            "assessment_per_claim": "not_assessed",
            "semantic_entailment_verified": False,
            "external_evidence_reverified": False,
            "authorization_granted": False,
        },
        "execution_constraints": {
            "automated_sat_action_allowed": False,
            "repository_writeback_allowed": False,
            "learned_rule_promotion_allowed": False,
            "publication_as_verified_engineering_text_allowed": False,
        },
        "limitations": [
            "Resolving a local record ID does not prove that the source supports the claim.",
            "Historical decision and outcome records are untrusted evidence candidates.",
            "No external evidence bundle, formal SAT proof, or engineering correctness was verified.",
            "Human review and independent supporting evidence are required for decisions.",
        ],
    }
    dossier["dossier_sha256"] = _digest(dossier)
    return dossier


def verify_dossier(dossier: dict, audit: dict, repository: Path) -> bool:
    if not isinstance(dossier, dict) or dossier.get("schema_version") != SCHEMA_VERSION:
        raise ReviewDossierError("Unsupported review dossier schema")
    sha = dossier.get("dossier_sha256")
    if not isinstance(sha, str) or not HEX64.fullmatch(sha):
        raise ReviewDossierError("Missing dossier SHA-256")
    body = {k: v for k, v in dossier.items() if k != "dossier_sha256"}
    if _digest(body) != sha:
        raise ReviewDossierError("Review dossier checksum mismatch")
    fresh = create_dossier(repository, audit)
    if _canonical(dossier) != _canonical(fresh):
        raise ReviewDossierError("Dossier does not match the current audit and repository")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only SAT claim-level review dossier")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--audit-file", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output")
    mode.add_argument("--verify-file")
    args = parser.parse_args(argv)
    try:
        audit = _read_json(Path(args.audit_file))
        if args.verify_file:
            dossier = _read_json(Path(args.verify_file))
            verify_dossier(dossier, audit, Path(args.repository))
            print("Review dossier verified against checked-out sources; no approval granted")
        else:
            result = create_dossier(Path(args.repository), audit)
            payload = json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
            # Reuse the G3.4.18 atomic, symlink-safe, out-of-repository output contract.
            proposals.memory._write_optional(Path(args.output), payload, Path(args.repository))
            print(f"SAT review dossier created: {args.output}")
            print(f"Claims requiring review: {result['trace_summary']['claims_total']}")
            print("Not approved; no SAT action authorized")
    except (ReviewDossierError, proposals.ProposalAuditError,
            proposals.memory.ContextRetrievalError,
            proposals.memory.learning_rules.RuleValidationError,
            ValueError, TypeError, KeyError, OSError, UnicodeError) as exc:
        parser.exit(2, f"SAT review dossier failed: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

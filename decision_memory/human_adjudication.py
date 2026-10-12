"""G3.4.21: record *untrusted human review annotations* over a verified SAT dossier.

This module authenticates neither the reviewer nor the semantics of any claim.
No rule promotion, document certification, repository mutation or SAT actuation.
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
    from decision_memory import review_dossier as dossiers
    from decision_memory import proposal_audit as audits
except ModuleNotFoundError:  # direct script execution from source/decision_memory/
    import review_dossier as dossiers  # type: ignore[no-redef]
    import proposal_audit as audits  # type: ignore[no-redef]

SUBMISSION_SCHEMA = "sat-human-review-submission/v1"
REPORT_SCHEMA = "sat-human-review-annotations/v1"
VERDICTS = frozenset({"supported_by_reviewer", "unsupported", "insufficient_evidence", "needs_revision", "abstain"})
MAX_RATIONALE = 2000
MAX_LABEL = 100
HEX = re.compile(r"[0-9a-f]{64}\Z")

class AdjudicationError(ValueError):
    """Malformed, stale, contradictory or unsafe human-review input."""


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hash(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _validate_submission(sub: dict, dossier: dict) -> dict[int, dict]:
    if not isinstance(sub, dict) or set(sub) != {"schema_version", "dossier_sha256", "reviewer_label", "assessments"}:
        raise AdjudicationError("Review submission keys are missing or unexpected")
    if sub["schema_version"] != SUBMISSION_SCHEMA or sub["dossier_sha256"] != dossier["dossier_sha256"]:
        raise AdjudicationError("Review does not bind to this exact dossier")
    label = sub["reviewer_label"]
    if not isinstance(label, str) or not (1 <= len(label.strip()) <= MAX_LABEL) or label != label.strip() or any(ord(c) < 32 for c in label):
        raise AdjudicationError("Invalid reviewer label (self-asserted, not authenticated)")
    entries = sub["assessments"]
    if not isinstance(entries, list) or len(entries) > len(dossier["claim_reviews"]) or not entries:
        raise AdjudicationError("Expected at least one, at most one assessment per dossier claim")
    allowed = {x["claim_index"]: x for x in dossier["claim_reviews"]}
    chosen = {}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"claim_index", "claim_sha256", "verdict", "rationale", "reviewed_source_ids"}:
            raise AdjudicationError("Invalid claim assessment fields")
        num = item["claim_index"]
        if isinstance(num, bool) or not isinstance(num, int) or num not in allowed or num in chosen:
            raise AdjudicationError("Duplicate or non-existent claim index")
        claim = allowed[num]
        if item["claim_sha256"] != claim["claim_sha256"]:
            raise AdjudicationError("Claim text SHA-256 does not match the dossier")
        verdict = item["verdict"]
        if not isinstance(verdict, str) or verdict not in VERDICTS:
            raise AdjudicationError("Invalid reviewer verdict")
        reason = item["rationale"]
        if not isinstance(reason, str) or reason != reason.strip() or not (20 <= len(reason) <= MAX_RATIONALE) or any(ord(c) < 32 and c not in "\n\t" for c in reason):
            raise AdjudicationError("Reviewer rationale must be substantive text between 20 and 2000 characters")
        refs = item["reviewed_source_ids"]
        if not isinstance(refs, list) or len(refs) != len(set(str(x) for x in refs)) or any(not isinstance(x,str) for x in refs):
            raise AdjudicationError("Invalid or duplicate reviewed source IDs")
        if not set(refs).issubset(set(claim["resolved_record_ids"])):
            raise AdjudicationError("Reviewed sources must be among claim's verified local citations")
        if verdict == "supported_by_reviewer":
            if (claim["trace_status"] != "structurally_traced_only" or not refs or
                    any(x in claim["review_blockers"] for x in
                        ("historical_outcome_conflict", "unapproved_learning_rule", "unresolved_citation", "missing_explicit_citation"))):
                raise AdjudicationError("Cannot mark unresolved or conflicting claim as supported")
        chosen[num] = item
    return chosen


def create_annotations(repository: Path, audit: dict, dossier: dict, submission: dict, actor: str = "unknown") -> dict:
    """Verify the audit and dossier from source bytes; then bind reviewer *claims* to them."""
    if not isinstance(actor, str) or not (1 <= len(actor) <= 100) or any(ord(c) < 32 for c in actor):
        raise AdjudicationError("Invalid GitHub actor metadata")
    try:
        dossiers.verify_dossier(dossier, audit, repository)
    except (dossiers.ReviewDossierError, audits.ProposalAuditError, TypeError, KeyError, OSError) as exc:
        raise AdjudicationError("Input dossier or audit no longer matches source bytes") from exc
    selected = _validate_submission(submission, dossier)
    reviews = []
    for claim in dossier["claim_reviews"]:
        assessment = selected.get(claim["claim_index"])
        reviews.append({
            "claim_index": claim["claim_index"],
            "claim_sha256": claim["claim_sha256"],
            "cited_record_ids": claim["cited_record_ids"],
            "trace_status": claim["trace_status"],
            "historical_caveats": claim["historical_caveats"],
            "review_blockers": claim["review_blockers"],
            "reviewed": assessment is not None,
            "reviewer_verdict_unverified": assessment["verdict"] if assessment else None,
            "reviewer_rationale_untrusted": assessment["rationale"] if assessment else None,
            "reviewed_source_ids": assessment["reviewed_source_ids"] if assessment else [],
            "independent_semantic_entailment_verified": False,
        })
    reviewed = sum(item["reviewed"] for item in reviews)
    obj = {
        "schema_version": REPORT_SCHEMA,
        "dossier_sha256": dossier["dossier_sha256"],
        "proposal_audit_sha256": dossier["proposal_audit_sha256"],
        "source_commit_sha": dossier["source_commit_sha"],
        "source_file_bindings": [
            {"record_id": s["record_id"], "source_path": s["source_path"], "source_sha256": s["source_sha256"]}
            for s in dossier["sources"]
        ],
        "review_submission_sha256": _hash(submission),
        "reviewer_label_unverified": submission["reviewer_label"],
        "github_actor_observed_not_attested": actor,
        "reviews": reviews,
        "summary": {
            "total_claims": len(reviews),
            "reviewed_claims": reviewed,
            "unreviewed_claims": len(reviews) - reviewed,
            "review_completeness": "complete" if reviewed == len(reviews) else "partial",
            "human_statements_collected": True,
            "semantic_truth_verified_by_software": False,
        },
        "execution_constraints": dict(dossier["execution_constraints"]),
        "approval": {
            "human_identity_cryptographically_verified": False,
            "independent_engineering_approval_granted": False,
            "sat_action_authorized": False,
            "automatic_memory_writeback_permitted": False,
            "candidate_rule_promoted": False,
        },
        "limitations": [
            "Reviewer identity and subjective assessment are unverified assertions; GitHub actor metadata is not a signature.",
            "A positive reviewer verdict does not establish semantic support, scientific truth, or an independent SAT proof.",
            "This temporary record does not approve publication, SAT actions, permanent memory writes, or rule promotion.",
        ],
    }
    obj["annotations_sha256"] = _hash(obj)
    return obj


def verify_annotations(report: dict, repository: Path, audit: dict, dossier: dict, submission: dict, actor: str = "unknown") -> bool:
    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA:
        raise AdjudicationError("Unsupported annotation schema")
    digest = report.get("annotations_sha256")
    if not isinstance(digest, str) or not HEX.fullmatch(digest):
        raise AdjudicationError("Missing canonical annotations digest")
    if _hash({k: v for k, v in report.items() if k != "annotations_sha256"}) != digest:
        raise AdjudicationError("Annotations digest mismatch")
    fresh = create_annotations(repository, audit, dossier, submission, actor)
    if _canonical(fresh) != _canonical(report):
        raise AdjudicationError("Annotations disagree with independently recomputed sources")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G3.4.21 read-only human claim annotation binding")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--audit-file", required=True)
    parser.add_argument("--dossier-file", required=True)
    parser.add_argument("--review-file", required=True)
    parser.add_argument("--github-actor", default="unknown")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output")
    mode.add_argument("--verify-file")
    args = parser.parse_args(argv)
    try:
        audit = dossiers._read_json(Path(args.audit_file))
        dossier = dossiers._read_json(Path(args.dossier_file))
        submission = dossiers._read_json(Path(args.review_file))
        if args.verify_file:
            report = dossiers._read_json(Path(args.verify_file))
            verify_annotations(report, Path(args.repository), audit, dossier, submission, args.github_actor)
            print("Review annotations verified structurally against source; no engineering approval")
        else:
            report = create_annotations(Path(args.repository), audit, dossier, submission, args.github_actor)
            text = json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            audits.memory._write_optional(Path(args.output), text, Path(args.repository))
            print("Human review annotations recorded:", report["summary"]["reviewed_claims"])
            print("Review completeness:", report["summary"]["review_completeness"])
            print("No SAT action or repository writeback authorized")
    except (AdjudicationError, dossiers.ReviewDossierError, audits.ProposalAuditError,
            audits.memory.ContextRetrievalError, ValueError, KeyError, TypeError, OSError, UnicodeError) as exc:
        parser.exit(2, f"Human claim annotation failed: {exc}\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())

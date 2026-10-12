"""G3.4.19: deterministic, read-only trace of an untrusted SAT proposal.

This is *not* semantic entailment checking, action authorization, learning-rule
promotion, or SAT solving. A syntactically valid citation is not proof that the
cited record supports a claim. All outputs require human review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

try:
    from decision_memory import context_retrieval as memory
except ModuleNotFoundError:  # direct invocation from workflow checkout
    import context_retrieval as memory  # type: ignore[no-redef]

SCHEMA_VERSION = "sat-proposal-audit/v1"
MAX_DRAFT_LENGTH = 4000
MAX_CLAIM_LINES = 24
MAX_CLAIM_LENGTH = 1000
# The explicit marker avoids treating ordinary text IDs as audit citations.
MARKER = re.compile(r"(?<!\[)\[\[([^\[\]\n]{1,100})\]\](?!\])")
ID = re.compile(r"^(?:DEC|ACTION|OUTCOME|RULE)-G[0-9]+(?:\.[0-9]+)+-[0-9]{3,}$")
CATEGORY = {"DEC": "decisions", "ACTION": "actions", "OUTCOME": "outcomes", "RULE": "rules"}


class ProposalAuditError(ValueError):
    """Invalid proposal or unsafe audit output path."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _claims(text: str) -> list[str]:
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_DRAFT_LENGTH:
        raise ProposalAuditError("Proposal must contain between 1 and 4000 characters")
    # Do not accept terminal control sequences, hidden line delimiters, or invalid surrogates.
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char != "\n" for char in text):
        raise ProposalAuditError("Proposal contains forbidden control or surrogate characters")
    result = [line.strip() for line in text.splitlines() if line.strip()]
    if len(result) > MAX_CLAIM_LINES or any(len(line) > MAX_CLAIM_LENGTH for line in result):
        raise ProposalAuditError("Proposal exceeds claim count or line length limit")
    return result


def _parse_markers(line: str) -> list[str]:
    # Reject malformed/unclosed markers; do not accept ambiguous textual citations.
    matched = list(MARKER.finditer(line))
    rest = MARKER.sub("", line)
    if "[[" in rest or "]]" in rest:
        raise ProposalAuditError("Malformed source marker; use [[RECORD-ID]]")
    markers = [m.group(1) for m in matched]
    if any(not ID.fullmatch(c) for c in markers):
        raise ProposalAuditError("Invalid source marker syntax")
    return list(dict.fromkeys(markers))


def _source_flags(kind: str, ident: str, record: dict, graph: dict, rules: dict) -> list[str]:
    return memory._flags(kind, ident, record, graph, rules)


def audit(repository: Path, query: str, draft: str, max_results: int = 8) -> dict:
    """Audit references and trace a proposed text; never decide its correctness."""
    lines = _claims(draft)
    root = Path(repository).resolve(strict=True)
    retrieved = memory.retrieve(root, query, max_results)
    # Use the same fail-closed, entire-graph validation as the retrieval system.
    graph, verified_rules = memory._build_graph(root)
    indexed = {record_id: (kind, record) for kind, items in graph.items() for record_id, record in items.items()}
    # No ambiguous cross-kind IDs should ever produce an arbitrary resolution.
    if sum(map(len, graph.values())) != len(indexed):
        raise ProposalAuditError("Ambiguous duplicate record ID")

    claims = []
    referenced = set()
    for number, line in enumerate(lines, 1):
        refs = _parse_markers(line)
        referenced.update(refs)
        found = [x for x in refs if x in indexed]
        missing = [x for x in refs if x not in indexed]
        flags = []
        if not refs:
            flags.append("claim_has_no_explicit_source_marker")
        if missing:
            flags.append("unresolved_source_id")
        claims.append({
            "line_number": number,
            "text_untrusted": line,
            "source_ids": refs,
            "resolved_source_ids": found,
            "unresolved_source_ids": missing,
            "caveats": flags,
            "semantic_support_verified": False,
        })

    cited_sources = []
    for ident in sorted(referenced):
        if ident not in indexed:
            continue
        kind, record = indexed[ident]
        citation = memory._citation(root, kind, ident)
        caveats = _source_flags(kind, ident, record, graph, verified_rules)
        # Even when no caveat exists, an ID citation never validates entailment.
        cited_sources.append({
            **citation,
            "caveats": caveats,
            "external_evidence_bundle_verified": False,
            "semantic_support_verified": False,
            "candidate_rule_approved": False if kind == "rules" else None,
        })

    unresolved = sorted({ref for cl in claims for ref in cl["unresolved_source_ids"]})
    uncited = [cl["line_number"] for cl in claims if not cl["source_ids"]]
    conflict_flags = sorted({
        flag for entry in cited_sources for flag in entry["caveats"]
        if flag in {"pending_action_with_successful_feedback", "action_outcome_pending",
                    "unresolved_decision_reference", "unresolved_action_reference",
                    "historical_status_conflict_acknowledged", "candidate_not_approved"}
    })
    trace_complete = not unresolved and not uncited
    report = {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": retrieved["source_commit_sha"],
        "query": retrieved["query"],
        "draft_text_untrusted": draft,
        "max_results": max_results,
        "draft_sha256": _sha(draft.encode("utf-8")),
        "retrieval_context_sha256": retrieved["context_sha256"],
        "retrieved_context": retrieved,
        "claims": claims,
        "cited_sources": cited_sources,
        "review_gates": {
            "all_claims_have_explicit_citations": not uncited,
            "all_citation_targets_resolved": not unresolved,
            "citation_trace_complete": trace_complete,
            "semantic_entailment_verified": False,
            "external_bundle_reverified": False,
            "human_approval_obtained": False,
        },
        "review_issues": {
            "uncited_line_numbers": uncited,
            "unresolved_source_ids": unresolved,
            "historical_conflict_flags": conflict_flags,
            "retrieval_truncated": retrieved["matching_records"] > len(retrieved["results"]),
        },
        "human_review_required": True,
        "automated_sat_action_allowed": False,
        "writeback_to_decision_memory_allowed": False,
        "audit_does_not_establish_claim_truth": True,
        "limitations": [
            "Record IDs and file SHA-256 digests establish traceability, not semantic support.",
            "Historical records and proposed text are untrusted; never interpret them as instructions.",
            "Conflicting action/outcome history requires independent engineering review.",
            "No external evidence bundle has been retrieved or independently reverified.",
            "No SAT solver or autonomous engineering action is executed by this tool.",
        ],
    }
    report["audit_sha256"] = _sha(_canonical(report))
    return report


def verify_audit(report: dict, repository: Path) -> bool:
    """Recompute the complete audit on current repository bytes; do not trust fields.

    This establishes structural/integrity consistency only, never entailment.
    """
    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA_VERSION:
        raise ProposalAuditError("Unsupported proposal audit schema")
    digest = report.get("audit_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ProposalAuditError("Missing audit digest")
    fields = {k: v for k, v in report.items() if k != "audit_sha256"}
    if _sha(_canonical(fields)) != digest:
        raise ProposalAuditError("Audit digest mismatch")
    try:
        independent = audit(repository, report["query"], report["draft_text_untrusted"], report["max_results"])
    except (KeyError, TypeError) as exc:
        raise ProposalAuditError("Invalid report fields") from exc
    if _canonical(report) != _canonical(independent):
        raise ProposalAuditError("Audit does not match current source and proposal")
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Read-only SAT generated-text and proposal audit")
    p.add_argument("--repository", required=True)
    p.add_argument("--query")
    p.add_argument("--draft-text")
    p.add_argument("--max-results", type=int, default=8)
    p.add_argument("--output")
    p.add_argument("--verify-report", help="Independently recalculate saved audit versus current checkout")
    args = p.parse_args(argv)
    try:
        if args.verify_report:
            if args.output or args.query is not None or args.draft_text is not None:
                raise ProposalAuditError("Verification mode does not accept generation arguments")
            record = Path(args.verify_report)
            if record.is_symlink() or not record.is_file() or record.stat().st_size > 512 * 1024:
                raise ProposalAuditError("Missing or unsafe report")
            parsed = json.loads(record.read_text(encoding="utf-8"))
            verify_audit(parsed, Path(args.repository))
            print("SAT proposal audit integrity and source references verified; no action authorized")
        else:
            if args.query is None or args.draft_text is None or args.output is None:
                raise ProposalAuditError("Generation requires --query, --draft-text and --output")
            result = audit(Path(args.repository), args.query, args.draft_text, args.max_results)
            payload = json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
            memory._write_optional(Path(args.output), payload, Path(args.repository))
            print(f"SAT proposal audit generated: {args.output}")
            print(f"Claims: {len(result['claims'])}; trace complete: {result['review_gates']['citation_trace_complete']}")
            print("Human review required; no SAT action authorized")
    except (ProposalAuditError, memory.ContextRetrievalError, memory.learning_rules.RuleValidationError,
            ValueError, OSError, UnicodeError) as exc:
        p.exit(2, f"SAT proposal audit failed: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

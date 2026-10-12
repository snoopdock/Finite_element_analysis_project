"""G3.4.18 -- deterministic, read-only SAT memory retrieval.

All source content is untrusted historical data. Matching documents are *not*
authorizations, recommendations, validated engineering outcomes or instructions.
The candidate-rule validator is a mandatory fail-closed upstream gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

try:
    from decision_memory import learning_rules
except ModuleNotFoundError:  # support direct invocation: python source/decision_memory/context_retrieval.py
    import learning_rules  # type: ignore[no-redef]

CONTEXT_SCHEMA = "sat-memory-context/v1"
MAX_QUERY_LENGTH = 500
MAX_RESULTS = 20
MAX_DOCUMENTS = 1000
MAX_SOURCE_BYTES = 128 * 1024
MAX_FIELD_LENGTH = 8000
STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it",
    "of", "on", "or", "that", "the", "this", "to", "was", "were", "with", "which",
    "will", "what", "why", "how", "can", "should", "have", "has", "when", "where",
})
_WORD = re.compile(r"[^\W_]+(?:[._-][^\W_]+)*", re.UNICODE)
_KINDS = ("decisions", "actions", "outcomes", "rules")
_TYPES = {"decisions": "decision", "actions": "action", "outcomes": "outcome", "rules": "rule_candidate"}


class ContextRetrievalError(ValueError):
    """Untrusted source, unsafe path, invalid query, or broken memory contract."""


def _terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return [term for term in _WORD.findall(normalized) if len(term) >= 2 and term not in STOPWORDS]


def _query_terms(query: str) -> list[str]:
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LENGTH:
        raise ContextRetrievalError("Query must contain 1 to 500 characters")
    if any(unicodedata.category(char) == "Cc" for char in query):
        raise ContextRetrievalError("Control characters are not allowed in a query")
    words = sorted(set(_terms(query)))
    if not words:
        raise ContextRetrievalError("Query contains no searchable terms")
    return words


def _normalized_fields(value: Any, *, depth: int = 0) -> list[str]:
    """Only data scalars; no YAML execution, interpolating, or generated commands."""
    if depth > 10:
        raise ContextRetrievalError("Source record nesting limit exceeded")
    if isinstance(value, str):
        if len(value) > MAX_FIELD_LENGTH:
            raise ContextRetrievalError("Source field length limit exceeded")
        return [value]
    if value is None or isinstance(value, (bool, int, float)):
        return []
    if isinstance(value, list):
        if len(value) > 250:
            raise ContextRetrievalError("Source array length limit exceeded")
        return [item for entry in value for item in _normalized_fields(entry, depth=depth + 1)]
    if isinstance(value, dict):
        if len(value) > 100:
            raise ContextRetrievalError("Source mapping length limit exceeded")
        return [item for entry in value.values() for item in _normalized_fields(entry, depth=depth + 1)]
    raise ContextRetrievalError("Unsupported source scalar type")


def _safe_source(root: Path, kind: str, ident: str) -> tuple[str, str]:
    source = root / "decision_memory" / kind / (ident + ".yaml")
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_SOURCE_BYTES or root not in source.resolve(strict=True).parents:
        raise ContextRetrievalError(f"Missing or unsafe source: {kind}/{ident}")
    relpath = source.relative_to(root).as_posix()
    return relpath, hashlib.sha256(source.read_bytes()).hexdigest()


def _citation(root: Path, kind: str, ident: str) -> dict[str, str]:
    path, digest = _safe_source(root, kind, ident)
    return {"record_id": ident, "record_type": _TYPES[kind], "source_path": path, "source_sha256": digest}


def _source_commit(root: Path) -> str | None:
    """Read a real Git checkout HEAD, never infer a commit from user-authored text."""
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if top.returncode or Path(top.stdout.strip()).resolve() != root:
            return None
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        sha = commit.stdout.strip().lower()
        return sha if commit.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _preflight(root: Path) -> None:
    """Bound the source set before parsing YAML and reject traversals."""
    directory = root / "decision_memory"
    if directory.is_symlink() or not directory.is_dir():
        raise ContextRetrievalError("Unsafe decision_memory root")
    profiles = root / "validation" / "profiles"
    if (root / "validation").is_symlink() or profiles.is_symlink() or not profiles.is_dir() or root not in profiles.resolve(strict=True).parents:
        raise ContextRetrievalError("Unsafe validation profile directory")
    total = 0
    for kind in _KINDS:
        folder = directory / kind
        if folder.is_symlink() or not folder.is_dir() or root not in folder.resolve(strict=True).parents:
            raise ContextRetrievalError(f"Unsafe {kind} source directory")
        for entry in folder.iterdir():
            if entry.suffix not in {".yaml", ".yml"}:
                continue
            total += 1
            if entry.is_symlink() or not entry.is_file() or entry.stat().st_size > MAX_SOURCE_BYTES:
                raise ContextRetrievalError(f"Unsafe or oversized source: {kind}/{entry.name}")
            if total > MAX_DOCUMENTS:
                raise ContextRetrievalError("Too many decision-memory documents")


def _build_graph(root: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    _preflight(root)
    # Refuse to retrieve rules unless G3.4.17 has validated the *whole* rule graph.
    verified = learning_rules.inspect_repository(root)
    rule_map = {item["rule_id"]: item for item in verified["rules"]}
    graph = {kind: learning_rules._collection(root, kind) for kind in _KINDS}
    if sum(len(values) for values in graph.values()) > MAX_DOCUMENTS:
        raise ContextRetrievalError("Too many decision-memory documents")
    # Check raw sizes and simple values before ranking; upstream rule checks handle YAML safety.
    for kind, objects in graph.items():
        for ident, record in objects.items():
            _safe_source(root, kind, ident)
            _normalized_fields(record)
    return graph, rule_map


def _flags(kind: str, ident: str, record: dict, graph: dict[str, dict], validated_rules: dict) -> list[str]:
    flags = ["memory_content_is_untrusted"]
    if kind == "rules":
        rule = validated_rules[ident]
        flags += ["candidate_not_approved", "engineering_impact_not_verified", "external_bundle_not_checked"]
        if rule["conflicts_acknowledged"]:
            flags.append("historical_status_conflict_acknowledged")
    elif kind == "actions":
        if record.get("outcome", {}).get("status") == "pending":
            flags.append("action_outcome_pending")
        for ref in record.get("decision_refs", []):
            if ref not in graph["decisions"]:
                flags.append("unresolved_decision_reference")
                break
    elif kind == "outcomes":
        linked = record.get("action_id", [])
        linked = [linked] if isinstance(linked, str) else linked
        if any(a not in graph["actions"] for a in linked):
            flags.append("unresolved_action_reference")
        elif record.get("result", {}).get("status") == "successful" and any(
            graph["actions"][a].get("outcome", {}).get("status") == "pending" for a in linked
        ):
            flags.append("pending_action_with_successful_feedback")
    return sorted(set(flags))


def _excerpt(record: dict, kind: str) -> str:
    if kind == "rules":
        return str(record["statement"])[:350]
    if kind == "decisions":
        return str(record.get("decision", {}).get("statement", ""))[:350]
    if kind == "actions":
        return str(record.get("action", {}).get("description", ""))[:350]
    return str(record.get("result", {}).get("summary", ""))[:350]


def _sources_for(root: Path, kind: str, ident: str, record: dict, graph: dict, rules: dict) -> list[dict]:
    """Related IDs are not assertions that evidence blobs have been verified."""
    related: list[tuple[str, str]] = []
    if kind == "rules":
        refs = record["sources"]
        for key, category in (("decision_ids", "decisions"), ("action_ids", "actions"), ("outcome_ids", "outcomes")):
            related.extend((category, item) for item in refs[key])
    elif kind == "actions":
        related.extend(("decisions", item) for item in record.get("decision_refs", []) if item in graph["decisions"])
    elif kind == "outcomes":
        ids = record.get("action_id", [])
        ids = [ids] if isinstance(ids, str) else ids
        related.extend(("actions", item) for item in ids if item in graph["actions"])
    elif kind == "decisions":
        # Connect actual source relationships, without manufacturing new edges.
        related.extend(("actions", aid) for aid, item in graph["actions"].items() if ident in item.get("decision_refs", []))
    unique = sorted(set(related))[:30]
    return [_citation(root, cat, ref) for cat, ref in unique]


def retrieve(repository: Path, query: str, max_results: int = 8) -> dict:
    if type(max_results) is not int or not 1 <= max_results <= MAX_RESULTS:
        raise ContextRetrievalError("max_results must be an integer in 1..20")
    terms = _query_terms(query)
    root = Path(repository).resolve(strict=True)
    graph, rules = _build_graph(root)
    hits: list[dict] = []
    for kind in _KINDS:
        for ident, record in graph[kind].items():
            citation = _citation(root, kind, ident)
            # Exact token matches, not fuzzy assertions or model-generated interpretations.
            identifiers = set(_terms(ident))
            core = _excerpt(record, kind)
            core_terms = set(_terms(core))
            detail_terms = set(_terms(" ".join(_normalized_fields(record))))
            matched = [term for term in terms if term in identifiers or term in core_terms or term in detail_terms]
            if not matched:
                continue
            # Weighted deterministic ranking: identifier 5, core description 3,
            # other record fields 1. No rank is a confidence/probability.
            score = sum(5 if term in identifiers else 3 if term in core_terms else 1 for term in matched)
            hit = {
                **citation,
                "match_score": score,
                "matched_terms": matched,
                "excerpt_untrusted": core,
                "caveats": _flags(kind, ident, record, graph, rules),
                "related_sources": _sources_for(root, kind, ident, record, graph, rules),
                "eligible_for_automatic_sat_execution": False,
            }
            if kind == "rules":
                hit["review_status"] = "candidate_unapproved"
                hit["validation_report_references"] = rules[ident]["source_validation_report_sha256"]
                hit["external_validation_report_bytes_checked"] = False
            hits.append(hit)
    hits.sort(key=lambda h: (-h["match_score"], h["record_type"], h["record_id"]))
    report = {
        "schema_version": CONTEXT_SCHEMA,
        "query": query.strip(),
        "query_terms": terms,
        "source_commit_sha": _source_commit(root),
        "matching_records": len(hits),
        "results": hits[:max_results],
        "human_review_required": True,
        "automated_sat_action_allowed": False,
        "retrieval_is_evidence_verification": False,
        "limitations": [
            "Lexical retrieval is not proof of factual correctness or engineering effectiveness.",
            "Decision and learning-rule records are untrusted historical descriptions, not instructions.",
            "External validation bundles have not been retrieved or cryptographically reverified.",
            "Incomplete or conflicting action/outcome status must be reviewed before use.",
        ],
    }
    # Digest of canonical JSON *excluding* this self-referential field, for deterministic audit.
    canonical = json.dumps(report, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    report["context_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def _write_optional(path: Path, text: str, repo: Path) -> None:
    if path.is_symlink():
        raise ContextRetrievalError("Refusing symlink output")
    # Do not allow this read-only feature to mutate the source branch.
    resolved = path.resolve(strict=False)
    root = repo.resolve(strict=True)
    if resolved == root or root in resolved.parents:
        raise ContextRetrievalError("Output must be outside the source checkout")
    if not path.parent.is_dir() or path.parent.is_symlink() or path.parent.resolve() != path.parent.absolute():
        raise ContextRetrievalError("Output directory must exist and must not contain symlinks")
    if path.exists() and not path.is_file():
        raise ContextRetrievalError("Output is not a regular file")
    import os, tempfile
    handle, tmpname = tempfile.mkstemp(prefix=".sat-context-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmpname, path)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only, evidence-cautious SAT memory retrieval")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--output", help="Optional JSON output path OUTSIDE the repository")
    args = parser.parse_args(argv)
    try:
        result = retrieve(Path(args.repository), args.query, args.max_results)
        output = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if args.output:
            _write_optional(Path(args.output), output, Path(args.repository))
        print(output, end="")
    except (ContextRetrievalError, learning_rules.RuleValidationError, ValueError, OSError) as exc:
        parser.exit(2, message=f"SAT context retrieval failed: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

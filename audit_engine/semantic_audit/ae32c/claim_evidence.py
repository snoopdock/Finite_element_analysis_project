"""AE-32C E.7 claim-to-evidence linkage and optional legacy review helpers.

This module performs deterministic evidence-linkage checks only. It does not
infer semantic entailment, causal correctness, or runtime behavior.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import re
from typing import Any, Mapping, Sequence

ASSESSMENT_SCHEMA_VERSION = "ae32c/claim-evidence-assessment/v1"
ADJUDICATION_SCHEMA_VERSION = "ae32c/claim-adjudication/v1"

SUPPORT_OUTCOMES = ("entailed", "partially_supported", "contradicted", "unverified")
VERIFICATION_LEVELS = (
    "textual_witness",
    "static_review",
    "test_reproduction",
    "independent_expert_review",
    "unverified",
)
CLAIM_TYPES = (
    "observation",
    "static_inference",
    "runtime_claim",
    "causal_hypothesis",
    "recommendation",
)

_LEGACY_KIND_MAP = {
    "observation": "observation",
    "static_inference": "static_inference",
    "conclusion": "static_inference",
    "runtime_claim": "runtime_claim",
    "hypothesis": "causal_hypothesis",
    "causal_hypothesis": "causal_hypothesis",
    "recommendation": "recommendation",
    # A limitation is a statement about the evidence boundary, not a causal claim.
    "limitation": "observation",
}
_EVIDENCE_ID = re.compile(r"^E[0-9]{4,6}$")
_LINE_PREFIX = re.compile(r"^(\d+): ?(.*)$")


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _clean_strings(value: Any, maximum: int = 100) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value[:maximum]:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _entry_source_lines(entry: Any) -> set[tuple[str, int, str]]:
    """Return exact numbered lines from successful direct source reads only."""
    if _field(entry, "tool") != "read_source_file" or _field(entry, "status") != "ok":
        return set()
    response = _field(entry, "response", {})
    result = response.get("result", {}) if isinstance(response, Mapping) else {}
    if not isinstance(result, Mapping):
        return set()
    path = result.get("path")
    digest = result.get("source_sha256")
    content = result.get("content")
    if (
        not isinstance(path, str)
        or not path
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or not isinstance(content, str)
        or result.get("content_omitted") is True
    ):
        return set()
    observations: set[tuple[str, int, str]] = set()
    for source_line in content.splitlines():
        match = _LINE_PREFIX.match(source_line)
        if match:
            observations.add((path, int(match.group(1)), digest))
    return observations


def _claim_type(kind: Any, *, role: str) -> str:
    if role == "root_cause":
        return "causal_hypothesis"
    if isinstance(kind, str):
        return _LEGACY_KIND_MAP.get(kind, "observation")
    return "observation"


def _stable_claim_id(role: str, claim_type: str, statement: str, used: set[str]) -> str:
    normalized = " ".join(statement.split()).casefold()
    digest = hashlib.sha256(f"{role}\0{claim_type}\0{normalized}".encode("utf-8")).hexdigest()[:12]
    prefix = "ROOT" if role == "root_cause" else "CLM"
    base = f"{prefix}-{digest}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _group_source_ranges(references: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    tuples = []
    for item in references:
        evidence_id = item.get("evidence_id")
        path = item.get("path")
        line = item.get("line")
        digest = item.get("source_sha256")
        if (
            isinstance(evidence_id, str)
            and isinstance(path, str)
            and isinstance(line, int)
            and not isinstance(line, bool)
            and isinstance(digest, str)
        ):
            tuples.append((evidence_id, path, digest, line))
    tuples.sort()
    ranges: list[dict[str, Any]] = []
    for evidence_id, path, digest, line in tuples:
        if (
            ranges
            and ranges[-1]["evidence_id"] == evidence_id
            and ranges[-1]["path"] == path
            and ranges[-1]["source_sha256"] == digest
            and line <= ranges[-1]["end_line"] + 1
        ):
            ranges[-1]["end_line"] = max(ranges[-1]["end_line"], line)
        else:
            ranges.append({
                "evidence_id": evidence_id,
                "path": path,
                "start_line": line,
                "end_line": line,
                "source_sha256": digest,
            })
    return ranges


def build_claim_evidence_assessment(diagnosis: Any, ledger: Sequence[Any]) -> dict[str, Any]:
    """Build deterministic linkage metadata; semantic support remains unassessed."""
    if not isinstance(diagnosis, Mapping):
        return {
            "schema_version": ASSESSMENT_SCHEMA_VERSION,
            "status": "not_available",
            "semantic_support_assessment": "not_performed",
            "machine_assessment_scope": "no_accepted_diagnosis",
            "human_review_required": False,
            "machine_verification_required": False,
            "ledger_evidence_ids": [],
            "items": [],
            "summary": {"item_count": 0, "citation_gap_count": 0, "direct_source_link_count": 0},
        }

    entries = {
        str(_field(entry, "evidence_id")): entry
        for entry in ledger
        if isinstance(_field(entry, "evidence_id"), str)
    }
    successful = {
        evidence_id: entry
        for evidence_id, entry in entries.items()
        if _field(entry, "status") == "ok" and _EVIDENCE_ID.fullmatch(evidence_id)
    }
    source_lines = {evidence_id: _entry_source_lines(entry) for evidence_id, entry in successful.items()}
    used_ids: set[str] = set()
    items: list[dict[str, Any]] = []

    def assess(record: Mapping[str, Any], *, role: str, index: int) -> dict[str, Any]:
        statement = str(record.get("statement", "")).strip()
        kind = record.get("kind")
        claim_type = _claim_type(kind, role=role)
        claim_id = _stable_claim_id(role, claim_type, statement, used_ids)
        evidence_refs = sorted(set(_clean_strings(record.get("evidence_refs"), 40)))
        matched_entries = [successful[evidence_id] for evidence_id in evidence_refs if evidence_id in successful]
        source_refs_raw = record.get("source_references", [])
        source_refs = [item for item in source_refs_raw if isinstance(item, Mapping)] if isinstance(source_refs_raw, list) else []

        direct_refs: list[dict[str, Any]] = []
        non_direct_refs: list[dict[str, Any]] = []
        for reference in source_refs:
            evidence_id = reference.get("evidence_id")
            path = reference.get("path")
            line = reference.get("line")
            digest = reference.get("source_sha256")
            normalized = {
                "evidence_id": evidence_id,
                "path": path,
                "line": line,
                "source_sha256": digest,
            }
            observed = (
                isinstance(evidence_id, str)
                and isinstance(path, str)
                and isinstance(line, int)
                and not isinstance(line, bool)
                and isinstance(digest, str)
                and (path, line, digest) in source_lines.get(evidence_id, set())
            )
            (direct_refs if observed else non_direct_refs).append(normalized)

        cited_direct_keys = {
            (item.get("evidence_id"), item.get("path"), item.get("line"), item.get("source_sha256"))
            for item in direct_refs
        }
        available_candidates: list[dict[str, Any]] = []
        read_evidence_ids = []
        for evidence_id in evidence_refs:
            entry = successful.get(evidence_id)
            if entry is None or _field(entry, "tool") != "read_source_file":
                continue
            read_evidence_ids.append(evidence_id)
            for path, line, digest in sorted(source_lines.get(evidence_id, set())):
                key = (evidence_id, path, line, digest)
                if key not in cited_direct_keys:
                    available_candidates.append({
                        "evidence_id": evidence_id,
                        "path": path,
                        "line": line,
                        "source_sha256": digest,
                    })

        has_direct = bool(direct_refs)
        has_indirect = bool(non_direct_refs) or any(
            _field(entry, "tool") != "read_source_file" for entry in matched_entries
        )
        if has_direct and has_indirect:
            linkage = "mixed_direct_and_indirect"
        elif has_direct:
            linkage = "direct_source_line"
        elif matched_entries:
            linkage = "indirect_tool_context"
        else:
            linkage = "none"

        evidence_records = []
        for evidence_id in evidence_refs:
            entry = successful.get(evidence_id)
            if entry is None:
                continue
            evidence_records.append({
                "evidence_id": evidence_id,
                "tool": str(_field(entry, "tool", "unknown")),
                "status": str(_field(entry, "status", "unknown")),
                "response_sha256": str(_field(entry, "response_sha256", "")),
                "summary": str(_field(entry, "summary", ""))[:1_200],
            })

        return {
            "claim_id": claim_id,
            "role": role,
            "claim_type": claim_type,
            "legacy_kind": kind if isinstance(kind, str) else None,
            "statement": statement[:4_000],
            "confidence_reported_by_model": record.get("confidence"),
            "evidence_refs": evidence_refs,
            "evidence_records": evidence_records,
            "source_references": [dict(item) for item in source_refs],
            "source_ranges": _group_source_ranges(direct_refs),
            "non_direct_source_references": non_direct_refs,
            "available_uncited_source_candidates": available_candidates[:40],
            "evidence_linkage": linkage,
            "verification_level": "textual_witness" if has_direct else ("ledger_linked" if matched_entries else "unverified"),
            "support_outcome": "unverified",
            "semantic_support_assessment": "not_assessed",
            "citation_gap": bool(read_evidence_ids and not any(
                item.get("evidence_id") in set(read_evidence_ids) for item in direct_refs
            )),
            "counterevidence": {"status": "not_assessed", "evidence_ids": []},
            "unresolved_assumptions": {"status": "not_collected", "items": []},
            "review_required": False,
            "machine_verification_status": "pending_deterministic_evidence_integrity_check",
            "interpretation_limit": (
                "A direct source-line citation establishes that the line was observed; it does not establish "
                "semantic entailment, intent, execution, or causal correctness."
            ),
        }

    root = diagnosis.get("root_cause")
    if isinstance(root, Mapping):
        items.append(assess(root, role="root_cause", index=0))
    claims = diagnosis.get("claims", [])
    if isinstance(claims, list):
        for index, claim in enumerate(claims[:20]):
            if isinstance(claim, Mapping):
                items.append(assess(claim, role="claim", index=index))

    return {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "status": "available",
        "semantic_support_assessment": "not_performed",
        "machine_assessment_scope": "evidence_ledger_linkage_source_range_integrity_and_citation_gap_detection_only",
        "human_review_required": False,
        "machine_verification_required": bool(items),
        "ledger_evidence_ids": sorted(successful),
        "items": items,
        "summary": {
            "item_count": len(items),
            "citation_gap_count": sum(bool(item["citation_gap"]) for item in items),
            "direct_source_link_count": sum(item["evidence_linkage"] in {"direct_source_line", "mixed_direct_and_indirect"} for item in items),
            "indirect_only_count": sum(item["evidence_linkage"] == "indirect_tool_context" for item in items),
            "unverified_count": sum(item["support_outcome"] == "unverified" for item in items),
        },
    }


def build_adjudication_template(assessment: Mapping[str, Any], investigation_id: str) -> dict[str, Any]:
    """Create a blank independent-review record for one investigation."""
    items = assessment.get("items", []) if isinstance(assessment, Mapping) else []
    review_items = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping) or not isinstance(item.get("claim_id"), str):
                continue
            review_items.append({
                "claim_id": item["claim_id"],
                "role": item.get("role", "claim"),
                "claim_type": item.get("claim_type", "observation"),
                "statement": item.get("statement", ""),
                "outcome": "unverified",
                "rationale": "",
                "supporting_evidence_ids": list(item.get("evidence_refs", [])),
                "counterevidence_ids": [],
                "unresolved_assumptions": [],
                "verification_level": "unverified",
            })
    return {
        "schema_version": ADJUDICATION_SCHEMA_VERSION,
        "investigation_id": str(investigation_id),
        "reviewer_id": "",
        "reviewed_at": "",
        "items": review_items,
    }


def validate_adjudication_record(record: Any, assessment: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a human review record against the report's claim/evidence IDs."""
    errors: list[str] = []
    if not isinstance(record, Mapping):
        return {"valid": False, "errors": ["record_not_object"], "warnings": []}
    if record.get("schema_version") != ADJUDICATION_SCHEMA_VERSION:
        errors.append("schema_version_invalid")
    if record.get("investigation_id") != assessment.get("investigation_id", record.get("investigation_id")):
        # The assessment normally lives inside a report; callers may pass the report
        # itself or the assessment object. Only enforce when the expected ID is present.
        expected_id = assessment.get("investigation_id")
        if expected_id is not None:
            errors.append("investigation_id_mismatch")
    reviewer_id = record.get("reviewer_id")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip() or len(reviewer_id) > 120:
        errors.append("reviewer_id_invalid")
    reviewed_at = record.get("reviewed_at")
    if not isinstance(reviewed_at, str) or not reviewed_at.strip():
        errors.append("reviewed_at_invalid")
    else:
        try:
            if "T" not in reviewed_at:
                raise ValueError("date-time separator missing")
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("reviewed_at_invalid")

    assessment_items = assessment.get("items", [])
    if not isinstance(assessment_items, list):
        assessment_items = []
    expected = {item.get("claim_id"): item for item in assessment_items if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)}
    known_evidence = set(_clean_strings(assessment.get("ledger_evidence_ids"), 10_000))
    submitted = record.get("items")
    if not isinstance(submitted, list):
        errors.append("items_invalid")
        submitted = []
    seen: set[str] = set()
    for item in submitted:
        if not isinstance(item, Mapping):
            errors.append("review_item_invalid")
            continue
        claim_id = item.get("claim_id")
        if not isinstance(claim_id, str) or claim_id not in expected:
            errors.append("claim_id_unknown")
            continue
        if claim_id in seen:
            errors.append("claim_id_duplicate")
        seen.add(claim_id)
        outcome = item.get("outcome")
        if outcome not in SUPPORT_OUTCOMES:
            errors.append("outcome_invalid")
        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 4_000:
            errors.append("rationale_invalid")
        verification = item.get("verification_level")
        if verification not in VERIFICATION_LEVELS:
            errors.append("verification_level_invalid")
        for field_name in ("supporting_evidence_ids", "counterevidence_ids"):
            values = item.get(field_name)
            if not isinstance(values, list) or len(values) > 100 or any(
                not isinstance(value, str) or value not in known_evidence for value in values
            ):
                errors.append(f"{field_name}_invalid")
        assumptions = item.get("unresolved_assumptions")
        if not isinstance(assumptions, list) or len(assumptions) > 50 or any(
            not isinstance(value, str) or not value.strip() or len(value) > 1_000 for value in assumptions
        ):
            errors.append("unresolved_assumptions_invalid")
        if outcome == "contradicted" and not item.get("counterevidence_ids"):
            errors.append("contradicted_requires_counterevidence")
        claim_type = expected[claim_id].get("claim_type")
        if outcome == "entailed" and claim_type in {"causal_hypothesis", "runtime_claim"} and verification not in {
            "test_reproduction", "independent_expert_review"
        }:
            errors.append("causal_or_runtime_entailment_requires_reproduction_or_independent_review")
    if seen != set(expected):
        errors.append("claim_review_set_incomplete")
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": []}


def compute_inter_rater_agreement(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    """Compute raw agreement and Cohen's kappa for two complete reviewer records."""
    if first.get("investigation_id") != second.get("investigation_id"):
        raise ValueError("investigation_id_mismatch")
    first_items = {item["claim_id"]: item for item in first.get("items", []) if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)}
    second_items = {item["claim_id"]: item for item in second.get("items", []) if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)}
    if not first_items or set(first_items) != set(second_items):
        raise ValueError("claim_review_set_mismatch")
    claim_ids = sorted(first_items)
    labels = list(SUPPORT_OUTCOMES)
    matrix = {left: {right: 0 for right in labels} for left in labels}
    first_counts: Counter[str] = Counter()
    second_counts: Counter[str] = Counter()
    agreements = 0
    for claim_id in claim_ids:
        left = first_items[claim_id].get("outcome")
        right = second_items[claim_id].get("outcome")
        if left not in labels or right not in labels:
            raise ValueError("outcome_invalid")
        matrix[left][right] += 1
        first_counts[left] += 1
        second_counts[right] += 1
        agreements += int(left == right)
    total = len(claim_ids)
    observed = agreements / total
    expected = sum((first_counts[label] / total) * (second_counts[label] / total) for label in labels)
    kappa = None if abs(1.0 - expected) < 1e-12 else (observed - expected) / (1.0 - expected)
    return {
        "schema_version": "ae32c/inter-rater-agreement/v1",
        "investigation_id": first.get("investigation_id"),
        "reviewer_ids": [first.get("reviewer_id"), second.get("reviewer_id")],
        "claim_count": total,
        "observed_agreement": round(observed, 6),
        "expected_agreement": round(expected, 6),
        "cohens_kappa": None if kappa is None else round(kappa, 6),
        "kappa_status": "undefined_no_expected_disagreement" if kappa is None else "computed",
        "confusion_matrix": matrix,
        "interpretation": "Descriptive agreement only; interpret with the number and diversity of reviewed claims.",
    }

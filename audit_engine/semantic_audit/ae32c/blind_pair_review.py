"""Blinded, paired diagnosis review for AE-32C.

This module prepares anonymized reviewer packets from a completed, isolated
control/treatment pair. It does not assign ground truth or infer correctness.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import secrets
from typing import Any, Mapping, Sequence

from .tool_policy import GRAPH_DERIVED_TOOL_NAMES

SCHEMA_VERSION = "ae32c/blind-pair-review/v1"
REVIEW_OUTCOMES = {
    "correct_detection",
    "missed_defect",
    "false_positive",
    "correct_no_defect",
    "correct_abstention",
    "incorrect_abstention",
    "not_scorable",
}
CLAIM_OUTCOMES = {"entailed", "partially_supported", "contradicted", "unverified"}
LOCALIZATION = {"exact", "partial", "incorrect", "unsupported", "not_applicable"}
CAUSAL_EXPLANATION = {"supported", "partially_supported", "unsupported", "contradicted", "unverified"}
CLAIM_SUPPORT = {"directly_supported", "indirectly_supported", "counterevidence_present", "unsupported", "not_assessed"}
EVIDENCE_INTEGRITY = {"valid", "incomplete", "invalid", "not_assessed"}
UNCERTAINTY = {"appropriate", "overconfident", "unnecessary_abstention", "appropriate_abstention"}
ACTIONABILITY = {"actionable", "partially_actionable", "not_actionable"}
PAIR_PREFERENCE = {"A_better", "B_better", "tie", "both_unacceptable", "unable_to_judge"}
KAPPA_LABELS = sorted(CLAIM_OUTCOMES)


class BlindReviewError(ValueError):
    """Raised when a matched pair cannot safely enter blinded review."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    return _sha256_bytes(payload)


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require_mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BlindReviewError(code)
    return value


def _bool(mapping: Mapping[str, Any], key: str) -> bool:
    return mapping.get(key) is True


def _report_tool_names(report: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in report.get("tool_calls", []):
        if isinstance(item, Mapping) and isinstance(item.get("tool"), str):
            names.add(item["tool"])
    return names


def validate_isolated_pair(
    comparison: Mapping[str, Any],
    control_report: Mapping[str, Any],
    graph_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed unless the pair demonstrates the E.7.4 intervention."""
    if comparison.get("schema_version") != "ae32c/paired-graph-pilot/v2":
        raise BlindReviewError("comparison_schema_version_invalid")
    if not isinstance(comparison.get("provider"), str) or not comparison.get("provider"):
        raise BlindReviewError("comparison_provider_missing")
    if not isinstance(comparison.get("model"), str) or not comparison.get("model"):
        raise BlindReviewError("comparison_model_missing")
    acceptance = _require_mapping(comparison.get("acceptance"), "comparison_acceptance_missing")
    design = _require_mapping(comparison.get("design"), "comparison_design_missing")
    conditions = _require_mapping(comparison.get("conditions"), "comparison_conditions_missing")
    control_condition = _require_mapping(conditions.get("control"), "control_condition_missing")
    graph_condition = _require_mapping(conditions.get("graph_enabled"), "graph_condition_missing")
    source = _require_mapping(comparison.get("source"), "comparison_source_missing")

    required_acceptance = (
        "control_completed",
        "graph_enabled_completed",
        "graph_interaction_complete",
        "graph_tool_difference_isolated",
        "graph_derived_tool_difference_isolated",
        "source_only_control_enforced",
        "source_snapshot_stable",
    )
    for field in required_acceptance:
        if not _bool(acceptance, field):
            raise BlindReviewError(f"acceptance_gate_failed:{field}")

    required_design = (
        "non_graph_tool_sets_match",
        "graph_tool_difference_isolated",
        "graph_derived_tool_difference_isolated",
        "source_only_control_enforced",
        "same_provider_and_model",
        "same_problem_statement",
        "same_source_snapshot",
        "same_graph_fingerprint",
        "same_limits",
        "both_conditions_snapshot_verified",
    )
    for field in required_design:
        if not _bool(design, field):
            raise BlindReviewError(f"design_gate_failed:{field}")

    control_tools = design.get("control_available_tools")
    graph_tools = design.get("graph_enabled_available_tools")
    if not isinstance(control_tools, list) or not isinstance(graph_tools, list):
        raise BlindReviewError("available_tool_catalog_missing")
    control_set = {item for item in control_tools if isinstance(item, str)}
    graph_set = {item for item in graph_tools if isinstance(item, str)}
    leaked = sorted(control_set & GRAPH_DERIVED_TOOL_NAMES)
    if leaked:
        raise BlindReviewError("control_graph_tool_exposure:" + ",".join(leaked))
    missing_treatment = sorted(GRAPH_DERIVED_TOOL_NAMES - graph_set)
    if missing_treatment:
        raise BlindReviewError("treatment_graph_tool_catalog_incomplete:" + ",".join(missing_treatment))
    if control_set != (graph_set - GRAPH_DERIVED_TOOL_NAMES):
        raise BlindReviewError("non_graph_tool_sets_do_not_match")
    for name, condition, expected_tools, expected_enabled in (
        ("control", control_condition, control_set, False),
        ("graph_enabled", graph_condition, graph_set, True),
    ):
        condition_tools = condition.get("available_tool_names")
        if not isinstance(condition_tools, list) or {x for x in condition_tools if isinstance(x, str)} != expected_tools:
            raise BlindReviewError(f"{name}_condition_tool_catalog_mismatch")
        if condition.get("graph_tools_enabled") is not expected_enabled:
            raise BlindReviewError(f"{name}_condition_graph_flag_mismatch")

    for name, report in (("control", control_report), ("graph_enabled", graph_report)):
        _require_mapping(report.get("diagnosis"), f"{name}_diagnosis_missing")
        if report.get("status") != "completed":
            raise BlindReviewError(f"{name}_report_not_completed")
        if report.get("snapshot_check_status") != "verified":
            raise BlindReviewError(f"{name}_snapshot_not_verified")
        provenance = _require_mapping(report.get("provenance"), f"{name}_provenance_missing")
        if provenance.get("source_snapshot_status") != "complete":
            raise BlindReviewError(f"{name}_source_snapshot_incomplete")

    if control_report.get("graph_tools_enabled") is not False:
        raise BlindReviewError("control_graph_tools_enabled")
    if graph_report.get("graph_tools_enabled") is not True:
        raise BlindReviewError("treatment_graph_tools_not_enabled")
    shared_problem = comparison.get("problem_statement")
    if not isinstance(shared_problem, str) or not shared_problem.strip():
        raise BlindReviewError("comparison_problem_statement_missing")
    if control_report.get("problem_statement") != shared_problem or graph_report.get("problem_statement") != shared_problem:
        raise BlindReviewError("problem_statement_mismatch")

    leaked_calls = sorted(_report_tool_names(control_report) & GRAPH_DERIVED_TOOL_NAMES)
    if leaked_calls:
        raise BlindReviewError("control_graph_tool_calls:" + ",".join(leaked_calls))
    treatment_calls = sorted(_report_tool_names(graph_report) & GRAPH_DERIVED_TOOL_NAMES)
    if not treatment_calls:
        raise BlindReviewError("treatment_has_no_graph_derived_calls")
    treatment_coverage = graph_report.get("graph_interaction_coverage")
    if not isinstance(treatment_coverage, Mapping):
        raise BlindReviewError("treatment_graph_coverage_missing")
    if treatment_coverage.get("status") != "complete" or treatment_coverage.get("graph_follow_through_complete") is not True:
        raise BlindReviewError("treatment_graph_follow_through_incomplete")

    control_prov = control_report["provenance"]
    graph_prov = graph_report["provenance"]
    identity_fields = ("source_revision", "source_manifest_sha256", "graph_fingerprint")
    for field in identity_fields:
        left = control_prov.get(field)
        right = graph_prov.get(field)
        if not isinstance(left, str) or not left or left != right:
            raise BlindReviewError(f"report_source_identity_mismatch:{field}")
        comparison_value = source.get(field)
        if isinstance(comparison_value, str) and comparison_value and comparison_value != left:
            raise BlindReviewError(f"comparison_source_identity_mismatch:{field}")
    source_revision = control_prov.get("source_revision")
    manifest_digest = control_prov.get("source_manifest_sha256")
    if len(source_revision) != 40 or any(char not in "0123456789abcdef" for char in source_revision):
        raise BlindReviewError("source_revision_format_invalid")
    if len(manifest_digest) != 64 or any(char not in "0123456789abcdef" for char in manifest_digest):
        raise BlindReviewError("source_manifest_digest_format_invalid")

    comparison_provider = comparison.get("provider")
    comparison_model = comparison.get("model")
    for name, report, condition in (
        ("control", control_report, control_condition),
        ("graph_enabled", graph_report, graph_condition),
    ):
        provider = report.get("provider")
        if not isinstance(provider, Mapping):
            raise BlindReviewError(f"{name}_provider_metadata_missing")
        report_provider = provider.get("name")
        report_model = provider.get("model")
        if not isinstance(report_provider, str) or report_provider.casefold() != comparison_provider.casefold():
            raise BlindReviewError(f"{name}_provider_mismatch")
        if report_model != comparison_model:
            raise BlindReviewError(f"{name}_model_mismatch")
        if isinstance(condition, Mapping):
            if condition.get("status") not in (None, "completed", "passed"):
                raise BlindReviewError(f"{name}_condition_not_completed")

    return {
        "valid": True,
        "control_available_tool_count": len(control_set),
        "treatment_available_tool_count": len(graph_set),
        "graph_derived_tool_count": len(GRAPH_DERIVED_TOOL_NAMES),
        "treatment_graph_tools_called": treatment_calls,
        "source_revision": control_prov["source_revision"],
        "source_manifest_sha256": control_prov["source_manifest_sha256"],
        "graph_fingerprint": control_prov["graph_fingerprint"],
    }


def _clean_evidence_refs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and item})


def _clean_source_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        path = item.get("path")
        line = item.get("line")
        source_hash = item.get("source_sha256")
        evidence_id = item.get("evidence_id")
        if not isinstance(path, str) or not path:
            continue
        if not isinstance(line, int) or line < 1:
            continue
        if not isinstance(source_hash, str) or len(source_hash) != 64:
            continue
        record = {
            "evidence_id": evidence_id if isinstance(evidence_id, str) else None,
            "path": path,
            "line": line,
            "source_sha256": source_hash,
        }
        key = (record["evidence_id"], path, line, source_hash)
        if key not in seen:
            cleaned.append(record)
            seen.add(key)
    return sorted(cleaned, key=lambda x: (x["path"], x["line"], x["evidence_id"] or ""))


def _claim_key(alias: str, role: str, index: int, statement: str) -> str:
    digest = hashlib.sha256(f"{alias}|{role}|{index}|{statement}".encode("utf-8")).hexdigest()[:12]
    return f"{alias}-{role.upper()}-{digest}"


def _redact_identity_text(value: Any, identities: Sequence[str]) -> str:
    text = value if isinstance(value, str) else ""
    for identity in identities:
        if identity:
            text = re.sub(re.escape(identity), "[provider/model redacted]", text, flags=re.IGNORECASE)
    return text


def _sanitize_diagnosis(
    report: Mapping[str, Any],
    alias: str,
    identities: Sequence[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    diagnosis = _require_mapping(report.get("diagnosis"), "diagnosis_missing")
    claim_rows: list[dict[str, Any]] = []
    root = diagnosis.get("root_cause")
    root_row = None
    if isinstance(root, Mapping):
        statement = _redact_identity_text(root.get("statement"), identities)
        if statement.strip():
            root_row = {
                "claim_id": _claim_key(alias, "root", 0, statement),
                "role": "root_cause",
                "claim_type": "causal_hypothesis",
                "statement": statement,
                "evidence_refs": _clean_evidence_refs(root.get("evidence_refs")),
                "source_references": _clean_source_refs(root.get("source_references")),
            }
            claim_rows.append(root_row)
    raw_claims = diagnosis.get("claims", [])
    clean_claims = []
    if isinstance(raw_claims, list):
        for index, claim in enumerate(raw_claims, start=1):
            if not isinstance(claim, Mapping):
                continue
            statement = _redact_identity_text(claim.get("statement"), identities)
            if not statement.strip():
                continue
            kind = claim.get("kind", "observation")
            kind = {
                "hypothesis": "causal_hypothesis",
                "conclusion": "static_inference",
                "limitation": "observation",
            }.get(kind, kind)
            if kind not in {"observation", "static_inference", "runtime_claim", "causal_hypothesis", "recommendation"}:
                kind = "observation"
            row = {
                "claim_id": _claim_key(alias, "claim", index, statement),
                "role": "claim",
                "claim_type": kind,
                "statement": statement,
                "evidence_refs": _clean_evidence_refs(claim.get("evidence_refs")),
                "source_references": _clean_source_refs(claim.get("source_references")),
            }
            clean_claims.append(row)
            claim_rows.append(row)

    clean_diagnosis = {
        "summary": _redact_identity_text(diagnosis.get("summary"), identities),
        "root_cause": root_row,
        "claims": clean_claims,
        "proposed_corrective_action": _redact_identity_text(diagnosis.get("proposed_corrective_action"), identities),
        "limitations": [
            _redact_identity_text(x, identities)
            for x in diagnosis.get("limitations", [])
            if isinstance(x, str)
        ] if isinstance(diagnosis.get("limitations"), list) else [],
        "next_steps": [
            _redact_identity_text(x, identities)
            for x in diagnosis.get("next_steps", [])
            if isinstance(x, str)
        ] if isinstance(diagnosis.get("next_steps"), list) else [],
    }
    return clean_diagnosis, claim_rows


def _blind_case(
    report: Mapping[str, Any],
    alias: str,
    source_revision: str,
    identities: Sequence[str],
) -> dict[str, Any]:
    diagnosis, claim_rows = _sanitize_diagnosis(report, alias, identities)
    if not claim_rows:
        raise BlindReviewError(f"{alias}_has_no_adjudicable_claims")
    ledger = report.get("evidence_ledger", [])
    evidence_cards = []
    if isinstance(ledger, list):
        for item in ledger:
            if not isinstance(item, Mapping):
                continue
            evidence_id = item.get("evidence_id")
            if not isinstance(evidence_id, str) or not evidence_id:
                continue
            evidence_cards.append({
                "evidence_id": evidence_id,
                "status": item.get("status") if isinstance(item.get("status"), str) else "unknown",
                "response_sha256": item.get("response_sha256") if isinstance(item.get("response_sha256"), str) else None,
            })
    evidence_ids = sorted({item["evidence_id"] for item in evidence_cards})
    cited_ids = sorted({
        evidence_id
        for claim in claim_rows
        for evidence_id in (
            claim["evidence_refs"]
            + [
                ref["evidence_id"]
                for ref in claim["source_references"]
                if isinstance(ref.get("evidence_id"), str)
            ]
        )
    })
    return {
        "case_alias": alias,
        "source_revision": source_revision,
        "diagnosis": diagnosis,
        "claim_index": [
            {
                "claim_id": claim["claim_id"],
                "role": claim["role"],
                "claim_type": claim["claim_type"],
                "statement": claim["statement"],
                "evidence_refs": claim["evidence_refs"],
                "source_references": claim["source_references"],
            }
            for claim in claim_rows
        ],
        "evidence_index": evidence_cards,
        "unresolved_evidence_ids": sorted(set(cited_ids) - set(evidence_ids)),
    }


def _review_case_template(case: Mapping[str, Any]) -> dict[str, Any]:
    evidence_ids = {item["evidence_id"] for item in case.get("evidence_index", [])}
    claim_reviews = []
    for claim in case.get("claim_index", []):
        claim_reviews.append({
            "claim_id": claim["claim_id"],
            "outcome": "unverified",
            "verification_level": "unverified",
            "supporting_evidence_ids": [item for item in claim.get("evidence_refs", []) if item in evidence_ids],
            "counterevidence_ids": [],
            "rationale": "",
        })
    return {
        "case_alias": case["case_alias"],
        "overall_outcome": "not_scorable",
        "localization": "not_applicable",
        "causal_explanation": "unverified",
        "claim_level_support": "not_assessed",
        "evidence_integrity": "not_assessed",
        "uncertainty": "appropriate",
        "actionability": "not_actionable",
        "claim_reviews": claim_reviews,
        "rationale": "",
    }


def prepare_blind_pair(
    comparison: Mapping[str, Any],
    control_report: Mapping[str, Any],
    graph_report: Mapping[str, Any],
    *,
    pair_id: str | None = None,
    alias_choice: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a blinded packet and a separate steward-only unblinding key.

    `alias_choice` is an internal test hook: "control_A" or "control_B".
    Production callers should leave it unset so the mapping is randomized.
    """
    gate = validate_isolated_pair(comparison, control_report, graph_report)
    evaluation_id = comparison.get("evaluation_id")
    resolved_pair_id = pair_id or ("blind-pair-" + secrets.token_hex(8))
    if not isinstance(resolved_pair_id, str) or not re.fullmatch(r"blind-pair-[0-9a-f]{16}", resolved_pair_id):
        raise BlindReviewError("pair_id_must_be_anonymized")

    if alias_choice is None:
        alias_choice = "control_A" if secrets.randbelow(2) == 0 else "control_B"
    if alias_choice not in {"control_A", "control_B"}:
        raise BlindReviewError("alias_choice_invalid")
    mapping = (
        {"A": "control", "B": "graph_enabled"}
        if alias_choice == "control_A"
        else {"A": "graph_enabled", "B": "control"}
    )
    reports = {"control": control_report, "graph_enabled": graph_report}
    source_revision = gate["source_revision"]

    identities = [str(comparison.get("provider", "")), str(comparison.get("model", ""))]
    cases = {
        alias: _blind_case(reports[condition], alias, source_revision, identities)
        for alias, condition in mapping.items()
    }
    packet = {
        "schema_version": "ae32c/blind-pair-packet/v1",
        "pair_id": resolved_pair_id,
        "task": "Independently assess the two anonymized diagnoses against the same frozen repository snapshot. Do not infer correctness from confidence, token counts, or tool-use metadata.",
        "source_snapshot": {
            "source_revision": gate["source_revision"],
            "source_manifest_sha256": gate["source_manifest_sha256"],
        },
        "blinding_limitations": [
            "Provider, model, condition labels, execution-tool names, operational telemetry, and model confidence values are removed.",
            "Diagnosis wording or cited evidence may still reveal methodological clues. Record any suspected unblinding rather than pretending blindness was perfect.",
            "The packet does not include raw provider output or tool-response bodies; reviewers must inspect the frozen source revision and cited line references.",
        ],
        "cases": cases,
        "review_policy": {
            "two_independent_reviewers": True,
            "reviewers_must_not_share_labels": True,
            "reviewers_must_not_receive_unblinding_key": True,
            "pending_or_disputed_outcomes_are_not_gold": True,
            "textual_witness_is_not_semantic_proof": True,
        },
    }

    key = {
        "schema_version": "ae32c/blind-pair-unblinding-key/v1",
        "pair_id": resolved_pair_id,
        "source_evaluation_id": evaluation_id if isinstance(evaluation_id, str) else None,
        "aliases": {
            alias: {
                "condition": condition,
                "provider": comparison.get("provider"),
                "model": comparison.get("model"),
            }
            for alias, condition in mapping.items()
        },
        "source_revision": gate["source_revision"],
        "source_manifest_sha256": gate["source_manifest_sha256"],
        "graph_fingerprint": gate["graph_fingerprint"],
        "isolation_gate": gate,
        "warning": "Steward-only. Do not provide this file or its contents to reviewers before both reviews are submitted and validated.",
    }
    return packet, key


def build_review_template(packet: Mapping[str, Any], reviewer_id: str = "") -> dict[str, Any]:
    cases = packet.get("cases")
    if not isinstance(cases, Mapping) or set(cases) != {"A", "B"}:
        raise BlindReviewError("packet_cases_invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "pair_id": packet.get("pair_id"),
        "reviewer_id": reviewer_id,
        "reviewed_at": "",
        "cases": [_review_case_template(cases[alias]) for alias in ("A", "B")],
        "pair_preference": "unable_to_judge",
        "pair_rationale": "",
        "blindness_attestation": {
            "has_not_seen_other_reviewer_labels": False,
            "has_not_seen_provider_or_model_identity": False,
            "has_not_seen_condition_mapping": False,
        },
    }


def _parse_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_review_record(record: Any, packet: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(record, Mapping):
        return {"valid": False, "errors": ["review_not_object"]}
    allowed_record_fields = {
        "schema_version", "pair_id", "reviewer_id", "reviewed_at", "cases",
        "pair_preference", "pair_rationale", "blindness_attestation",
    }
    if set(record) - allowed_record_fields:
        errors.append("unexpected_review_fields")
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version_invalid")
    if record.get("pair_id") != packet.get("pair_id"):
        errors.append("pair_id_mismatch")
    reviewer_id = record.get("reviewer_id")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip() or len(reviewer_id) > 120:
        errors.append("reviewer_id_invalid")
    if not _parse_datetime(record.get("reviewed_at")):
        errors.append("reviewed_at_invalid_timezone_required")

    packet_cases = packet.get("cases", {})
    expected_aliases = {"A", "B"}
    review_cases = record.get("cases")
    if not isinstance(review_cases, list) or len(review_cases) != 2:
        errors.append("review_cases_invalid")
        review_cases = []
    seen_aliases: set[str] = set()
    for case_review in review_cases:
        if not isinstance(case_review, Mapping):
            errors.append("case_review_invalid")
            continue
        allowed_case_fields = {
            "case_alias", "overall_outcome", "localization", "causal_explanation",
            "claim_level_support", "evidence_integrity", "uncertainty", "actionability",
            "claim_reviews", "rationale",
        }
        if set(case_review) - allowed_case_fields:
            errors.append("case_review_unexpected_fields")
        alias = case_review.get("case_alias")
        if alias not in expected_aliases or alias in seen_aliases:
            errors.append("case_alias_invalid_or_duplicate")
            continue
        seen_aliases.add(alias)
        packet_case = packet_cases.get(alias, {}) if isinstance(packet_cases, Mapping) else {}
        for field_name, allowed in (
            ("overall_outcome", REVIEW_OUTCOMES),
            ("localization", LOCALIZATION),
            ("causal_explanation", CAUSAL_EXPLANATION),
            ("claim_level_support", CLAIM_SUPPORT),
            ("evidence_integrity", EVIDENCE_INTEGRITY),
            ("uncertainty", UNCERTAINTY),
            ("actionability", ACTIONABILITY),
        ):
            if case_review.get(field_name) not in allowed:
                errors.append(f"{alias}_{field_name}_invalid")
        rationale = case_review.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 5000:
            errors.append(f"{alias}_rationale_invalid")

        expected_claims = {
            item.get("claim_id")
            for item in packet_case.get("claim_index", [])
            if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)
        }
        review_claims = case_review.get("claim_reviews")
        if not isinstance(review_claims, list):
            errors.append(f"{alias}_claim_reviews_invalid")
            review_claims = []
        seen_claims: set[str] = set()
        known_evidence = {
            item.get("evidence_id")
            for item in packet_case.get("evidence_index", [])
            if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)
        }
        for claim_review in review_claims:
            if not isinstance(claim_review, Mapping):
                errors.append(f"{alias}_claim_review_invalid")
                continue
            allowed_claim_fields = {
                "claim_id", "outcome", "verification_level", "supporting_evidence_ids",
                "counterevidence_ids", "rationale",
            }
            if set(claim_review) - allowed_claim_fields:
                errors.append(f"{alias}_claim_review_unexpected_fields")
            claim_id = claim_review.get("claim_id")
            if not isinstance(claim_id, str) or claim_id not in expected_claims:
                errors.append(f"{alias}_claim_id_unknown")
                continue
            if claim_id in seen_claims:
                errors.append(f"{alias}_claim_id_duplicate")
            seen_claims.add(claim_id)
            if claim_review.get("outcome") not in CLAIM_OUTCOMES:
                errors.append(f"{alias}_claim_outcome_invalid")
            verification_level = claim_review.get("verification_level")
            if verification_level not in {
                "textual_witness", "static_review", "test_reproduction",
                "independent_expert_review", "unverified",
            }:
                errors.append(f"{alias}_claim_verification_level_invalid")
            claim_type = next(
                (
                    item.get("claim_type")
                    for item in packet_case.get("claim_index", [])
                    if isinstance(item, Mapping) and item.get("claim_id") == claim_id
                ),
                None,
            )
            if (
                claim_review.get("outcome") == "entailed"
                and claim_type in {"causal_hypothesis", "runtime_claim"}
                and verification_level not in {"test_reproduction", "independent_expert_review"}
            ):
                errors.append(f"{alias}_causal_or_runtime_entailment_requires_reproduction_or_expert_review")
            for field_name in ("supporting_evidence_ids", "counterevidence_ids"):
                values = claim_review.get(field_name)
                if not isinstance(values, list) or len(values) > 100 or any(
                    not isinstance(value, str) or value not in known_evidence for value in values
                ):
                    errors.append(f"{alias}_{field_name}_invalid")
            if claim_review.get("outcome") == "contradicted" and not claim_review.get("counterevidence_ids"):
                errors.append(f"{alias}_contradicted_requires_counterevidence")
            claim_rationale = claim_review.get("rationale")
            if not isinstance(claim_rationale, str) or not claim_rationale.strip() or len(claim_rationale) > 4000:
                errors.append(f"{alias}_claim_rationale_invalid")
        if seen_claims != expected_claims:
            errors.append(f"{alias}_claim_review_set_incomplete")

    if seen_aliases != expected_aliases:
        errors.append("review_alias_set_incomplete")
    if record.get("pair_preference") not in PAIR_PREFERENCE:
        errors.append("pair_preference_invalid")
    pair_rationale = record.get("pair_rationale")
    if not isinstance(pair_rationale, str) or not pair_rationale.strip() or len(pair_rationale) > 5000:
        errors.append("pair_rationale_invalid")
    attestation = record.get("blindness_attestation")
    if not isinstance(attestation, Mapping):
        errors.append("blindness_attestation_missing")
    else:
        allowed_attestation_fields = {
            "has_not_seen_other_reviewer_labels",
            "has_not_seen_provider_or_model_identity",
            "has_not_seen_condition_mapping",
        }
        if set(attestation) - allowed_attestation_fields:
            errors.append("blindness_attestation_unexpected_fields")
        for field_name in (
            "has_not_seen_other_reviewer_labels",
            "has_not_seen_provider_or_model_identity",
            "has_not_seen_condition_mapping",
        ):
            if attestation.get(field_name) is not True:
                errors.append(f"blindness_attestation_not_true:{field_name}")
    return {"valid": not errors, "errors": sorted(set(errors))}


def _kappa(first: Sequence[str], second: Sequence[str], labels: Sequence[str]) -> dict[str, Any]:
    if len(first) != len(second) or not first:
        return {"count": 0, "observed_agreement": None, "expected_agreement": None, "cohens_kappa": None, "status": "no_common_items"}
    matrix = {left: {right: 0 for right in labels} for left in labels}
    count_a: Counter[str] = Counter()
    count_b: Counter[str] = Counter()
    agreement = 0
    for left, right in zip(first, second):
        if left not in matrix or right not in matrix:
            raise BlindReviewError("agreement_label_invalid")
        matrix[left][right] += 1
        count_a[left] += 1
        count_b[right] += 1
        agreement += int(left == right)
    total = len(first)
    observed = agreement / total
    expected = sum((count_a[label] / total) * (count_b[label] / total) for label in labels)
    kappa = None if abs(1.0 - expected) < 1e-12 else (observed - expected) / (1.0 - expected)
    return {
        "count": total,
        "observed_agreement": round(observed, 6),
        "expected_agreement": round(expected, 6),
        "cohens_kappa": None if kappa is None else round(kappa, 6),
        "status": "undefined_no_expected_disagreement" if kappa is None else "computed",
        "confusion_matrix": matrix,
    }


def compare_reviews(
    packet: Mapping[str, Any],
    reviewer_a: Mapping[str, Any],
    reviewer_b: Mapping[str, Any],
) -> dict[str, Any]:
    first_validation = validate_review_record(reviewer_a, packet)
    second_validation = validate_review_record(reviewer_b, packet)
    if not first_validation["valid"] or not second_validation["valid"]:
        raise BlindReviewError("review_validation_failed")
    if reviewer_a.get("reviewer_id") == reviewer_b.get("reviewer_id"):
        raise BlindReviewError("reviewer_ids_must_differ")

    first_cases = {item["case_alias"]: item for item in reviewer_a["cases"]}
    second_cases = {item["case_alias"]: item for item in reviewer_b["cases"]}
    case_outcomes = {}
    for alias in ("A", "B"):
        left = first_cases[alias]["overall_outcome"]
        right = second_cases[alias]["overall_outcome"]
        case_outcomes[alias] = {"reviewer_a": left, "reviewer_b": right, "agreement": left == right}

    first_claims: dict[tuple[str, str], str] = {}
    second_claims: dict[tuple[str, str], str] = {}
    disagreements = []
    for alias in ("A", "B"):
        for item in first_cases[alias]["claim_reviews"]:
            first_claims[(alias, item["claim_id"])] = item["outcome"]
        for item in second_cases[alias]["claim_reviews"]:
            second_claims[(alias, item["claim_id"])] = item["outcome"]
    keys = sorted(first_claims)
    for key in keys:
        left = first_claims[key]
        right = second_claims[key]
        if left != right:
            disagreements.append({"case_alias": key[0], "claim_id": key[1], "reviewer_a": left, "reviewer_b": right})

    claim_agreement = _kappa(
        [first_claims[key] for key in keys],
        [second_claims[key] for key in keys],
        KAPPA_LABELS,
    )
    overall_case_agreement = sum(item["agreement"] for item in case_outcomes.values()) / 2
    preference_agreement = reviewer_a.get("pair_preference") == reviewer_b.get("pair_preference")
    return {
        "schema_version": "ae32c/blind-pair-review-agreement/v1",
        "pair_id": packet.get("pair_id"),
        "valid": True,
        "reviewer_ids": [reviewer_a.get("reviewer_id"), reviewer_b.get("reviewer_id")],
        "reviewer_form_sha256": {
            "reviewer_a": _sha256_json(reviewer_a),
            "reviewer_b": _sha256_json(reviewer_b),
        },
        "case_outcomes": case_outcomes,
        "case_outcome_raw_agreement": round(overall_case_agreement, 6),
        "claim_level_agreement": claim_agreement,
        "pair_preference": {
            "reviewer_a": reviewer_a.get("pair_preference"),
            "reviewer_b": reviewer_b.get("pair_preference"),
            "agreement": preference_agreement,
        },
        "claim_disagreements": disagreements,
        "final_adjudication": "pending_human_adjudicator",
        "primary_benchmark_eligible": False,
        "interpretation": "Agreement statistics are descriptive. Two reviews do not automatically establish gold truth; disagreements and all causal claims require human adjudication or deterministic reproduction where feasible.",
    }


def unblind_pair(
    key: Mapping[str, Any],
    agreement: Mapping[str, Any],
) -> dict[str, Any]:
    if agreement.get("valid") is not True:
        raise BlindReviewError("agreement_record_not_valid")
    if key.get("pair_id") != agreement.get("pair_id"):
        raise BlindReviewError("unblinding_pair_id_mismatch")
    aliases = key.get("aliases")
    if not isinstance(aliases, Mapping) or set(aliases) != {"A", "B"}:
        raise BlindReviewError("unblinding_key_invalid")
    return {
        "schema_version": "ae32c/blind-pair-unblinding-result/v1",
        "pair_id": key.get("pair_id"),
        "aliases": aliases,
        "reviewer_agreement": {
            "reviewer_ids": agreement.get("reviewer_ids"),
            "reviewer_form_sha256": agreement.get("reviewer_form_sha256"),
            "case_outcome_raw_agreement": agreement.get("case_outcome_raw_agreement"),
            "claim_level_agreement": agreement.get("claim_level_agreement"),
            "pair_preference": agreement.get("pair_preference"),
            "claim_disagreements": agreement.get("claim_disagreements"),
        },
        "final_adjudication": "pending_human_adjudicator",
        "primary_benchmark_eligible": False,
        "warning": "Unblinding identifies conditions only. It does not convert reviewer agreement into ground truth or establish causal benefit.",
    }


def write_json(value: Any, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def prepare_from_files(
    comparison_path: str | Path,
    control_report_path: str | Path,
    graph_report_path: str | Path,
    output_dir: str | Path,
    *,
    pair_id: str | None = None,
) -> dict[str, Any]:
    comparison = _read_json(comparison_path)
    control = _read_json(control_report_path)
    graph = _read_json(graph_report_path)
    packet, key = prepare_blind_pair(comparison, control, graph, pair_id=pair_id)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise BlindReviewError("output_directory_not_empty")
    output.mkdir(parents=True, exist_ok=True)
    for reviewer in ("reviewer-1", "reviewer-2"):
        folder = output / reviewer
        folder.mkdir(parents=True, exist_ok=True)
        write_json(packet, folder / "packet.json")
        write_json(build_review_template(packet, reviewer), folder / "review.template.json")
        (folder / "README.md").write_text(
            "# Independent blinded review\n\n"
            "Review both anonymized cases independently. Do not share labels or rationales with the other reviewer. "
            "Do not request or inspect the steward-only unblinding key. Inspect the frozen source revision and cited lines. "
            "Complete `review.template.json`, set a timezone-aware ISO 8601 `reviewed_at`, and truthfully attest to blinding.\n",
            encoding="utf-8",
        )
    steward = output / "steward"
    steward.mkdir(parents=True, exist_ok=True)
    write_json(key, steward / "unblinding-key.json")
    (steward / "README.md").write_text(
        "# Steward-only files\\n\\n"
        "Do not share this directory with either reviewer. Preserve the unblinding key until both independent "
        "review forms have been completed and validated. Agreement statistics are descriptive only; a separate "
        "human adjudicator must decide any final label.\\n",
        encoding="utf-8",
    )
    source_manifest = {
        "schema_version": "ae32c/blind-pair-input-manifest/v1",
        "pair_id": packet["pair_id"],
        "inputs": {
            "comparison": {"sha256": _sha256_bytes(Path(comparison_path).read_bytes())},
            "control_report": {"sha256": _sha256_bytes(Path(control_report_path).read_bytes())},
            "graph_report": {"sha256": _sha256_bytes(Path(graph_report_path).read_bytes())},
        },
        "reviewer_packet_sha256": _sha256_json(packet),
        "isolation_gate": key["isolation_gate"],
    }
    write_json(source_manifest, steward / "input-manifest.json")
    return {
        "pair_id": packet["pair_id"],
        "output_dir": str(output),
        "reviewer_packet_sha256": source_manifest["reviewer_packet_sha256"],
        "isolation_gate": key["isolation_gate"],
    }

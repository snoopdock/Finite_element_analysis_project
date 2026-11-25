"""Versioned rule coverage contracts and source-bound finding ledger for AE-32C.

The registry is deliberately conservative: absence claims remain ABSTAIN until a
rule-specific closed-world contract is explicitly authored and independently
satisfied. Evidence references are bound to one source and graph snapshot.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

RULE_REGISTRY_SCHEMA = "ae32c/rule-coverage-registry/v1"
FINDING_LEDGER_SCHEMA = "ae32c/finding-ledger/v1"
RULE_CONTRACT_VERSION = "1.0.0"


class RuleContractError(ValueError):
    """A rule contract or finding binding is invalid."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


# These identifiers are the AE-32A rule identifiers emitted by _build_findings.
# Dynamic component suffixes are explicit patterns, not implicit unknown rules.
_RULES: tuple[dict[str, Any], ...] = (
    {"rule_id": "AE32A-LLM-ISOLATION-*", "claim_polarity": "mixed",
     "required_evidence_kinds": ["llm_transport_call"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-NO-TOOL-LOOP", "claim_polarity": "absence",
     "required_evidence_kinds": ["model_tool_protocol_indicator", "tool_dispatch_indicator"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-NO-GENERAL-AE-WORKFLOW", "claim_polarity": "absence",
     "required_evidence_kinds": ["workflow_command"],
     "required_coverage": ["workflow_static_scan", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-FIXED-DIAGNOSTIC-CONTEXT", "claim_polarity": "mixed",
     "required_evidence_kinds": ["fixed_context_allowlist"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-GRAPH-SERVICE-UNUSED", "claim_polarity": "absence",
     "required_evidence_kinds": ["graph_import"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-GRAPH-NOT-IN-LLM-PATH", "claim_polarity": "absence",
     "required_evidence_kinds": ["graph_import"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-AE28-EXTERNAL-MODEL-INPUT", "claim_polarity": "positive",
     "required_evidence_kinds": ["external_model_response_intake"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-AE29-VERIFICATION-RECEIPT-ONLY", "claim_polarity": "mixed",
     "required_evidence_kinds": ["verification_gate_api"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-SYNTHETIC-EVAL-ONLY", "claim_polarity": "mixed",
     "required_evidence_kinds": ["evaluation_indicator"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-NO-TEST-REFERENCE-*", "claim_polarity": "absence",
     "required_evidence_kinds": ["component_inventory"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-PROVIDER-PATH-DUPLICATION", "claim_polarity": "positive",
     "required_evidence_kinds": ["llm_transport_call"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-DECISION-MEMORY-BRIDGE-NOT-OBSERVED", "claim_polarity": "absence",
     "required_evidence_kinds": ["decision_memory_indicator"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-INCOMPLETE-PYTHON-SCAN", "claim_polarity": "positive",
     "required_evidence_kinds": ["python_syntax_error"],
     "required_coverage": ["python_ast", "source_manifest"], "closed_world": None},
    {"rule_id": "AE32A-SCOPE-EXCLUSIONS", "claim_polarity": "positive",
     "required_evidence_kinds": ["scope_exclusion"],
     "required_coverage": ["source_manifest"], "closed_world": None},
)


def _matches(pattern: str, rule_id: str) -> bool:
    if pattern.endswith("*"):
        return rule_id.startswith(pattern[:-1])
    return pattern == rule_id


def rule_registry() -> dict[str, Any]:
    rules = [dict(item, version=RULE_CONTRACT_VERSION) for item in _RULES]
    payload = {"schema": RULE_REGISTRY_SCHEMA, "rules": rules}
    return {**payload, "registry_sha256": digest(payload)}


def resolve_rule(rule_id: str, registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    selected = registry or rule_registry()
    matches = [item for item in selected.get("rules", []) if _matches(str(item.get("rule_id", "")), rule_id)]
    if len(matches) != 1:
        raise RuleContractError("unknown_or_ambiguous_rule:" + rule_id)
    return dict(matches[0])


def _coverage_by_path(graph_manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    coverage = graph_manifest.get("coverage", {})
    return {str(item.get("path")): item for item in coverage.get("source_units", [])
            if isinstance(item, Mapping) and isinstance(item.get("path"), str)}


def build_finding_ledger(
    findings: list[dict[str, Any]],
    source_manifest: Mapping[str, Any],
    graph_manifest: Mapping[str, Any],
    graph: Mapping[str, Any],
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind findings to exact rule, source, graph and evidence identities.

    A positive claim can be SUPPORTED only when its cited source files are
    represented and digest-matched. Absence claims remain ABSTAIN because this
    registry currently defines no proved query-specific closed-world contract.
    """
    selected_registry = dict(registry or rule_registry())
    registry_payload = {key: value for key, value in selected_registry.items() if key != "registry_sha256"}
    if selected_registry.get("registry_sha256") != digest(registry_payload):
        raise RuleContractError("rule_registry_digest_mismatch")

    source_id = source_manifest.get("source_snapshot_id")
    graph_id = graph_manifest.get("graph_snapshot_id")
    if not source_id or not graph_id:
        raise RuleContractError("source_or_graph_snapshot_identity_missing")
    inventory = {
        str(item.get("path")): item
        for item in source_manifest.get("source_inventory", {}).get("entries", [])
        if isinstance(item, Mapping) and isinstance(item.get("path"), str)
    }
    coverage = _coverage_by_path(graph_manifest)
    node_ids = {str(item.get("id")) for item in graph.get("nodes", []) if isinstance(item, Mapping)}
    bound: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            raise RuleContractError("finding_record_invalid")
        rule_id = str(finding.get("id", ""))
        contract = resolve_rule(rule_id, selected_registry)
        evidence_refs: list[dict[str, Any]] = []
        evidence_issues: list[str] = []
        raw_evidence = finding.get("evidence", [])
        if not isinstance(raw_evidence, list):
            raise RuleContractError("finding_evidence_invalid:" + rule_id)
        for item in raw_evidence:
            if not isinstance(item, Mapping):
                evidence_issues.append("evidence_record_invalid")
                continue
            path = item.get("path")
            if not isinstance(path, str) or path not in inventory:
                evidence_issues.append("evidence_source_not_in_snapshot")
                continue
            unit = coverage.get(path)
            source_entry = inventory[path]
            expected_hash = source_entry.get("content_sha256")
            if not unit or unit.get("status") != "represented":
                evidence_issues.append("evidence_source_not_represented:" + path)
                continue
            if not expected_hash or unit.get("source_content_sha256") != expected_hash:
                evidence_issues.append("evidence_source_digest_mismatch:" + path)
                continue
            node_id = "file:" + path
            if node_id not in node_ids:
                evidence_issues.append("evidence_graph_node_missing:" + path)
                continue
            line = item.get("line")
            if line is not None and (not isinstance(line, int) or line < 1):
                evidence_issues.append("evidence_line_invalid:" + path)
                continue
            evidence_refs.append({
                "source_path": path,
                "source_content_sha256": expected_hash,
                "graph_node_id": node_id,
                "line": line,
                "kind": str(item.get("kind", "unspecified")),
                "detail_sha256": digest(str(item.get("detail", ""))),
            })
        required_scope_complete = (
            graph_manifest.get("coverage", {}).get("status") == "COMPLETE_WITH_DECLARED_EXCLUSIONS"
            and graph_manifest.get("coverage", {}).get("unaccounted_count") == 0
        )
        observed_kinds = {item["kind"] for item in evidence_refs}
        required_kinds = set(contract.get("required_evidence_kinds", []))
        missing_kinds = sorted(required_kinds - observed_kinds)
        if missing_kinds:
            evidence_issues.extend("required_evidence_kind_missing:" + kind for kind in missing_kinds)
        extractor_coverage = graph_manifest.get("coverage", {}).get("extractor_coverage", {})
        coverage_issues: list[str] = []
        for requirement in contract.get("required_coverage", []):
            if requirement == "source_manifest" and not required_scope_complete:
                coverage_issues.append("source_manifest_incomplete")
            elif requirement == "python_ast":
                ast_coverage = extractor_coverage.get("python_ast", {})
                if ast_coverage.get("candidate_count") != ast_coverage.get("parsed_count") or ast_coverage.get("failed_count", 0):
                    coverage_issues.append("python_ast_incomplete")
            elif requirement == "workflow_static_scan":
                if extractor_coverage.get("workflow_static_scan", {}).get("status") != "complete":
                    coverage_issues.append("workflow_static_scan_incomplete")
        if contract["claim_polarity"] in {"absence", "mixed"} and contract.get("closed_world") is None:
            claim_status = "ABSTAIN"
            reason = (
                "closed_world_contract_not_defined"
                if contract["claim_polarity"] == "absence"
                else "mixed_claim_requires_closed_world_contract"
            )
        elif evidence_issues or not evidence_refs:
            claim_status = "INSUFFICIENT_EVIDENCE"
            reason = "evidence_binding_failed_or_missing"
        elif coverage_issues:
            claim_status = "ABSTAIN"
            reason = "required_source_coverage_incomplete"
        else:
            claim_status = "EVIDENCE_BOUND"
            reason = "source_and_graph_evidence_bound"
        finding_payload = {
            "rule_id": rule_id,
            "rule_version": contract["version"],
            "source_snapshot_id": source_id,
            "graph_snapshot_id": graph_id,
            "severity": finding.get("severity"),
            "title": finding.get("title"),
            "statement": finding.get("statement"),
            "limitation": finding.get("limitation"),
            "evidence": evidence_refs,
            "claim_status": claim_status,
            "status_reason": reason,
        }
        bound.append({
            "finding_id": digest(finding_payload),
            **finding_payload,
            "evidence_issues": sorted(set(evidence_issues)),
            "coverage_issues": sorted(set(coverage_issues)),
            "rule_contract": contract,
        })
    bound.sort(key=lambda item: (item["rule_id"], item["finding_id"]))
    ledger_payload = {
        "schema": FINDING_LEDGER_SCHEMA,
        "source_snapshot_id": source_id,
        "graph_snapshot_id": graph_id,
        "rule_registry_sha256": selected_registry["registry_sha256"],
        "finding_count": len(bound),
        "findings": bound,
        "authority": {
            "ledger_is_derived": True,
            "ledger_is_canonical_repository_authority": False,
            "absence_claims_authorized": False,
            "production_approval": False,
        },
    }
    return {**ledger_payload, "ledger_sha256": digest(ledger_payload)}


def verify_finding_ledger(ledger: Mapping[str, Any]) -> None:
    payload = {key: value for key, value in ledger.items() if key != "ledger_sha256"}
    if ledger.get("schema") != FINDING_LEDGER_SCHEMA:
        raise RuleContractError("finding_ledger_schema_invalid")
    if ledger.get("ledger_sha256") != digest(payload):
        raise RuleContractError("finding_ledger_digest_mismatch")
    if ledger.get("finding_count") != len(ledger.get("findings", [])):
        raise RuleContractError("finding_ledger_count_mismatch")
    for finding in ledger.get("findings", []):
        if finding.get("source_snapshot_id") != ledger.get("source_snapshot_id"):
            raise RuleContractError("finding_source_snapshot_mismatch")
        if finding.get("graph_snapshot_id") != ledger.get("graph_snapshot_id"):
            raise RuleContractError("finding_graph_snapshot_mismatch")
        expected = digest({key: finding[key] for key in (
            "rule_id", "rule_version", "source_snapshot_id", "graph_snapshot_id",
            "severity", "title", "statement", "limitation", "evidence",
            "claim_status", "status_reason",
        )})
        if finding.get("finding_id") != expected:
            raise RuleContractError("finding_identity_mismatch")
        if finding.get("claim_status") == "EVIDENCE_BOUND" and not finding.get("evidence"):
            raise RuleContractError("evidence_bound_finding_without_evidence")
        if finding.get("rule_version") != finding.get("rule_contract", {}).get("version"):
            raise RuleContractError("finding_rule_version_mismatch")
        if finding.get("rule_id") != finding.get("rule_contract", {}).get("rule_id") and not _matches(str(finding.get("rule_contract", {}).get("rule_id", "")), str(finding.get("rule_id", ""))):
            raise RuleContractError("finding_rule_contract_mismatch")
        polarity = finding.get("rule_contract", {}).get("claim_polarity")
        if polarity in {"absence", "mixed"} and finding.get("rule_contract", {}).get("closed_world") is None:
            if finding.get("claim_status") != "ABSTAIN":
                raise RuleContractError("open_world_claim_not_abstained")

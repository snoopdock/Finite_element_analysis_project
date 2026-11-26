"""M7.5.16 rule-specific semantic qualification of typed evidence observations.

Qualification validates only narrow, declared propositions. It never upgrades
an observation into global proposition truth or audit-decision authority.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .assurance import AssuranceClaim
from .coverage import EpistemicCoverageManifest
from .rule_coverage import RuleCoveragePlan, verify_rule_derived_manifest

SCHEMA = "ae32c/semantic-evidence-qualification/v1"
CONTRACT_SCHEMA = "ae32c/semantic-evidence-contract-registry/v1"


class SemanticQualificationError(ValueError):
    """A qualification request, contract, or replay is invalid."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


# These contracts make deliberately narrow claims. In particular, an import
# cannot establish that a service is unused or absent from an LLM execution path.
_CONTRACTS = {
    "AE32A-GRAPH-SERVICE-UNUSED": {
        "version": "1.0.0", "evidence_kind": "graph_import",
        "proposition": "A graph-library import was observed in the pinned source.",
        "qualification": "INSUFFICIENT",
        "reason": "An import establishes neither actual service use nor non-use.",
        "limitation": "No call-graph, runtime, dependency-injection, or reachability proof.",
    },
    "AE32A-GRAPH-NOT-IN-LLM-PATH": {
        "version": "1.0.0", "evidence_kind": "graph_import",
        "proposition": "A graph-library import was observed in the pinned source.",
        "qualification": "INSUFFICIENT",
        "reason": "An import cannot establish whether graph operations are on an LLM path.",
        "limitation": "No execution-path or data-flow proof.",
    },
    "AE32A-INCOMPLETE-PYTHON-SCAN": {
        "version": "1.0.0", "evidence_kind": "python_syntax_error",
        "proposition": "The pinned Python source fails the registered Python AST parse.",
        "qualification": "SUPPORTED",
        "reason": "The exact source bytes independently reproduce an AST SyntaxError.",
        "limitation": "This supports a parse-coverage limitation only, not broader code defect claims.",
    },
    "AE32A-SCOPE-EXCLUSIONS": {
        "version": "1.0.0", "evidence_kind": "scope_exclusion",
        "proposition": "The verified source inventory declares this path excluded.",
        "qualification": "INSUFFICIENT",
        "reason": "The observation carries a declared reason, but this validator does not independently replay the upstream extractor inventory.",
        "limitation": "No independent verification of exclusion selection, rationale, or scope completeness."
    },
}


def semantic_evidence_contract_registry() -> dict[str, Any]:
    contracts = {key: dict(value) for key, value in sorted(_CONTRACTS.items())}
    payload = {"schema": CONTRACT_SCHEMA, "contracts": contracts}
    return {**payload, "registry_sha256": _digest(payload)}


def _source_entries(source_manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    inventory = source_manifest.get("source_inventory")
    if not isinstance(inventory, Mapping) or not isinstance(inventory.get("entries"), list):
        raise SemanticQualificationError("source_inventory_missing_or_invalid")
    inventory_payload = list(inventory["entries"])
    if inventory.get("entry_count") != len(inventory_payload):
        raise SemanticQualificationError("source_inventory_entry_count_mismatch")
    if inventory.get("sha256") != _digest(inventory_payload):
        raise SemanticQualificationError("source_inventory_digest_mismatch")
    manifest_payload = {k: v for k, v in source_manifest.items() if k != "manifest_sha256"}
    if source_manifest.get("manifest_sha256") != _digest(manifest_payload):
        raise SemanticQualificationError("source_manifest_digest_mismatch")
    entries: dict[str, Mapping[str, Any]] = {}
    for item in inventory["entries"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            raise SemanticQualificationError("source_inventory_entry_invalid")
        path = item["path"]
        if path in entries:
            raise SemanticQualificationError("duplicate_source_inventory_path:" + path)
        digest = item.get("content_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SemanticQualificationError("source_inventory_digest_invalid:" + path)
        entries[path] = item
    return entries


def _read_source(root: Path, path: str, entries: Mapping[str, Mapping[str, Any]]) -> bytes:
    if path not in entries:
        raise SemanticQualificationError("observation_source_not_in_manifest:" + path)
    candidate = root / path
    # Reject symlink traversal and paths that escape the pinned repository root.
    if candidate.is_symlink():
        raise SemanticQualificationError("source_symlink_rejected:" + path)
    resolved = candidate.resolve(strict=True)
    if root not in resolved.parents and resolved != root:
        raise SemanticQualificationError("source_path_escape:" + path)
    if not resolved.is_file():
        raise SemanticQualificationError("source_not_regular_file:" + path)
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entries[path]["content_sha256"]:
        raise SemanticQualificationError("source_content_digest_mismatch:" + path)
    return raw


def _verify_observation(observation: Mapping[str, Any], *, source_snapshot_id: str,
                        entries: Mapping[str, Mapping[str, Any]], root: Path) -> bytes:
    if observation.get("schema") != "ae32c/typed-evidence-observation/v1":
        raise SemanticQualificationError("observation_schema_invalid")
    payload = {k: v for k, v in observation.items() if k != "evidence_observation_id"}
    if observation.get("evidence_observation_id") != _digest(payload):
        raise SemanticQualificationError("observation_identity_mismatch")
    if observation.get("source_snapshot_id") != source_snapshot_id:
        raise SemanticQualificationError("observation_snapshot_mismatch")
    if observation.get("status") != "STRUCTURALLY_OBSERVED":
        raise SemanticQualificationError("observation_not_structurally_observed")
    if observation.get("semantic_acceptance") != "NOT_ESTABLISHED":
        raise SemanticQualificationError("observation_semantic_state_invalid")
    path = observation.get("source_path")
    if not isinstance(path, str) or not path:
        raise SemanticQualificationError("observation_source_path_missing")
    raw = _read_source(root, path, entries)
    if observation.get("source_content_sha256") != entries[path]["content_sha256"]:
        raise SemanticQualificationError("observation_source_digest_mismatch")
    line = observation.get("source_line")
    line_digest = observation.get("source_line_sha256")
    if line is not None:
        lines = raw.splitlines()
        if isinstance(line, bool) or not isinstance(line, int) or line < 1 or line > len(lines):
            raise SemanticQualificationError("observation_line_outside_source")
        if hashlib.sha256(lines[line - 1]).hexdigest() != line_digest:
            raise SemanticQualificationError("observation_line_digest_mismatch")
    elif line_digest is not None:
        raise SemanticQualificationError("line_digest_without_line")
    return raw


def _verify_observation_semantics(observation: Mapping[str, Any], raw: bytes) -> None:
    kind = observation.get("evidence_kind")
    value = observation.get("structural_value")
    if not isinstance(value, Mapping):
        raise SemanticQualificationError("observation_structural_value_invalid")
    if kind == "graph_import":
        try:
            tree = ast.parse(raw, filename=str(observation.get("source_path")))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise SemanticQualificationError("graph_import_source_does_not_parse") from exc
        target_line = observation.get("source_line")
        module = value.get("module")
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if node.lineno == target_line and alias.name == module:
                        matches.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.lineno == target_line and node.module == module:
                    matches.append(node.module)
        if len(matches) != 1:
            raise SemanticQualificationError("graph_import_ast_replay_mismatch")
    elif kind == "python_syntax_error":
        try:
            ast.parse(raw, filename=str(observation.get("source_path")))
        except SyntaxError as exc:
            diagnostic = value.get("diagnostic_code")
            if diagnostic != "source_parse_failed":
                raise SemanticQualificationError("syntax_error_diagnostic_code_mismatch")
            if observation.get("source_line") is not None and exc.lineno != observation.get("source_line"):
                raise SemanticQualificationError("syntax_error_line_mismatch")
        except UnicodeDecodeError as exc:
            raise SemanticQualificationError("syntax_error_not_reproduced") from exc
        else:
            raise SemanticQualificationError("syntax_error_not_reproduced")
    elif kind == "scope_exclusion":
        if observation.get("observation_type") != "declared_scope_exclusion":
            raise SemanticQualificationError("scope_exclusion_observation_type_invalid")
        if not isinstance(value.get("reason"), str) or not value["reason"].strip():
            raise SemanticQualificationError("scope_exclusion_reason_missing")
    # Unsupported evidence kinds remain UNKNOWN. Source identity is checked by
    # the caller, but no semantic interpretation is attempted here.
    else:
        return


def _obligation_parts(obligation_id: str) -> tuple[str, str]:
    parts = obligation_id.split(":")
    if len(parts) < 4 or parts[0] != "rule" or parts[2] != "evidence":
        raise SemanticQualificationError("invalid_rule_obligation_id:" + obligation_id)
    return parts[1], ":".join(parts[3:])


def qualify_typed_evidence_observations(
    bundle: Mapping[str, Any], *, claim: AssuranceClaim, plan: RuleCoveragePlan,
    coverage_manifest: EpistemicCoverageManifest, source_manifest: Mapping[str, Any],
    repository_root: str | Path, defeaters: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Qualify each observed item against exact rule-specific contracts.

    A defeater is a source-bound counterclaim record. Its presence yields
    CONTESTED, but its truth is not asserted: validation remains explicitly
    NOT_ESTABLISHED until a dedicated defeater validator exists.
    """
    if not isinstance(bundle, Mapping):
        raise TypeError("bundle_must_be_an_object")
    payload = {k: v for k, v in bundle.items() if k != "bundle_sha256"}
    if bundle.get("bundle_sha256") != _digest(payload):
        raise SemanticQualificationError("observation_bundle_digest_mismatch")
    try:
        verify_rule_derived_manifest(claim, plan, coverage_manifest)
    except (ValueError, TypeError, KeyError) as exc:
        raise SemanticQualificationError("rule_coverage_plan_verification_failed:" + type(exc).__name__) from exc
    source_id = source_manifest.get("source_snapshot_id")
    if not isinstance(source_id, str) or source_id != bundle.get("source_snapshot_id"):
        raise SemanticQualificationError("source_snapshot_binding_mismatch")
    if plan.source_snapshot_id != source_id or bundle.get("plan_sha256") != plan.plan_sha256:
        raise SemanticQualificationError("rule_coverage_plan_binding_mismatch")
    entries = _source_entries(source_manifest)
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise SemanticQualificationError("repository_root_not_directory")
    if bundle.get("schema") != "ae32c/typed-evidence-observation-bundle/v1":
        raise SemanticQualificationError("observation_bundle_schema_invalid")
    observations = bundle.get("observations")
    if not isinstance(observations, list):
        raise SemanticQualificationError("observation_collection_invalid")
    if bundle.get("observation_count") != len(observations):
        raise SemanticQualificationError("observation_count_mismatch")
    contracts = semantic_evidence_contract_registry()["contracts"]
    by_id: dict[str, Mapping[str, Any]] = {}
    verified_raw: dict[str, bytes] = {}
    for item in observations:
        if not isinstance(item, Mapping):
            raise SemanticQualificationError("observation_record_invalid")
        identity = item.get("evidence_observation_id")
        if not isinstance(identity, str) or identity in by_id:
            raise SemanticQualificationError("duplicate_or_missing_observation_identity")
        verified_raw[identity] = _verify_observation(
            item, source_snapshot_id=source_id, entries=entries, root=root)
        by_id[identity] = item

    defeaters_by_observation: dict[str, list[dict[str, Any]]] = {}
    for item in defeaters:
        if not isinstance(item, Mapping):
            raise SemanticQualificationError("defeater_record_invalid")
        target = item.get("target_observation_id")
        observation = by_id.get(target)
        if observation is None:
            raise SemanticQualificationError("defeater_target_missing")
        path = item.get("source_path")
        if not isinstance(path, str) or path not in entries:
            raise SemanticQualificationError("defeater_source_not_in_manifest")
        if item.get("source_content_sha256") != entries[path]["content_sha256"]:
            raise SemanticQualificationError("defeater_source_digest_mismatch")
        raw = _read_source(root, path, entries)
        line = item.get("source_line")
        if line is not None:
            lines = raw.splitlines()
            if isinstance(line, bool) or not isinstance(line, int) or line < 1 or line > len(lines):
                raise SemanticQualificationError("defeater_line_outside_source")
            if item.get("source_line_sha256") != hashlib.sha256(lines[line - 1]).hexdigest():
                raise SemanticQualificationError("defeater_line_digest_mismatch")
        if item.get("source_snapshot_id") != source_id:
            raise SemanticQualificationError("defeater_snapshot_mismatch")
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise SemanticQualificationError("defeater_reason_missing")
        defeaters_by_observation.setdefault(target, []).append({
            "defeater_id": _digest(dict(item)),
            "reason": reason,
            "source_path": path,
            "source_content_sha256": entries[path]["content_sha256"],
            "validation": "NOT_ESTABLISHED",
        })

    results = []
    for identity, observation in sorted(by_id.items()):
        _verify_observation_semantics(observation, verified_raw[identity])
        obligation_ids = observation.get("rule_obligation_ids")
        if not isinstance(obligation_ids, list) or not obligation_ids:
            raise SemanticQualificationError("observation_obligation_binding_missing")
        if any(item not in plan.expected_obligation_ids for item in obligation_ids):
            raise SemanticQualificationError("observation_obligation_not_in_verified_plan")
        for obligation_id in obligation_ids:
            rule_id, evidence_kind = _obligation_parts(obligation_id)
            if observation.get("evidence_kind") != evidence_kind:
                raise SemanticQualificationError("observation_kind_obligation_mismatch")
            contract = contracts.get(rule_id)
            if contract is None or contract.get("evidence_kind") != evidence_kind:
                results.append({
                    "obligation_id": obligation_id, "observation_id": identity,
                    "rule_id": rule_id, "evidence_kind": evidence_kind,
                    "qualification": "UNKNOWN",
                    "reason": "no_matching_rule_specific_semantic_contract",
                    "defeaters": [],
                })
                continue
            attached = defeaters_by_observation.get(identity, [])
            outcome = "CONTESTED" if attached else contract["qualification"]
            results.append({
                "obligation_id": obligation_id, "observation_id": identity,
                "rule_id": rule_id, "evidence_kind": evidence_kind,
                "contract_version": contract["version"],
                "proposition": contract["proposition"],
                "qualification": outcome,
                "reason": ("source-bound counterclaim recorded; counterclaim validity not established"
                           if attached else contract["reason"]),
                "limitation": contract["limitation"],
                "defeaters": attached,
            })

    results.sort(key=lambda x: (x["obligation_id"], x["observation_id"]))
    summary = {status: sum(1 for x in results if x["qualification"] == status)
               for status in ("SUPPORTED", "INSUFFICIENT", "CONTESTED", "UNKNOWN")}
    result_payload = {
        "schema": SCHEMA, "source_snapshot_id": source_id,
        "observation_bundle_sha256": bundle["bundle_sha256"],
        "contract_registry_sha256": semantic_evidence_contract_registry()["registry_sha256"],
        "qualification_count": len(results), "qualifications": results,
        "summary": summary,
        "authority": {
            "rule_specific_narrow_support_established": summary["SUPPORTED"] > 0,
            "all_rule_obligations_satisfied": False,
            "proposition_truth_established": False,
            "epistemic_assertions_created": False,
            "coverage_dossier_mutated": False,
            "audit_decision_authority": False,
            "allow_deny_authority": False,
            "production_approval": False,
        },
    }
    return {**result_payload, "qualification_sha256": _digest(result_payload)}


def verify_semantic_evidence_qualification(
    qualification: Mapping[str, Any], bundle: Mapping[str, Any], *,
    claim: AssuranceClaim, plan: RuleCoveragePlan,
    coverage_manifest: EpistemicCoverageManifest,
    source_manifest: Mapping[str, Any], repository_root: str | Path,
    defeaters: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    if not isinstance(qualification, Mapping):
        raise TypeError("qualification_must_be_an_object")
    submitted = dict(qualification)
    digest = submitted.get("qualification_sha256")
    payload = {k: v for k, v in submitted.items() if k != "qualification_sha256"}
    if digest != _digest(payload):
        raise SemanticQualificationError("qualification_digest_mismatch")
    expected = qualify_typed_evidence_observations(
        bundle, claim=claim, plan=plan, coverage_manifest=coverage_manifest,
        source_manifest=source_manifest, repository_root=repository_root, defeaters=defeaters)
    if _canonical(expected) != _canonical(submitted):
        raise SemanticQualificationError("qualification_semantic_replay_mismatch")
    return {"qualification_sha256": digest, "semantic_replay": True,
            "qualification_count": expected["qualification_count"],
            "summary": dict(expected["summary"]) }

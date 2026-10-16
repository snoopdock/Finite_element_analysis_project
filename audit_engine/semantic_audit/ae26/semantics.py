"""AE-26: language-independent semantic vocabulary, normalization, and contract evolution.

AE-26 sits above AE-24 admission. It makes meaning, relationship semantics,
and contract change explicit without parsing or executing any programming
language. Occurrence identities remain evidence/provenance identities; the
semantic fingerprint deliberately collapses duplicate occurrences that carry
the same normalized semantic assertion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from audit_engine.semantic_audit.ae24.contracts import (
    admit, canonical, sha as _sha, Admission, ContractError,
)

SCHEMA = "ae26/semantic-vocabulary/v1"
DIFF_SCHEMA = "ae26/semantic-contract-diff/v1"

RELATION_SEMANTICS = {
    "PRODUCES": {"domain": "Component", "range": "Artifact", "inverse": "CONSUMES",
                 "character": "interface", "meaning_fields": ("format", "schema_id", "meaning_id")},
    "CONSUMES": {"domain": "Component", "range": "Artifact", "inverse": "PRODUCES",
                 "character": "interface", "meaning_fields": ("format", "schema_id", "meaning_id")},
    "PERFORMS": {"domain": "Component", "range": "Action", "inverse": None,
                 "character": "behavioral_observation", "meaning_fields": ()},
    "FORBIDS": {"domain": "Component", "range": "Action", "inverse": None,
                "character": "constraint", "meaning_fields": ()},
    "DEPENDS_ON": {"domain": "Component", "range": "Component", "inverse": None,
                   "character": "dependency", "meaning_fields": ()},
    "REQUIRES_CHECK": {"domain": "Component", "range": "Check", "inverse": None,
                       "character": "obligation", "meaning_fields": ()},
    "HAS_CHECK": {"domain": "Component", "range": "Check", "inverse": None,
                  "character": "verification_observation", "meaning_fields": ()},
}
CONCEPT_TYPES = frozenset({"Component", "Artifact", "Action", "Check", "Meaning", "Contract", "Policy"})
MAX_CHANGES = 12000


class SemanticModelError(ValueError):
    """Invalid semantic model, unsupported interpretation, or failed replay."""


@dataclass(frozen=True)
class SemanticEdgeView:
    occurrence_id: str
    subject: str
    predicate: str
    object: str
    origin: str
    source_id: str
    subject_kind: str
    object_kind: str
    meaning: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SemanticSnapshot:
    schema_version: str
    contract_sha256: str
    graph_fingerprint: str
    source_digests: tuple[tuple[str, str], ...]
    entities: tuple[tuple[str, str], ...]
    edges: tuple[SemanticEdgeView, ...]
    semantic_fingerprint: str


def _entity_map(contract: dict[str, Any]) -> dict[str, str]:
    return {row["id"]: row["kind"] for row in contract["entities"]}


def _meaning_tuple(assertion: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    attrs = assertion.get("attributes", {})
    return tuple((key, attrs[key]) for key in ("format", "schema_id", "meaning_id") if key in attrs)


def validate_vocabulary(contract: dict[str, Any], sources: Mapping[str, bytes]) -> Admission:
    """Admit AE-24 facts and validate the fixed semantic vocabulary."""
    admission = admit(contract, sources)
    kinds = _entity_map(contract)
    for assertion in contract["assertions"]:
        spec = RELATION_SEMANTICS.get(assertion["predicate"])
        if spec is None:
            raise SemanticModelError("Unsupported semantic predicate")
        if kinds[assertion["subject"]] != spec["domain"] or kinds[assertion["object"]] != spec["range"]:
            raise SemanticModelError(f"Semantic endpoint mismatch for {assertion['id']}")
        attrs = assertion.get("attributes", {})
        if set(attrs) & {"format", "schema_id", "meaning_id"} - set(spec["meaning_fields"]):
            raise SemanticModelError(f"Meaning field not applicable to {assertion['id']}")
    return admission


def snapshot(contract: dict[str, Any], sources: Mapping[str, bytes]) -> SemanticSnapshot:
    """Create a deterministic semantic projection from source-bound assertions."""
    admission = validate_vocabulary(contract, sources)
    kinds = _entity_map(contract)
    edges = tuple(sorted((
        SemanticEdgeView(
            occurrence_id=row["id"], subject=row["subject"], predicate=row["predicate"],
            object=row["object"], origin=row["origin"], source_id=row["source_id"],
            subject_kind=kinds[row["subject"]], object_kind=kinds[row["object"]],
            meaning=_meaning_tuple(row),
        )
        for row in contract["assertions"]
    ), key=lambda e: (e.subject, e.predicate, e.object, e.occurrence_id)))

    # Semantic identity intentionally excludes occurrence/source identity. This
    # means repeated observations of the same semantic relation do not alter
    # semantic state, while the evidence layer still retains every occurrence.
    semantic_edges = sorted({
        (e.subject, e.predicate, e.object, e.subject_kind, e.object_kind,
         e.origin, e.meaning)
        for e in edges
    }, key=repr)
    semantic_body = {
        "schema_version": SCHEMA,
        "entities": tuple(sorted(kinds.items())),
        "edges": semantic_edges,
        "policies": tuple(sorted(p["kind"] for p in contract.get("policies", []))),
        "coverage": tuple(sorted((c["component"], c["relation"], c["complete"])
                                 for c in contract.get("coverage", []))),
    }
    return SemanticSnapshot(
        schema_version=SCHEMA,
        contract_sha256=admission.contract_digest,
        graph_fingerprint=admission.graph_digest,
        source_digests=admission.source_digests,
        entities=tuple(sorted(kinds.items())),
        edges=edges,
        semantic_fingerprint=_sha(canonical(semantic_body)),
    )


def semantic_projection(s: SemanticSnapshot) -> dict[str, Any]:
    """Return a detached review representation; evidence identities are retained."""
    return {
        "schema_version": s.schema_version,
        "contract_sha256": s.contract_sha256,
        "graph_fingerprint": s.graph_fingerprint,
        "source_digests": [{"id": k, "sha256": v} for k, v in s.source_digests],
        "semantic_fingerprint": s.semantic_fingerprint,
        "entities": [{"id": k, "kind": v} for k, v in s.entities],
        "edges": [{
            "occurrence_id": e.occurrence_id, "subject": e.subject,
            "predicate": e.predicate, "object": e.object, "origin": e.origin,
            "source_id": e.source_id, "subject_kind": e.subject_kind,
            "object_kind": e.object_kind,
            "meaning": [{"key": k, "value": v} for k, v in e.meaning],
        } for e in s.edges],
    }


def verify_snapshot(contract: dict[str, Any], sources: Mapping[str, bytes],
                    claimed: SemanticSnapshot) -> bool:
    if not isinstance(claimed, SemanticSnapshot) or snapshot(contract, sources) != claimed:
        raise SemanticModelError("Semantic snapshot mismatch on exact replay")
    return True


def _semantic_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["subject"], row["predicate"], row["object"], row["origin"],
        tuple(sorted((k, v) for k, v in row.get("attributes", {}).items()
                     if k in {"format", "schema_id", "meaning_id", "producer", "producer_occurrence"})),
    )


def diff_contracts(before: dict[str, Any], before_sources: Mapping[str, bytes],
                   after: dict[str, Any], after_sources: Mapping[str, bytes]) -> dict[str, Any]:
    """Classify semantic changes between two independently admitted contracts."""
    old = snapshot(before, before_sources)
    new = snapshot(after, after_sources)
    old_rows = {_semantic_key(x) for x in before["assertions"]}
    new_rows = {_semantic_key(x) for x in after["assertions"]}
    changes = [_change("removed", key) for key in sorted(old_rows - new_rows, key=repr)]
    changes += [_change("added", key) for key in sorted(new_rows - old_rows, key=repr)]

    old_kinds, new_kinds = dict(old.entities), dict(new.entities)
    for entity in sorted(set(old_kinds) & set(new_kinds)):
        if old_kinds[entity] != new_kinds[entity]:
            changes.append({"change_type": "entity_semantic_kind_changed",
                             "entity_id": entity, "before": old_kinds[entity], "after": new_kinds[entity]})

    def interfaces(contract):
        return {
            (r["subject"], r["predicate"], r["object"]): r.get("attributes", {})
            for r in contract["assertions"] if r["predicate"] in {"PRODUCES", "CONSUMES"}
        }

    old_m, new_m = interfaces(before), interfaces(after)
    for key in sorted(set(old_m) & set(new_m)):
        old_v = {k: old_m[key].get(k) for k in ("format", "schema_id", "meaning_id")}
        new_v = {k: new_m[key].get(k) for k in ("format", "schema_id", "meaning_id")}
        if old_v != new_v:
            changes.append({"change_type": "interface_meaning_changed",
                             "subject": key[0], "predicate": key[1], "object": key[2],
                             "before": old_v, "after": new_v})
    if len(changes) > MAX_CHANGES:
        raise SemanticModelError("Semantic diff change budget exceeded")
    changes.sort(key=lambda x: canonical(x))
    result = {
        "schema_version": DIFF_SCHEMA,
        "before": {"contract_sha256": old.contract_sha256,
                   "semantic_fingerprint": old.semantic_fingerprint,
                   "source_digests": [{"id": k, "sha256": v} for k, v in old.source_digests]},
        "after": {"contract_sha256": new.contract_sha256,
                  "semantic_fingerprint": new.semantic_fingerprint,
                  "source_digests": [{"id": k, "sha256": v} for k, v in new.source_digests]},
        "changes": changes,
        "status": "semantic_change_detected" if changes else "no_semantic_change_in_admitted_projection",
        "authority": {"source_bytes_verified": True, "source_origin_authenticated": False,
                      "runtime_change_verified": False, "semantic_truth_verified": False},
    }
    result["report_sha256"] = _sha(canonical(result))
    return result


def _change(change_type: str, key: tuple[Any, ...]) -> dict[str, Any]:
    subject, predicate, obj, origin, attrs = key
    return {"change_type": f"relationship_{change_type}", "subject": subject,
            "predicate": predicate, "object": obj, "origin": origin,
            "attributes": [{"key": k, "value": v} for k, v in attrs]}


def verify_diff(before: dict[str, Any], before_sources: Mapping[str, bytes],
                after: dict[str, Any], after_sources: Mapping[str, bytes],
                claimed: dict[str, Any]) -> bool:
    expected = diff_contracts(before, before_sources, after, after_sources)
    if not isinstance(claimed, dict) or claimed != expected:
        raise SemanticModelError("Semantic diff does not match exact source replay")
    return True

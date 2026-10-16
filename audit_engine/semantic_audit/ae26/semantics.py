"""AE-26: language-independent semantic vocabulary, identity, and evolution.

This corrective G9.28 implementation establishes one canonical semantic model
for snapshot and diff operations.  Occurrence/source identities remain
provenance identities; semantic identity is derived from normalized meaning
and binding, never from an observation ID or evidence-source ID.

The authoritative semantic projection contains only admitted ``declared`` and
``observed`` relationships.  ``candidate`` relationships remain visible as a
separate hypothesis projection and can never alter the authoritative semantic
fingerprint.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from audit_engine.semantic_audit.ae24.contracts import (
    admit,
    canonical,
    sha as _sha,
    Admission,
)

SCHEMA = "ae26/semantic-vocabulary/v2"
DIFF_SCHEMA = "ae26/semantic-contract-diff/v3"

RELATION_SEMANTICS = {
    "PRODUCES": {
        "domain": "Component", "range": "Artifact", "inverse": "CONSUMES",
        "character": "interface",
        "meaning_fields": ("format", "schema_id", "meaning_id"),
    },
    "CONSUMES": {
        "domain": "Component", "range": "Artifact", "inverse": "PRODUCES",
        "character": "interface",
        "meaning_fields": ("format", "schema_id", "meaning_id"),
    },
    "PERFORMS": {
        "domain": "Component", "range": "Action", "inverse": None,
        "character": "behavioral_observation", "meaning_fields": (),
    },
    "FORBIDS": {
        "domain": "Component", "range": "Action", "inverse": None,
        "character": "constraint", "meaning_fields": (),
    },
    "DEPENDS_ON": {
        "domain": "Component", "range": "Component", "inverse": None,
        "character": "dependency", "meaning_fields": (),
    },
    "REQUIRES_CHECK": {
        "domain": "Component", "range": "Check", "inverse": None,
        "character": "obligation", "meaning_fields": (),
    },
    "HAS_CHECK": {
        "domain": "Component", "range": "Check", "inverse": None,
        "character": "verification_observation", "meaning_fields": (),
    },
}
CONCEPT_TYPES = frozenset(
    {"Component", "Artifact", "Action", "Check", "Meaning", "Contract", "Policy"}
)
INTERFACE_RELATIONS = frozenset({"PRODUCES", "CONSUMES"})
ADMITTED_ORIGINS = frozenset({"declared", "observed"})
CANDIDATE_ORIGIN = "candidate"
MAX_CHANGES = 12000

VOCABULARY_DIGEST = _sha(
    canonical(
        {
            "concept_types": sorted(CONCEPT_TYPES),
            "relations": RELATION_SEMANTICS,
        }
    )
)


class SemanticModelError(ValueError):
    """Invalid semantic model, unsupported interpretation, or failed replay."""


@dataclass(frozen=True)
class SemanticEdgeView:
    occurrence_id: str
    semantic_id: str
    subject: str
    predicate: str
    object: str
    origin: str
    source_id: str
    subject_kind: str
    object_kind: str
    meaning: tuple[tuple[str, str], ...]
    binding: str | None = None


@dataclass(frozen=True)
class SemanticSnapshot:
    schema_version: str
    vocabulary_digest: str
    contract_sha256: str
    graph_fingerprint: str
    source_digests: tuple[tuple[str, str], ...]
    entities: tuple[tuple[str, str], ...]
    edges: tuple[SemanticEdgeView, ...]
    semantic_records: tuple[bytes, ...]
    hypothesis_records: tuple[bytes, ...]
    policy_records: tuple[bytes, ...]
    coverage_records: tuple[bytes, ...]
    semantic_fingerprint: str
    hypothesis_fingerprint: str


def _entity_map(contract: dict[str, Any]) -> dict[str, str]:
    return {row["id"]: row["kind"] for row in contract["entities"]}


def _meaning_dict(assertion: dict[str, Any]) -> dict[str, str]:
    attrs = assertion.get("attributes", {})
    return {
        key: attrs[key]
        for key in ("format", "schema_id", "meaning_id")
        if key in attrs
    }


def _meaning_tuple(assertion: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(_meaning_dict(assertion).items())


def _binding_dict(
    assertion: dict[str, Any],
    producers_by_occurrence: Mapping[str, dict[str, Any]],
    producers_by_entity_artifact: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Resolve a CONSUMES producer selector to semantic, not occurrence, identity.

    ``producer_occurrence`` is a selector/provenance reference.  When it
    resolves to a producer contract, only the producer entity and normalized
    producer meaning enter semantic identity.  Thus changing p1 -> p2 does
    not change semantic identity when both producer occurrences express the
    same contract, while selecting a different contract version does.
    """
    if assertion["predicate"] != "CONSUMES":
        return None

    attrs = assertion.get("attributes", {})
    producer = attrs.get("producer")
    if producer is None:
        return None

    selected_occurrence = attrs.get("producer_occurrence")
    artifact = assertion["object"]

    if selected_occurrence is not None:
        producer_row = producers_by_occurrence.get(selected_occurrence)
        if (
            producer_row is None
            or producer_row["subject"] != producer
            or producer_row["object"] != artifact
            or producer_row["predicate"] != "PRODUCES"
        ):
            return {
                "producer": producer,
                "resolution": "unresolved",
            }
        if producer_row["origin"] == CANDIDATE_ORIGIN:
            return {
                "producer": producer,
                "resolution": "candidate_only",
            }
        return {
            "producer": producer,
            "resolution": "resolved",
            "producer_contract": _meaning_dict(producer_row),
        }

    choices = producers_by_entity_artifact.get((producer, artifact), [])
    admitted = [row for row in choices if row["origin"] in ADMITTED_ORIGINS]
    if not admitted:
        if any(row["origin"] == CANDIDATE_ORIGIN for row in choices):
            return {
                "producer": producer,
                "resolution": "candidate_only",
            }
        return {
            "producer": producer,
            "resolution": "unresolved",
        }

    contracts = {
        canonical(_meaning_dict(row)): _meaning_dict(row)
        for row in admitted
    }
    ordered_contracts = [
        contracts[key] for key in sorted(contracts)
    ]
    if len(ordered_contracts) == 1:
        return {
            "producer": producer,
            "resolution": "resolved",
            "producer_contract": ordered_contracts[0],
        }
    return {
        "producer": producer,
        "resolution": "ambiguous",
        "producer_contracts": ordered_contracts,
    }


def _record_for_assertion(
    assertion: dict[str, Any],
    kinds: Mapping[str, str],
    producers_by_occurrence: Mapping[str, dict[str, Any]],
    producers_by_entity_artifact: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    record = {
        "vocabulary_digest": VOCABULARY_DIGEST,
        "subject": assertion["subject"],
        "predicate": assertion["predicate"],
        "object": assertion["object"],
        "subject_kind": kinds[assertion["subject"]],
        "object_kind": kinds[assertion["object"]],
        "origin": assertion["origin"],
        "meaning": _meaning_dict(assertion),
        "binding": _binding_dict(
            assertion,
            producers_by_occurrence,
            producers_by_entity_artifact,
        ),
    }
    return record


def _record_bytes(record: dict[str, Any]) -> bytes:
    return canonical(record)


def _record_from_bytes(value: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(value)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SemanticModelError("Invalid canonical semantic record") from exc
    if canonical(obj) != value:
        raise SemanticModelError("Noncanonical semantic record")
    if not isinstance(obj, dict):
        raise SemanticModelError("Semantic record must be an object")
    return obj


def _semantic_id(record: dict[str, Any]) -> str:
    return _sha(_record_bytes(record))


def _entity_records(kinds: Mapping[str, str]) -> tuple[bytes, ...]:
    return tuple(
        _record_bytes({"id": entity_id, "kind": kind})
        for entity_id, kind in sorted(kinds.items())
    )


def _policy_records(contract: dict[str, Any]) -> tuple[bytes, ...]:
    # Policy IDs and source IDs are provenance identities, not semantic identity.
    records = {
        _record_bytes({"kind": policy["kind"]})
        for policy in contract.get("policies", [])
    }
    return tuple(sorted(records))


def _coverage_records(contract: dict[str, Any]) -> tuple[bytes, ...]:
    # Coverage source IDs are evidence provenance. Scope and completeness are
    # semantic state because they alter the meaning of an audit obligation.
    records = {
        _record_bytes(
            {
                "component": row["component"],
                "relation": row["relation"],
                "complete": row["complete"],
            }
        )
        for row in contract.get("coverage", [])
    }
    return tuple(sorted(records))


def _fingerprint(
    *,
    entities: tuple[bytes, ...],
    relations: tuple[bytes, ...],
    policies: tuple[bytes, ...],
    coverage: tuple[bytes, ...],
) -> str:
    body = {
        "schema_version": SCHEMA,
        "vocabulary_digest": VOCABULARY_DIGEST,
        "entities": [_record_from_bytes(x) for x in entities],
        "relations": [_record_from_bytes(x) for x in relations],
        "policies": [_record_from_bytes(x) for x in policies],
        "coverage": [_record_from_bytes(x) for x in coverage],
    }
    return _sha(canonical(body))


def _hypothesis_fingerprint(
    *,
    entities: tuple[bytes, ...],
    hypotheses: tuple[bytes, ...],
) -> str:
    body = {
        "schema_version": SCHEMA,
        "vocabulary_digest": VOCABULARY_DIGEST,
        "entities": [_record_from_bytes(x) for x in entities],
        "hypotheses": [_record_from_bytes(x) for x in hypotheses],
    }
    return _sha(canonical(body))


def validate_vocabulary(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
) -> Admission:
    """Admit AE-24 facts and validate the fixed semantic vocabulary."""
    admission = admit(contract, sources)
    kinds = _entity_map(contract)
    for assertion in contract["assertions"]:
        spec = RELATION_SEMANTICS.get(assertion["predicate"])
        if spec is None:
            raise SemanticModelError("Unsupported semantic predicate")
        if (
            kinds[assertion["subject"]] != spec["domain"]
            or kinds[assertion["object"]] != spec["range"]
        ):
            raise SemanticModelError(
                f"Semantic endpoint mismatch for {assertion['id']}"
            )
        attrs = assertion.get("attributes", {})
        meaning_keys = set(attrs) & {"format", "schema_id", "meaning_id"}
        if meaning_keys - set(spec["meaning_fields"]):
            raise SemanticModelError(
                f"Meaning field not applicable to {assertion['id']}"
            )
    return admission


def snapshot(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
) -> SemanticSnapshot:
    """Create one deterministic semantic model from source-bound assertions."""
    admission = validate_vocabulary(contract, sources)
    kinds = _entity_map(contract)

    producers_by_occurrence = {
        row["id"]: row
        for row in contract["assertions"]
        if row["predicate"] == "PRODUCES"
    }
    producers_by_entity_artifact: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in producers_by_occurrence.values():
        key = (row["subject"], row["object"])
        producers_by_entity_artifact.setdefault(key, []).append(row)

    edge_items = []
    authoritative_records = set()
    hypothesis_records = set()

    for row in contract["assertions"]:
        record = _record_for_assertion(
            row,
            kinds,
            producers_by_occurrence,
            producers_by_entity_artifact,
        )
        record_bytes = _record_bytes(record)
        semantic_id = _semantic_id(record)
        binding = record["binding"]
        binding_json = (
            canonical(binding).decode("utf-8")
            if binding is not None
            else None
        )
        edge_items.append(
            SemanticEdgeView(
                occurrence_id=row["id"],
                semantic_id=semantic_id,
                subject=row["subject"],
                predicate=row["predicate"],
                object=row["object"],
                origin=row["origin"],
                source_id=row["source_id"],
                subject_kind=kinds[row["subject"]],
                object_kind=kinds[row["object"]],
                meaning=_meaning_tuple(row),
                binding=binding_json,
            )
        )
        if row["origin"] in ADMITTED_ORIGINS:
            authoritative_records.add(record_bytes)
        else:
            hypothesis_records.add(record_bytes)

    edges = tuple(
        sorted(
            edge_items,
            key=lambda edge: (
                edge.subject,
                edge.predicate,
                edge.object,
                edge.origin,
                edge.occurrence_id,
            ),
        )
    )
    semantic_records = tuple(sorted(authoritative_records))
    hypotheses = tuple(sorted(hypothesis_records))
    entities = _entity_records(kinds)
    policies = _policy_records(contract)
    coverage = _coverage_records(contract)

    return SemanticSnapshot(
        schema_version=SCHEMA,
        vocabulary_digest=VOCABULARY_DIGEST,
        contract_sha256=admission.contract_digest,
        graph_fingerprint=admission.graph_digest,
        source_digests=admission.source_digests,
        entities=tuple(sorted(kinds.items())),
        edges=edges,
        semantic_records=semantic_records,
        hypothesis_records=hypotheses,
        policy_records=policies,
        coverage_records=coverage,
        semantic_fingerprint=_fingerprint(
            entities=entities,
            relations=semantic_records,
            policies=policies,
            coverage=coverage,
        ),
        hypothesis_fingerprint=_hypothesis_fingerprint(
            entities=entities,
            hypotheses=hypotheses,
        ),
    )


def _decode_records(values: tuple[bytes, ...]) -> list[dict[str, Any]]:
    return [_record_from_bytes(value) for value in values]


def semantic_projection(s: SemanticSnapshot) -> dict[str, Any]:
    """Return a detached review representation with explicit fact/hypothesis layers."""
    return {
        "schema_version": s.schema_version,
        "vocabulary_digest": s.vocabulary_digest,
        "contract_sha256": s.contract_sha256,
        "graph_fingerprint": s.graph_fingerprint,
        "source_digests": [
            {"id": key, "sha256": value}
            for key, value in s.source_digests
        ],
        "semantic_fingerprint": s.semantic_fingerprint,
        "hypothesis_fingerprint": s.hypothesis_fingerprint,
        "semantic_facts": [
            {
                **record,
                "semantic_id": _semantic_id(record),
            }
            for record in _decode_records(s.semantic_records)
        ],
        "hypotheses": [
            {
                **record,
                "semantic_id": _semantic_id(record),
            }
            for record in _decode_records(s.hypothesis_records)
        ],
        "policies": _decode_records(s.policy_records),
        "coverage": _decode_records(s.coverage_records),
        "entities": [
            {"id": key, "kind": value}
            for key, value in s.entities
        ],
        "edges": [
            {
                "occurrence_id": edge.occurrence_id,
                "semantic_id": edge.semantic_id,
                "subject": edge.subject,
                "predicate": edge.predicate,
                "object": edge.object,
                "origin": edge.origin,
                "source_id": edge.source_id,
                "subject_kind": edge.subject_kind,
                "object_kind": edge.object_kind,
                "meaning": [
                    {"key": key, "value": value}
                    for key, value in edge.meaning
                ],
                "binding": (
                    json.loads(edge.binding)
                    if edge.binding is not None
                    else None
                ),
            }
            for edge in s.edges
        ],
    }


def verify_snapshot(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    claimed: SemanticSnapshot,
) -> bool:
    if not isinstance(claimed, SemanticSnapshot):
        raise SemanticModelError("Invalid semantic snapshot")
    if snapshot(contract, sources) != claimed:
        raise SemanticModelError("Semantic snapshot mismatch on exact replay")
    return True


def verify_projection(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    claimed: dict[str, Any],
) -> dict[str, Any]:
    """Independently replay and compare a serialized semantic projection."""
    expected = semantic_projection(snapshot(contract, sources))
    if not isinstance(claimed, dict) or claimed != expected:
        raise SemanticModelError("Semantic projection mismatch on exact replay")
    return {
        "status": "source_replayed",
        "semantic_fingerprint": expected["semantic_fingerprint"],
        "hypothesis_fingerprint": expected["hypothesis_fingerprint"],
    }


def _relation_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record["subject"],
        record["predicate"],
        record["object"],
        record["origin"],
    )


def _change_for_relation(change_type: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "change_type": f"relationship_{change_type}",
        "semantic_id": _semantic_id(record),
        **record,
    }


def _change_for_hypothesis(change_type: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "change_type": f"hypothesis_{change_type}",
        "semantic_id": _semantic_id(record),
        **record,
    }


def _interface_change_records(
    old_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pair same-slot interface variants deterministically.

    No dictionary keyed only by (subject, predicate, object) is used, so
    parallel interface contracts cannot overwrite one another.  Pairing is
    canonical-byte ordered and therefore independent of input assertion order.
    """
    changes: list[dict[str, Any]] = []
    old_by_slot: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    new_by_slot: dict[tuple[Any, ...], list[dict[str, Any]]] = {}

    for record in old_records:
        if record["predicate"] in INTERFACE_RELATIONS:
            old_by_slot.setdefault(_relation_key(record), []).append(record)
    for record in new_records:
        if record["predicate"] in INTERFACE_RELATIONS:
            new_by_slot.setdefault(_relation_key(record), []).append(record)

    for slot in sorted(set(old_by_slot) & set(new_by_slot), key=lambda value: canonical({"slot": value})):
        old_variants = sorted(
            old_by_slot[slot],
            key=lambda record: _record_bytes(record),
        )
        new_variants = sorted(
            new_by_slot[slot],
            key=lambda record: _record_bytes(record),
        )
        for old_record, new_record in zip(
            old_variants,
            new_variants,
        ):
            if old_record["meaning"] != new_record["meaning"]:
                changes.append(
                    {
                        "change_type": "interface_meaning_changed",
                        "subject": slot[0],
                        "predicate": slot[1],
                        "object": slot[2],
                        "origin": slot[3],
                        "before": old_record["meaning"],
                        "after": new_record["meaning"],
                        "before_semantic_id": _semantic_id(old_record),
                        "after_semantic_id": _semantic_id(new_record),
                    }
                )
            if old_record["binding"] != new_record["binding"]:
                changes.append(
                    {
                        "change_type": "interface_binding_changed",
                        "subject": slot[0],
                        "predicate": slot[1],
                        "object": slot[2],
                        "origin": slot[3],
                        "before": old_record["binding"],
                        "after": new_record["binding"],
                        "before_semantic_id": _semantic_id(old_record),
                        "after_semantic_id": _semantic_id(new_record),
                    }
                )
    return changes


def _diff_entity_state(
    old_entities: tuple[tuple[str, str], ...],
    new_entities: tuple[tuple[str, str], ...],
) -> list[dict[str, Any]]:
    old_map = dict(old_entities)
    new_map = dict(new_entities)
    changes: list[dict[str, Any]] = []

    for entity_id in sorted(set(old_map) - set(new_map)):
        changes.append(
            {
                "change_type": "entity_removed",
                "entity_id": entity_id,
                "kind": old_map[entity_id],
            }
        )
    for entity_id in sorted(set(new_map) - set(old_map)):
        changes.append(
            {
                "change_type": "entity_added",
                "entity_id": entity_id,
                "kind": new_map[entity_id],
            }
        )
    for entity_id in sorted(set(old_map) & set(new_map)):
        if old_map[entity_id] != new_map[entity_id]:
            changes.append(
                {
                    "change_type": "entity_semantic_kind_changed",
                    "entity_id": entity_id,
                    "before": old_map[entity_id],
                    "after": new_map[entity_id],
                }
            )
    return changes


def _diff_policy_state(
    old_records: tuple[bytes, ...],
    new_records: tuple[bytes, ...],
) -> list[dict[str, Any]]:
    old_set = set(old_records)
    new_set = set(new_records)
    return [
        {
            "change_type": "policy_removed",
            **_record_from_bytes(record),
        }
        for record in sorted(old_set - new_set)
    ] + [
        {
            "change_type": "policy_added",
            **_record_from_bytes(record),
        }
        for record in sorted(new_set - old_set)
    ]


def _diff_coverage_state(
    old_records: tuple[bytes, ...],
    new_records: tuple[bytes, ...],
) -> list[dict[str, Any]]:
    old = {
        (
            _record_from_bytes(record)["component"],
            _record_from_bytes(record)["relation"],
        ): _record_from_bytes(record)
        for record in old_records
    }
    new = {
        (
            _record_from_bytes(record)["component"],
            _record_from_bytes(record)["relation"],
        ): _record_from_bytes(record)
        for record in new_records
    }
    changes: list[dict[str, Any]] = []
    for key in sorted(set(old) - set(new)):
        changes.append({"change_type": "coverage_removed", **old[key]})
    for key in sorted(set(new) - set(old)):
        changes.append({"change_type": "coverage_added", **new[key]})
    for key in sorted(set(old) & set(new)):
        if old[key]["complete"] != new[key]["complete"]:
            changes.append(
                {
                    "change_type": "coverage_completeness_changed",
                    "component": key[0],
                    "relation": key[1],
                    "before": old[key]["complete"],
                    "after": new[key]["complete"],
                }
            )
    return changes


def diff_contracts(
    before: dict[str, Any],
    before_sources: Mapping[str, bytes],
    after: dict[str, Any],
    after_sources: Mapping[str, bytes],
) -> dict[str, Any]:
    """Classify deterministic semantic and hypothesis evolution."""
    old = snapshot(before, before_sources)
    new = snapshot(after, after_sources)

    old_relations = {
        _record_bytes(_record_from_bytes(value)): _record_from_bytes(value)
        for value in old.semantic_records
    }
    new_relations = {
        _record_bytes(_record_from_bytes(value)): _record_from_bytes(value)
        for value in new.semantic_records
    }
    old_hypotheses = {
        _record_bytes(_record_from_bytes(value)): _record_from_bytes(value)
        for value in old.hypothesis_records
    }
    new_hypotheses = {
        _record_bytes(_record_from_bytes(value)): _record_from_bytes(value)
        for value in new.hypothesis_records
    }

    changes: list[dict[str, Any]] = []
    changes.extend(
        _change_for_relation("removed", old_relations[key])
        for key in sorted(set(old_relations) - set(new_relations))
    )
    changes.extend(
        _change_for_relation("added", new_relations[key])
        for key in sorted(set(new_relations) - set(old_relations))
    )
    changes.extend(
        _change_for_hypothesis("removed", old_hypotheses[key])
        for key in sorted(set(old_hypotheses) - set(new_hypotheses))
    )
    changes.extend(
        _change_for_hypothesis("added", new_hypotheses[key])
        for key in sorted(set(new_hypotheses) - set(old_hypotheses))
    )

    changes.extend(_diff_entity_state(old.entities, new.entities))
    changes.extend(_diff_policy_state(old.policy_records, new.policy_records))
    changes.extend(_diff_coverage_state(old.coverage_records, new.coverage_records))
    changes.extend(
        _interface_change_records(
            list(old_relations.values()),
            list(new_relations.values()),
        )
    )

    if len(changes) > MAX_CHANGES:
        raise SemanticModelError("Semantic diff change budget exceeded")

    changes.sort(key=lambda item: canonical(item))

    authoritative_change_types = {
        "relationship_removed",
        "relationship_added",
        "entity_removed",
        "entity_added",
        "entity_semantic_kind_changed",
        "policy_removed",
        "policy_added",
        "coverage_removed",
        "coverage_added",
        "coverage_completeness_changed",
        "interface_meaning_changed",
        "interface_binding_changed",
    }
    hypothesis_change_types = {"hypothesis_removed", "hypothesis_added"}
    authoritative_changed = any(
        item["change_type"] in authoritative_change_types
        for item in changes
    )
    hypothesis_changed = any(
        item["change_type"] in hypothesis_change_types
        for item in changes
    )

    if authoritative_changed and hypothesis_changed:
        status = "semantic_and_hypothesis_change_detected"
    elif authoritative_changed:
        status = "semantic_change_detected"
    elif hypothesis_changed:
        status = "hypothesis_change_detected"
    else:
        status = "no_semantic_change_in_admitted_projection"

    result = {
        "schema_version": DIFF_SCHEMA,
        "vocabulary_digest": VOCABULARY_DIGEST,
        "before": {
            "contract_sha256": old.contract_sha256,
            "semantic_fingerprint": old.semantic_fingerprint,
            "hypothesis_fingerprint": old.hypothesis_fingerprint,
            "source_digests": [
                {"id": key, "sha256": value}
                for key, value in old.source_digests
            ],
        },
        "after": {
            "contract_sha256": new.contract_sha256,
            "semantic_fingerprint": new.semantic_fingerprint,
            "hypothesis_fingerprint": new.hypothesis_fingerprint,
            "source_digests": [
                {"id": key, "sha256": value}
                for key, value in new.source_digests
            ],
        },
        "changes": changes,
        "status": status,
        "authority": {
            "source_bytes_verified": True,
            "source_origin_authenticated": False,
            "runtime_change_verified": False,
            "semantic_truth_verified": False,
            "candidate_hypotheses_verified": False,
        },
    }
    result["semantic_diff_fingerprint"] = semantic_diff_fingerprint(result)
    result["report_sha256"] = _sha(canonical(result))
    return result


def _semantic_diff_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return the order-independent semantic content of a diff report.

    ``contract_sha256`` and ``report_sha256`` intentionally do not participate:
    the former identifies the exact source contract supplied to AE-24 and may
    change when assertion ordering changes, while the latter seals the whole
    report and therefore changes whenever the contract identity changes.

    This fingerprint identifies the *derived semantic evolution result*.
    It is not a claim that the semantic truth itself has been independently
    verified.
    """
    before = result["before"]
    after = result["after"]
    return {
        "schema_version": result["schema_version"],
        "vocabulary_digest": result["vocabulary_digest"],
        "before": {
            "semantic_fingerprint": before["semantic_fingerprint"],
            "hypothesis_fingerprint": before["hypothesis_fingerprint"],
        },
        "after": {
            "semantic_fingerprint": after["semantic_fingerprint"],
            "hypothesis_fingerprint": after["hypothesis_fingerprint"],
        },
        "changes": result["changes"],
        "status": result["status"],
    }


def semantic_diff_fingerprint(result: Mapping[str, Any]) -> str:
    """Compute a deterministic identity for the semantic content of a diff."""
    return _sha(canonical(_semantic_diff_payload(result)))


def verify_diff(
    before: dict[str, Any],
    before_sources: Mapping[str, bytes],
    after: dict[str, Any],
    after_sources: Mapping[str, bytes],
    claimed: dict[str, Any],
) -> bool:
    expected = diff_contracts(
        before,
        before_sources,
        after,
        after_sources,
    )
    if not isinstance(claimed, dict) or claimed != expected:
        raise SemanticModelError(
            "Semantic diff does not match exact source replay"
        )
    return True

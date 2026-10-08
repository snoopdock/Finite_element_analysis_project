"""Deterministic domain verifiers for G3.1.1 semantic audit rules.

These verifiers interpret explicit obligations only. They do not define policy,
create findings, or infer scientific truth from graph topology.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from audit_engine.semantic_audit.graph.analysis.identity import edge_fingerprint
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus

from .models import VerificationAttempt, VerificationDecision
from .verifier import VerifierDescriptor


def _normalized_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("Expected a string or sequence of strings.")
    return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _mapping_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _read_path(mapping: Mapping[str, Any], dotted_path: str):
    current: Any = mapping
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


class GraphAttributeConstraintVerifier:
    """Verify node-attribute constraints around selected graph observations."""

    descriptor = VerifierDescriptor(
        verifier_id="graph-attribute-constraint",
        version="1.0.0",
        supported_obligation_types=("graph_attribute_constraint",),
    )

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        graph = context.require_graph()
        observations = context.selected_observations(obligation)
        if not observations:
            return VerificationAttempt.create(
                obligation_id=obligation.obligation_id,
                verifier_id=self.descriptor.verifier_id,
                verifier_version=self.descriptor.version,
                decision=VerificationDecision.INCONCLUSIVE,
                evidence_state=VerificationStatus.INCONCLUSIVE,
                evidence_ids=obligation.evidence_ids,
                details={"reason": "no_selected_observations"},
            )

        relation_types = set(_normalized_values(obligation.parameters.get("relation_types")))
        source_types = set(_normalized_values(obligation.parameters.get("source_entity_types")))
        target_types = set(_normalized_values(obligation.parameters.get("target_entity_types")))
        source_attributes = dict(obligation.parameters.get("source_attributes", {}))
        target_attributes = dict(obligation.parameters.get("target_attributes", {}))

        matched = []
        checked = []
        for observation in observations:
            source = graph.get_node(observation.subject_id)
            target = graph.get_node(observation.object_id)
            if source is None or target is None:
                raise ValueError("Selected observation references a node absent from the graph.")
            checks = {
                "relation_type": not relation_types or observation.predicate in relation_types,
                "source_entity_type": not source_types or source.entity_type in source_types,
                "target_entity_type": not target_types or target.entity_type in target_types,
                "source_attributes": _mapping_matches(source.attributes, source_attributes),
                "target_attributes": _mapping_matches(target.attributes, target_attributes),
            }
            record = {"observation_id": observation.observation_id, "checks": checks}
            checked.append(record)
            if all(checks.values()):
                matched.append(observation.observation_id)

        decision = (
            VerificationDecision.CONFIRMED if matched else VerificationDecision.REFUTED
        )
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=decision,
            evidence_state=VerificationStatus.VALIDATED,
            evidence_ids=obligation.evidence_ids,
            details={
                "matched_observation_ids": sorted(matched),
                "checked": checked,
            },
        )


class RequiredRelationshipVerifier:
    """Verify that source entities possess a required typed relationship.

    Absence is verified only relative to the exact canonical graph snapshot
    bound to the analysis result. It is not a claim about external reality.
    """

    descriptor = VerifierDescriptor(
        verifier_id="required-relationship",
        version="1.0.0",
        supported_obligation_types=("required_relationship",),
    )

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        graph = context.require_graph()
        relation_types = set(_normalized_values(obligation.parameters.get("relation_types")))
        if not relation_types:
            raise ValueError("required_relationship requires at least one relation type.")
        target_types = set(_normalized_values(obligation.parameters.get("target_entity_types")))
        direction = str(obligation.parameters.get("direction", "outgoing")).strip().lower()
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("direction must be outgoing, incoming, or both.")
        minimum_matches = int(obligation.parameters.get("minimum_matches", 1))
        if minimum_matches < 1:
            raise ValueError("minimum_matches must be at least 1.")

        requested_entities = obligation.parameters.get("entity_ids")
        if requested_entities is None:
            entity_ids = tuple(context.analysis_result.source_entities)
        else:
            entity_ids = _normalized_values(requested_entities)
        if not entity_ids:
            return VerificationAttempt.create(
                obligation_id=obligation.obligation_id,
                verifier_id=self.descriptor.verifier_id,
                verifier_version=self.descriptor.version,
                decision=VerificationDecision.INCONCLUSIVE,
                evidence_state=VerificationStatus.INCONCLUSIVE,
                evidence_ids=obligation.evidence_ids,
                details={"reason": "no_source_entities"},
            )

        counts: dict[str, int] = {}
        matched_edges: list[dict[str, str]] = []
        for entity_id in entity_ids:
            if graph.get_node(entity_id) is None:
                raise ValueError(f"Required-relationship source node is absent: {entity_id!r}")
            count = 0
            for edge in graph.edges:
                orientations = []
                if direction in {"outgoing", "both"} and edge.source_id == entity_id:
                    orientations.append(edge.target_id)
                if direction in {"incoming", "both"} and edge.target_id == entity_id:
                    orientations.append(edge.source_id)
                if not orientations or edge.relation_type not in relation_types:
                    continue
                for other_id in orientations:
                    target = graph.get_node(other_id)
                    if target is None:
                        continue
                    if target_types and target.entity_type not in target_types:
                        continue
                    count += 1
                    matched_edges.append(
                        {
                            "entity_id": entity_id,
                            "other_id": other_id,
                            "relation_type": edge.relation_type,
                            "edge_fingerprint": edge_fingerprint(edge),
                        }
                    )
            counts[entity_id] = count

        missing = sorted(
            entity_id for entity_id, count in counts.items() if count < minimum_matches
        )
        decision = (
            VerificationDecision.CONFIRMED if not missing else VerificationDecision.REFUTED
        )
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=decision,
            evidence_state=VerificationStatus.VALIDATED,
            evidence_ids=obligation.evidence_ids,
            details={
                "relation_types": sorted(relation_types),
                "target_entity_types": sorted(target_types),
                "minimum_matches": minimum_matches,
                "match_counts": counts,
                "missing_entity_ids": missing,
                "matched_edges": matched_edges,
            },
        )


class ProvenanceCompletenessVerifier:
    """Check explicit provenance paths on selected evidence records."""

    descriptor = VerifierDescriptor(
        verifier_id="provenance-completeness",
        version="1.0.0",
        supported_obligation_types=("provenance_completeness",),
    )

    def verify(self, obligation, context):
        context.validate_obligation_binding(obligation)
        required_paths = _normalized_values(obligation.parameters.get("required_paths"))
        if not required_paths:
            raise ValueError("provenance_completeness requires required_paths.")
        evidence = context.selected_evidence(obligation)
        if not evidence:
            return VerificationAttempt.create(
                obligation_id=obligation.obligation_id,
                verifier_id=self.descriptor.verifier_id,
                verifier_version=self.descriptor.version,
                decision=VerificationDecision.INCONCLUSIVE,
                evidence_state=VerificationStatus.INCONCLUSIVE,
                evidence_ids=(),
                details={"reason": "no_selected_evidence", "required_paths": list(required_paths)},
            )

        missing_by_evidence: dict[str, list[str]] = {}
        for record in evidence:
            missing = [
                path
                for path in required_paths
                if _read_path(record.provenance, path) in (None, "", [], {})
            ]
            if missing:
                missing_by_evidence[record.evidence_id] = missing

        decision = (
            VerificationDecision.CONFIRMED
            if not missing_by_evidence
            else VerificationDecision.REFUTED
        )
        return VerificationAttempt.create(
            obligation_id=obligation.obligation_id,
            verifier_id=self.descriptor.verifier_id,
            verifier_version=self.descriptor.version,
            decision=decision,
            evidence_state=VerificationStatus.VALIDATED,
            evidence_ids=[record.evidence_id for record in evidence],
            details={
                "required_paths": list(required_paths),
                "missing_by_evidence": missing_by_evidence,
            },
        )

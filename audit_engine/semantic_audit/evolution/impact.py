"""Fine-grained semantic change atoms and audit-artifact dependency profiles.

G3.2.1 deliberately models *impact* separately from semantic judgment.  A
change atom says what changed.  A dependency profile says which graph facts an
audit artifact relied upon.  Propagation combines the two later; this module
never creates findings and never mutates the canonical graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.graph.analysis.models import AnalysisType
from audit_engine.semantic_audit.graph.analysis.results import GraphAnalysisResult
from audit_engine.semantic_audit.verification.receipts import VerificationReceipt

from .delta import GraphDelta


IMPACT_SCHEMA_VERSION = "semantic_change_impact/v1"


class ChangeKind(str, Enum):
    NODE_ADDED = "node_added"
    NODE_REMOVED = "node_removed"
    NODE_MODIFIED = "node_modified"
    EDGE_ADDED = "edge_added"
    EDGE_REMOVED = "edge_removed"
    SEMANTIC_CONTEXT_CHANGED = "semantic_context_changed"


@dataclass(frozen=True)
class ChangeAtom:
    change_id: str
    kind: ChangeKind
    node_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    relation_types: tuple[str, ...] = field(default_factory=tuple)
    semantic_context_fields: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "kind": self.kind.value,
            "node_ids": list(self.node_ids),
            "evidence_ids": list(self.evidence_ids),
            "relation_types": list(self.relation_types),
            "semantic_context_fields": list(self.semantic_context_fields),
        }


def changes_from_delta(delta: GraphDelta) -> tuple[ChangeAtom, ...]:
    """Normalize a graph delta into deterministic, backend-neutral change atoms."""

    atoms: list[ChangeAtom] = []
    for node in delta.added_nodes:
        atoms.append(ChangeAtom(f"node-added:{node.node_id}", ChangeKind.NODE_ADDED, (node.node_id,)))
    for node in delta.removed_nodes:
        atoms.append(ChangeAtom(f"node-removed:{node.node_id}", ChangeKind.NODE_REMOVED, (node.node_id,)))
    for mutation in delta.modified_nodes:
        atoms.append(ChangeAtom(f"node-modified:{mutation.node_id}", ChangeKind.NODE_MODIFIED, (mutation.node_id,)))
    for edge in delta.added_edges:
        atoms.append(
            ChangeAtom(
                f"edge-added:{edge.edge_id}",
                ChangeKind.EDGE_ADDED,
                (edge.source_id, edge.target_id),
                (edge.edge_fingerprint,),
                (edge.relation_type,),
            )
        )
    for edge in delta.removed_edges:
        atoms.append(
            ChangeAtom(
                f"edge-removed:{edge.edge_id}",
                ChangeKind.EDGE_REMOVED,
                (edge.source_id, edge.target_id),
                (edge.edge_fingerprint,),
                (edge.relation_type,),
            )
        )
    if delta.semantic_context_delta.changed:
        fields = tuple(field_name for field_name, _, _ in delta.semantic_context_delta.changed_fields)
        atoms.append(
            ChangeAtom(
                "semantic-context-changed:" + ",".join(fields),
                ChangeKind.SEMANTIC_CONTEXT_CHANGED,
                semantic_context_fields=fields,
            )
        )
    return tuple(sorted(atoms, key=lambda item: (item.kind.value, item.change_id)))


class ImpactScope(str, Enum):
    """How safely a prior analysis can localize graph changes.

    ``LOCAL_NEIGHBORHOOD`` means changes can be screened by the source/
    discovered neighborhood and relation filter. ``PATH_FRONTIER`` remains
    conservative for additions touching the known path/frontier. ``GLOBAL``
    means an arbitrary graph change can affect completeness and therefore must
    trigger re-analysis.
    """

    LOCAL_NEIGHBORHOOD = "local_neighborhood"
    PATH_FRONTIER = "path_frontier"
    GLOBAL = "global"


@dataclass(frozen=True)
class ArtifactDependencyProfile:
    artifact_type: str
    artifact_id: str
    graph_fingerprint: str
    semantic_context_fingerprint: str
    node_ids: tuple[str, ...] = field(default_factory=tuple)
    source_node_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    observation_ids: tuple[str, ...] = field(default_factory=tuple)
    relation_types: tuple[str, ...] = field(default_factory=tuple)
    upstream_artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    impact_scope: ImpactScope = ImpactScope.GLOBAL
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "graph_fingerprint": self.graph_fingerprint,
            "semantic_context_fingerprint": self.semantic_context_fingerprint,
            "node_ids": list(self.node_ids),
            "source_node_ids": list(self.source_node_ids),
            "evidence_ids": list(self.evidence_ids),
            "observation_ids": list(self.observation_ids),
            "relation_types": list(self.relation_types),
            "upstream_artifact_ids": list(self.upstream_artifact_ids),
            "impact_scope": self.impact_scope.value,
            "metadata": dict(self.metadata),
        }


def _analysis_scope(result: GraphAnalysisResult) -> ImpactScope:
    if result.analysis_type in (AnalysisType.STRUCTURAL, AnalysisType.DEPENDENCY):
        return ImpactScope.LOCAL_NEIGHBORHOOD
    if result.analysis_type is AnalysisType.PATH:
        return ImpactScope.PATH_FRONTIER
    return ImpactScope.GLOBAL


def profile_analysis(result: GraphAnalysisResult) -> ArtifactDependencyProfile:
    nodes = set(result.source_entities) | set(result.discovered_entities)
    observations = []
    relations = set()
    for observation in result.observations:
        nodes.update((observation.subject_id, observation.object_id))
        observations.append(observation.observation_id)
    configured_relations = result.parameters.get("relation_types", ())
    relations.update(str(value) for value in configured_relations if str(value))
    target = result.parameters.get("target_entity")
    if isinstance(target, str) and target:
        nodes.add(target)

    node_depths: dict[str, int] = {node_id: 0 for node_id in result.source_entities}
    for observation in result.observations:
        traversed_from = observation.metadata.get("traversed_from")
        traversed_to = observation.metadata.get("traversed_to")
        if isinstance(traversed_from, str):
            node_depths[traversed_from] = min(
                node_depths.get(traversed_from, max(observation.depth - 1, 0)),
                max(observation.depth - 1, 0),
            )
        if isinstance(traversed_to, str):
            node_depths[traversed_to] = min(
                node_depths.get(traversed_to, observation.depth),
                observation.depth,
            )
    profile_metadata = {
        "analysis_type": result.analysis_type.value,
        "query_id": result.query_id,
        "direction": result.parameters.get("direction", "outgoing"),
        "max_depth": result.parameters.get("max_depth"),
        "node_depths": dict(sorted(node_depths.items())),
    }
    return ArtifactDependencyProfile(
        artifact_type="analysis",
        artifact_id=result.analysis_id,
        graph_fingerprint=result.graph_fingerprint,
        semantic_context_fingerprint=result.semantic_context.fingerprint,
        node_ids=tuple(sorted(nodes)),
        source_node_ids=tuple(sorted(result.source_entities)),
        evidence_ids=tuple(sorted(record.evidence_id for record in result.evidence)),
        observation_ids=tuple(sorted(observations)),
        relation_types=tuple(sorted(relations)),
        impact_scope=_analysis_scope(result),
        metadata=profile_metadata,
    )


def profile_receipt(receipt: VerificationReceipt) -> ArtifactDependencyProfile:
    details = dict(receipt.details)
    nodes: set[str] = set()
    relations: set[str] = set()
    evidence = set(receipt.evidence_ids)

    for item in details.get("checked", ()):
        if isinstance(item, Mapping):
            for key in ("subject_id", "object_id"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    nodes.add(value)
    for item in details.get("matched_edges", ()):
        if not isinstance(item, Mapping):
            continue
        for key in ("entity_id", "other_id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                nodes.add(value)
        relation = item.get("relation_type")
        if isinstance(relation, str) and relation:
            relations.add(relation)
        fingerprint = item.get("edge_fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            evidence.add(fingerprint)
    match_counts = details.get("match_counts", {})
    if isinstance(match_counts, Mapping):
        nodes.update(str(key) for key in match_counts if str(key))
    relations.update(str(value) for value in details.get("relation_types", ()) if str(value))

    return ArtifactDependencyProfile(
        artifact_type="verification_receipt",
        artifact_id=receipt.receipt_id,
        graph_fingerprint=receipt.graph_fingerprint,
        semantic_context_fingerprint=receipt.semantic_context_fingerprint,
        node_ids=tuple(sorted(nodes)),
        evidence_ids=tuple(sorted(evidence)),
        relation_types=tuple(sorted(relations)),
        upstream_artifact_ids=(receipt.source_analysis_id,),
        impact_scope=ImpactScope.GLOBAL,
        metadata={"verifier_id": receipt.verifier_id, "obligation_id": receipt.obligation_id},
    )


def profile_finding(finding: AuditFinding) -> ArtifactDependencyProfile:
    return ArtifactDependencyProfile(
        artifact_type="finding",
        artifact_id=finding.finding_id,
        graph_fingerprint=finding.graph_fingerprint,
        semantic_context_fingerprint=finding.semantic_context_fingerprint,
        evidence_ids=tuple(sorted(finding.evidence_ids)),
        upstream_artifact_ids=(finding.receipt_id,),
        impact_scope=ImpactScope.GLOBAL,
        metadata={"rule_id": finding.rule_id, "severity": finding.severity},
    )


class AuditArtifactDependencyIndex:
    """Validated dependency index for incremental impact propagation."""

    def __init__(self) -> None:
        self._profiles: dict[str, ArtifactDependencyProfile] = {}
        self._downstream: dict[str, set[str]] = {}

    def add_profile(self, profile: ArtifactDependencyProfile) -> None:
        existing = self._profiles.get(profile.artifact_id)
        if existing is not None and existing != profile:
            raise ValueError(f"Artifact dependency identity collision: {profile.artifact_id}")
        self._profiles[profile.artifact_id] = profile
        for upstream in profile.upstream_artifact_ids:
            self._downstream.setdefault(upstream, set()).add(profile.artifact_id)

    def add_artifact(self, artifact: GraphAnalysisResult | VerificationReceipt | AuditFinding) -> None:
        if isinstance(artifact, GraphAnalysisResult):
            self.add_profile(profile_analysis(artifact))
            return
        if isinstance(artifact, VerificationReceipt):
            self.add_profile(profile_receipt(artifact))
            return
        if isinstance(artifact, AuditFinding):
            self.add_profile(profile_finding(artifact))
            return
        raise TypeError(f"Unsupported audit artifact type: {type(artifact).__name__}")

    @classmethod
    def build(
        cls,
        artifacts: Iterable[GraphAnalysisResult | VerificationReceipt | AuditFinding],
    ) -> "AuditArtifactDependencyIndex":
        index = cls()
        for artifact in artifacts:
            index.add_artifact(artifact)
        return index

    def get(self, artifact_id: str) -> ArtifactDependencyProfile | None:
        return self._profiles.get(artifact_id)

    def profiles(self) -> tuple[ArtifactDependencyProfile, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))

    def downstream_of(self, artifact_id: str, *, transitive: bool = True) -> tuple[str, ...]:
        discovered: set[str] = set()
        frontier = list(sorted(self._downstream.get(artifact_id, ())))
        while frontier:
            current = frontier.pop(0)
            if current in discovered:
                continue
            discovered.add(current)
            if transitive:
                frontier.extend(sorted(self._downstream.get(current, ())))
        return tuple(sorted(discovered))

    def unresolved_upstream_ids(self) -> tuple[str, ...]:
        missing = {
            upstream
            for profile in self._profiles.values()
            for upstream in profile.upstream_artifact_ids
            if upstream not in self._profiles
        }
        return tuple(sorted(missing))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": IMPACT_SCHEMA_VERSION,
            "profiles": [profile.to_dict() for profile in self.profiles()],
            "unresolved_upstream_ids": list(self.unresolved_upstream_ids()),
        }

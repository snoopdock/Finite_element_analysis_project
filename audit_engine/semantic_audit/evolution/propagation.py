"""Incremental, dependency-aware impact propagation for audit artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .delta import GraphDelta
from .impact import (
    ArtifactDependencyProfile,
    AuditArtifactDependencyIndex,
    ChangeAtom,
    ChangeKind,
    ImpactScope,
    changes_from_delta,
)
from .invalidation import ArtifactValidity
from .snapshots import GraphSnapshot


IMPACT_PROPAGATION_SCHEMA_VERSION = "semantic_impact_propagation/v1"


@dataclass(frozen=True)
class ArtifactImpact:
    artifact_type: str
    artifact_id: str
    validity: ArtifactValidity
    reasons: tuple[str, ...] = field(default_factory=tuple)
    change_ids: tuple[str, ...] = field(default_factory=tuple)
    inherited_from: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "validity": self.validity.value,
            "reasons": list(self.reasons),
            "change_ids": list(self.change_ids),
            "inherited_from": list(self.inherited_from),
        }


@dataclass(frozen=True)
class ImpactPropagationReport:
    before_snapshot_id: str
    after_snapshot_id: str
    changes: tuple[ChangeAtom, ...]
    impacts: tuple[ArtifactImpact, ...]
    unresolved_upstream_ids: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = IMPACT_PROPAGATION_SCHEMA_VERSION

    def by_id(self, artifact_id: str) -> ArtifactImpact | None:
        return next((item for item in self.impacts if item.artifact_id == artifact_id), None)

    @property
    def affected_ids(self) -> tuple[str, ...]:
        return tuple(
            item.artifact_id
            for item in self.impacts
            if item.validity is not ArtifactValidity.CURRENT
        )

    def to_dict(self) -> dict[str, Any]:
        counts = {state.value: 0 for state in ArtifactValidity}
        for item in self.impacts:
            counts[item.validity.value] += 1
        return {
            "schema_version": self.schema_version,
            "before_snapshot_id": self.before_snapshot_id,
            "after_snapshot_id": self.after_snapshot_id,
            "summary": counts,
            "changes": [item.to_dict() for item in self.changes],
            "impacts": [item.to_dict() for item in self.impacts],
            "unresolved_upstream_ids": list(self.unresolved_upstream_ids),
        }


def _relation_relevant(profile: ArtifactDependencyProfile, atom: ChangeAtom) -> bool:
    if not profile.relation_types or not atom.relation_types:
        return True
    return bool(set(profile.relation_types) & set(atom.relation_types))


def _edge_touches_active_frontier(profile: ArtifactDependencyProfile, atom: ChangeAtom) -> bool:
    node_depths = {
        str(key): int(value)
        for key, value in dict(profile.metadata.get("node_depths", {})).items()
    }
    max_depth = profile.metadata.get("max_depth")
    direction = str(profile.metadata.get("direction", "outgoing"))
    if max_depth is None:
        depth_allows = lambda node_id: node_id in node_depths
    else:
        depth_limit = int(max_depth)
        depth_allows = lambda node_id: node_id in node_depths and node_depths[node_id] < depth_limit
    if len(atom.node_ids) != 2:
        return bool(set(profile.node_ids) & set(atom.node_ids))
    source_id, target_id = atom.node_ids
    if direction == "outgoing":
        return depth_allows(source_id)
    if direction == "incoming":
        return depth_allows(target_id)
    return depth_allows(source_id) or depth_allows(target_id)


def _direct_analysis_impact(
    profile: ArtifactDependencyProfile,
    changes: tuple[ChangeAtom, ...],
    *,
    fully_removed_evidence_ids: set[str],
) -> ArtifactImpact:
    reasons: list[str] = []
    change_ids: list[str] = []
    validity = ArtifactValidity.CURRENT
    node_set = set(profile.node_ids)
    source_set = set(profile.source_node_ids)
    evidence_set = set(profile.evidence_ids)

    for atom in changes:
        atom_nodes = set(atom.node_ids)
        atom_evidence = set(atom.evidence_ids)

        if atom.kind is ChangeKind.SEMANTIC_CONTEXT_CHANGED:
            validity = ArtifactValidity.STALE
            reasons.append("semantic_context_changed")
            change_ids.append(atom.change_id)
            continue

        if (
            atom.kind is ChangeKind.EDGE_REMOVED
            and evidence_set & atom_evidence & fully_removed_evidence_ids
        ):
            validity = ArtifactValidity.STALE
            reasons.append("supporting_evidence_removed")
            change_ids.append(atom.change_id)
            continue

        if atom.kind is ChangeKind.NODE_REMOVED and source_set & atom_nodes:
            validity = ArtifactValidity.STALE
            reasons.append("source_entity_removed")
            change_ids.append(atom.change_id)
            continue

        if atom.kind is ChangeKind.NODE_REMOVED and node_set & atom_nodes:
            if validity is not ArtifactValidity.STALE:
                validity = ArtifactValidity.RECHECK_REQUIRED
            reasons.append("referenced_entity_removed")
            change_ids.append(atom.change_id)
            continue

        if atom.kind is ChangeKind.NODE_MODIFIED and node_set & atom_nodes:
            if validity is not ArtifactValidity.STALE:
                validity = ArtifactValidity.RECHECK_REQUIRED
            reasons.append("referenced_entity_modified")
            change_ids.append(atom.change_id)
            continue

        if profile.impact_scope in (ImpactScope.LOCAL_NEIGHBORHOOD, ImpactScope.PATH_FRONTIER):
            if atom.kind is ChangeKind.EDGE_ADDED:
                if _edge_touches_active_frontier(profile, atom) and _relation_relevant(profile, atom):
                    if validity is not ArtifactValidity.STALE:
                        validity = ArtifactValidity.RECHECK_REQUIRED
                    reasons.append("relevant_neighborhood_changed")
                    change_ids.append(atom.change_id)
        elif profile.impact_scope is ImpactScope.GLOBAL:
            if atom.kind is not ChangeKind.SEMANTIC_CONTEXT_CHANGED:
                if validity is not ArtifactValidity.STALE:
                    validity = ArtifactValidity.RECHECK_REQUIRED
                reasons.append("global_analysis_source_graph_changed")
                change_ids.append(atom.change_id)

    return ArtifactImpact(
        artifact_type=profile.artifact_type,
        artifact_id=profile.artifact_id,
        validity=validity,
        reasons=tuple(dict.fromkeys(reasons)),
        change_ids=tuple(dict.fromkeys(change_ids)),
    )


def _direct_nonanalysis_impact(
    profile: ArtifactDependencyProfile,
    changes: tuple[ChangeAtom, ...],
    *,
    fully_removed_evidence_ids: set[str],
) -> ArtifactImpact:
    validity = ArtifactValidity.CURRENT
    reasons: list[str] = []
    change_ids: list[str] = []
    node_set = set(profile.node_ids)
    evidence_set = set(profile.evidence_ids)
    for atom in changes:
        atom_evidence = set(atom.evidence_ids)
        atom_nodes = set(atom.node_ids)
        if atom.kind is ChangeKind.SEMANTIC_CONTEXT_CHANGED:
            return ArtifactImpact(
                profile.artifact_type,
                profile.artifact_id,
                ArtifactValidity.STALE,
                ("semantic_context_changed",),
                (atom.change_id,),
            )
        if (
            atom.kind is ChangeKind.EDGE_REMOVED
            and evidence_set & atom_evidence & fully_removed_evidence_ids
        ):
            validity = ArtifactValidity.STALE
            reasons.append("supporting_evidence_removed")
            change_ids.append(atom.change_id)
            continue
        if node_set:
            if atom.kind is ChangeKind.NODE_REMOVED and node_set & atom_nodes:
                validity = ArtifactValidity.STALE
                reasons.append("verifier_entity_removed")
                change_ids.append(atom.change_id)
                continue
            if atom.kind is ChangeKind.NODE_MODIFIED and node_set & atom_nodes:
                if validity is not ArtifactValidity.STALE:
                    validity = ArtifactValidity.RECHECK_REQUIRED
                reasons.append("verifier_entity_modified")
                change_ids.append(atom.change_id)
                continue
            if atom.kind in (ChangeKind.EDGE_ADDED, ChangeKind.EDGE_REMOVED):
                if node_set & atom_nodes and _relation_relevant(profile, atom):
                    if validity is not ArtifactValidity.STALE:
                        validity = ArtifactValidity.RECHECK_REQUIRED
                    reasons.append("verifier_relationship_neighborhood_changed")
                    change_ids.append(atom.change_id)
    return ArtifactImpact(
        profile.artifact_type,
        profile.artifact_id,
        validity,
        tuple(dict.fromkeys(reasons)),
        tuple(dict.fromkeys(change_ids)),
    )


def _merge_inherited(
    profile: ArtifactDependencyProfile,
    direct: ArtifactImpact,
    impacts: dict[str, ArtifactImpact],
) -> ArtifactImpact:
    validity = direct.validity
    reasons = list(direct.reasons)
    change_ids = list(direct.change_ids)
    inherited_from: list[str] = []

    for upstream_id in profile.upstream_artifact_ids:
        upstream = impacts.get(upstream_id)
        if upstream is None:
            if validity is ArtifactValidity.CURRENT:
                validity = ArtifactValidity.RECHECK_REQUIRED
            reasons.append("upstream_artifact_unavailable")
            inherited_from.append(upstream_id)
            continue
        if upstream.validity is ArtifactValidity.STALE:
            validity = ArtifactValidity.STALE
            reasons.append("upstream_artifact_stale")
            change_ids.extend(upstream.change_ids)
            inherited_from.append(upstream_id)
        elif upstream.validity is ArtifactValidity.RECHECK_REQUIRED:
            if validity is ArtifactValidity.CURRENT:
                validity = ArtifactValidity.RECHECK_REQUIRED
            reasons.append("upstream_artifact_requires_recheck")
            change_ids.extend(upstream.change_ids)
            inherited_from.append(upstream_id)

    return ArtifactImpact(
        artifact_type=profile.artifact_type,
        artifact_id=profile.artifact_id,
        validity=validity,
        reasons=tuple(dict.fromkeys(reasons)),
        change_ids=tuple(dict.fromkeys(change_ids)),
        inherited_from=tuple(dict.fromkeys(inherited_from)),
    )


def propagate_impacts(
    *,
    before: GraphSnapshot,
    after: GraphSnapshot,
    delta: GraphDelta,
    dependency_index: AuditArtifactDependencyIndex,
) -> ImpactPropagationReport:
    if delta.before_snapshot_id != before.snapshot_id or delta.after_snapshot_id != after.snapshot_id:
        raise ValueError("GraphDelta does not describe the supplied snapshots.")

    changes = changes_from_delta(delta)
    fully_removed_evidence_ids = set(delta.removed_evidence_ids)
    impacts: dict[str, ArtifactImpact] = {}
    profiles = dependency_index.profiles()

    # Analyses are roots.  Receipts and findings are evaluated after their
    # upstream artifacts so validity can propagate monotonically downstream.
    ordered = sorted(
        profiles,
        key=lambda profile: (
            {"analysis": 0, "verification_receipt": 1, "finding": 2}.get(profile.artifact_type, 3),
            profile.artifact_id,
        ),
    )
    for profile in ordered:
        if profile.graph_fingerprint != before.graph_fingerprint or profile.semantic_context_fingerprint != before.semantic_context_fingerprint:
            direct = ArtifactImpact(
                profile.artifact_type,
                profile.artifact_id,
                ArtifactValidity.STALE,
                reasons=("artifact_not_bound_to_before_snapshot",),
            )
        elif profile.artifact_type == "analysis":
            direct = _direct_analysis_impact(
                profile,
                changes,
                fully_removed_evidence_ids=fully_removed_evidence_ids,
            )
        else:
            direct = _direct_nonanalysis_impact(
                profile,
                changes,
                fully_removed_evidence_ids=fully_removed_evidence_ids,
            )

        impacts[profile.artifact_id] = _merge_inherited(profile, direct, impacts)

    return ImpactPropagationReport(
        before_snapshot_id=before.snapshot_id,
        after_snapshot_id=after.snapshot_id,
        changes=changes,
        impacts=tuple(impacts[key] for key in sorted(impacts)),
        unresolved_upstream_ids=dependency_index.unresolved_upstream_ids(),
    )

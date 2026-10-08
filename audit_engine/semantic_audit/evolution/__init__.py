"""G3.2 semantic graph evolution and durable audit-memory primitives."""

from .delta import GraphDelta, NodeMutation, SemanticContextDelta, compare_snapshots
from .invalidation import (
    ArtifactInvalidation,
    ArtifactValidity,
    InvalidationReport,
    assess_transition,
)
from .memory import AuditLongTermMemory, MemoryRecord
from .service import GraphEvolutionResult, SemanticGraphEvolutionService
from .snapshots import EdgeSnapshot, GraphSnapshot, NodeSnapshot
from .topology import (
    DegreeChange,
    DegreeRecord,
    RelationCountChange,
    TopologyDelta,
    TopologySummary,
    compare_topology,
    summarize_topology,
)

__all__ = [
    'ArtifactInvalidation',
    'ArtifactValidity',
    'AuditLongTermMemory',
    'DegreeChange',
    'DegreeRecord',
    'EdgeSnapshot',
    'GraphDelta',
    'GraphEvolutionResult',
    'GraphSnapshot',
    'InvalidationReport',
    'MemoryRecord',
    'NodeMutation',
    'NodeSnapshot',
    'RelationCountChange',
    'SemanticContextDelta',
    'SemanticGraphEvolutionService',
    'TopologyDelta',
    'TopologySummary',
    'assess_transition',
    'compare_snapshots',
    'compare_topology',
    'summarize_topology',
]

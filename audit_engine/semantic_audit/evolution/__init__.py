"""G3.2 semantic graph evolution, audit memory, and incremental re-verification."""

from .delta import GraphDelta, NodeMutation, SemanticContextDelta, compare_snapshots
from .impact import (
    ArtifactDependencyProfile,
    AuditArtifactDependencyIndex,
    ChangeAtom,
    ChangeKind,
    ImpactScope,
    changes_from_delta,
    profile_analysis,
    profile_finding,
    profile_receipt,
)
from .incremental import IncrementalReverificationResult, IncrementalReverificationService
from .invalidation import (
    ArtifactInvalidation,
    ArtifactValidity,
    InvalidationReport,
    assess_transition,
)
from .memory import AuditLongTermMemory, MemoryRecord
from .memory_queries import AuditMemoryQueryService, MemoryQuery, MemoryQueryResult
from .propagation import ArtifactImpact, ImpactPropagationReport, propagate_impacts
from .reverification import (
    PriorityBand,
    ReverificationAction,
    ReverificationPlan,
    ReverificationPolicy,
    ReverificationTask,
    build_reverification_plan,
)
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
    'ArtifactDependencyProfile',
    'ArtifactImpact',
    'ArtifactInvalidation',
    'ArtifactValidity',
    'AuditArtifactDependencyIndex',
    'AuditLongTermMemory',
    'AuditMemoryQueryService',
    'ChangeAtom',
    'ChangeKind',
    'DegreeChange',
    'DegreeRecord',
    'EdgeSnapshot',
    'GraphDelta',
    'GraphEvolutionResult',
    'GraphSnapshot',
    'ImpactPropagationReport',
    'ImpactScope',
    'IncrementalReverificationResult',
    'IncrementalReverificationService',
    'InvalidationReport',
    'MemoryQuery',
    'MemoryQueryResult',
    'MemoryRecord',
    'NodeMutation',
    'NodeSnapshot',
    'PriorityBand',
    'RelationCountChange',
    'ReverificationAction',
    'ReverificationPlan',
    'ReverificationPolicy',
    'ReverificationTask',
    'SemanticContextDelta',
    'SemanticGraphEvolutionService',
    'TopologyDelta',
    'TopologySummary',
    'assess_transition',
    'build_reverification_plan',
    'changes_from_delta',
    'compare_snapshots',
    'compare_topology',
    'profile_analysis',
    'profile_finding',
    'profile_receipt',
    'propagate_impacts',
    'summarize_topology',
]

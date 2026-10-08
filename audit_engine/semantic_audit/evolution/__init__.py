"""G3.2 semantic graph evolution, audit memory, and incremental re-verification."""

from .delta import GraphDelta, NodeMutation, SemanticContextDelta, compare_snapshots
from .execution import (
    ArtifactReplacement,
    IncrementalReverificationExecutor,
    ReverificationExecutionResult,
    ReverificationReplayCatalog,
    ReverificationTaskExecution,
    TaskExecutionStatus,
)
from .execution_memory import ExecutionMemoryCommit, ReverificationExecutionMemoryRecorder
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
from .invalidation import ArtifactInvalidation, ArtifactValidity, InvalidationReport, assess_transition
from .memory import AuditLongTermMemory, MemoryRecord
from .memory_queries import AuditMemoryQueryService, MemoryQuery, MemoryQueryResult
from .propagation import ArtifactImpact, ImpactPropagationReport, propagate_impacts
from .reconciliation import (
    ArtifactReconciliation,
    ReconciliationDisposition,
    reconcile_analysis,
    reconcile_finding,
    reconcile_receipt,
)
from .replay import (
    AnalysisReplayResult,
    ObligationReplayResult,
    ReplaySelectionMode,
    ReplayStatus,
    graph_query_from_analysis,
    rebase_verification_obligation,
    replay_analysis,
)
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
    'AnalysisReplayResult', 'ArtifactDependencyProfile', 'ArtifactImpact',
    'ArtifactInvalidation', 'ArtifactReconciliation', 'ArtifactReplacement',
    'ArtifactValidity', 'AuditArtifactDependencyIndex', 'AuditLongTermMemory',
    'AuditMemoryQueryService', 'ChangeAtom', 'ChangeKind', 'DegreeChange',
    'DegreeRecord', 'EdgeSnapshot', 'ExecutionMemoryCommit', 'GraphDelta',
    'GraphEvolutionResult', 'GraphSnapshot', 'ImpactPropagationReport', 'ImpactScope',
    'IncrementalReverificationExecutor', 'IncrementalReverificationResult',
    'IncrementalReverificationService', 'InvalidationReport', 'MemoryQuery',
    'MemoryQueryResult', 'MemoryRecord', 'NodeMutation', 'NodeSnapshot',
    'ObligationReplayResult', 'PriorityBand', 'ReconciliationDisposition',
    'RelationCountChange', 'ReplaySelectionMode', 'ReplayStatus',
    'ReverificationAction', 'ReverificationExecutionMemoryRecorder',
    'ReverificationExecutionResult', 'ReverificationPlan', 'ReverificationPolicy',
    'ReverificationReplayCatalog', 'ReverificationTask', 'ReverificationTaskExecution',
    'SemanticContextDelta', 'SemanticGraphEvolutionService', 'TaskExecutionStatus',
    'TopologyDelta', 'TopologySummary', 'assess_transition', 'build_reverification_plan',
    'changes_from_delta', 'compare_snapshots', 'compare_topology',
    'graph_query_from_analysis', 'profile_analysis', 'profile_finding', 'profile_receipt',
    'propagate_impacts', 'rebase_verification_obligation', 'reconcile_analysis',
    'reconcile_finding', 'reconcile_receipt', 'replay_analysis', 'summarize_topology',
]

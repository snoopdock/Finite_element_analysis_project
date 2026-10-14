"""AE-02: Evidence-driven audit evolution and change lifecycle."""
from .snapshots import AuditSnapshot, create_snapshot
from .delta import AuditDelta, compare_snapshots
from .lifecycle import FindingLifecycleManager
from .coverage import CoverageMatrix, CoverageStatus

__all__ = [
    "AuditSnapshot","create_snapshot","AuditDelta","compare_snapshots",
    "FindingLifecycleManager","CoverageMatrix","CoverageStatus",
]

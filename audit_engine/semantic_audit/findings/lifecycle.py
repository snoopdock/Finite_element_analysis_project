
"""Explicit lifecycle transitions for audit findings."""

from __future__ import annotations

from dataclasses import replace

from .models import AuditFinding, FindingLifecycleStatus


_ALLOWED_TRANSITIONS = {
    FindingLifecycleStatus.OPEN: {
        FindingLifecycleStatus.ACKNOWLEDGED,
        FindingLifecycleStatus.RESOLVED,
        FindingLifecycleStatus.SUPPRESSED,
        FindingLifecycleStatus.STALE,
    },
    FindingLifecycleStatus.ACKNOWLEDGED: {
        FindingLifecycleStatus.RESOLVED,
        FindingLifecycleStatus.SUPPRESSED,
        FindingLifecycleStatus.STALE,
    },
    FindingLifecycleStatus.RESOLVED: {FindingLifecycleStatus.STALE},
    FindingLifecycleStatus.SUPPRESSED: {FindingLifecycleStatus.STALE},
    FindingLifecycleStatus.STALE: set(),
}


def transition_finding(
    finding: AuditFinding,
    target: FindingLifecycleStatus,
) -> AuditFinding:
    if target is finding.lifecycle_status:
        return finding
    if target not in _ALLOWED_TRANSITIONS[finding.lifecycle_status]:
        raise ValueError(
            f"Invalid finding lifecycle transition: "
            f"{finding.lifecycle_status.value} -> {target.value}"
        )
    return replace(finding, lifecycle_status=target)


def mark_stale_if_context_changed(
    finding: AuditFinding,
    *,
    graph_fingerprint: str,
    semantic_context_fingerprint: str,
) -> AuditFinding:
    if (
        finding.graph_fingerprint == graph_fingerprint
        and finding.semantic_context_fingerprint == semantic_context_fingerprint
    ):
        return finding
    if finding.lifecycle_status is FindingLifecycleStatus.STALE:
        return finding
    return replace(finding, lifecycle_status=FindingLifecycleStatus.STALE)

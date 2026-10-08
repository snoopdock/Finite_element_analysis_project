"""Task-local working memory for semantic graph auditing.

This implements the working-memory half of the audit-memory model.  Durable,
cross-project long-term memory is intentionally deferred until lifecycle,
privacy, and governance policies are specified.
"""

from __future__ import annotations

from dataclasses import dataclass

from .results import GraphAnalysisResult


@dataclass(frozen=True)
class AnalysisMemoryEntry:
    result: GraphAnalysisResult

    def is_stale_for(self, graph_fingerprint: str) -> bool:
        return self.result.graph_fingerprint != graph_fingerprint


class AuditWorkingMemory:
    """In-memory registry of traceable intermediate analysis artifacts."""

    def __init__(self) -> None:
        self._entries: dict[str, AnalysisMemoryEntry] = {}

    def record(self, result: GraphAnalysisResult) -> None:
        existing = self._entries.get(result.analysis_id)
        if existing is not None and existing.result.to_dict() != result.to_dict():
            raise ValueError(
                f"Analysis identity collision with different content: {result.analysis_id}"
            )
        self._entries[result.analysis_id] = AnalysisMemoryEntry(result=result)

    def get(
        self,
        analysis_id: str,
        *,
        current_graph_fingerprint: str | None = None,
        allow_stale: bool = False,
    ) -> GraphAnalysisResult | None:
        entry = self._entries.get(analysis_id)
        if entry is None:
            return None
        if (
            current_graph_fingerprint is not None
            and entry.is_stale_for(current_graph_fingerprint)
            and not allow_stale
        ):
            return None
        return entry.result

    def stale_analysis_ids(self, graph_fingerprint: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                analysis_id
                for analysis_id, entry in self._entries.items()
                if entry.is_stale_for(graph_fingerprint)
            )
        )

    def __len__(self) -> int:
        return len(self._entries)

"""Registry of explicitly activated high-assurance adapters."""

from __future__ import annotations

from .adapter import HighAssuranceAdapter


class HighAssuranceAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, HighAssuranceAdapter] = {}

    def register(self, adapter: HighAssuranceAdapter) -> None:
        adapter_id = adapter.descriptor.adapter_id
        if adapter_id in self._adapters:
            raise ValueError(f"High-assurance adapter already registered: {adapter_id}")
        self._adapters[adapter_id] = adapter

    def get(self, adapter_id: str) -> HighAssuranceAdapter | None:
        return self._adapters.get(adapter_id)

    def require(self, adapter_id: str) -> HighAssuranceAdapter:
        adapter = self.get(adapter_id)
        if adapter is None:
            raise KeyError(f"Unknown high-assurance adapter: {adapter_id}")
        return adapter

    def adapters(self) -> tuple[HighAssuranceAdapter, ...]:
        return tuple(self._adapters[key] for key in sorted(self._adapters))

    def __len__(self) -> int:
        return len(self._adapters)

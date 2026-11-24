"""Explicit teardown tests for RepositoryEvidenceTools backend resources."""
from __future__ import annotations

from types import SimpleNamespace

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools


def test_close_releases_an_owned_native_backend_adapter():
    class FakeAdapter:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    adapter = FakeAdapter()
    tools = RepositoryEvidenceTools.__new__(RepositoryEvidenceTools)
    tools.graph_service = SimpleNamespace(
        engine=SimpleNamespace(
            traversal_engine=SimpleNamespace(adapter=adapter),
        ),
    )

    tools.close()

    assert adapter.close_calls == 1


def test_close_is_a_noop_for_reference_or_in_process_engine():
    tools = RepositoryEvidenceTools.__new__(RepositoryEvidenceTools)
    tools.graph_service = SimpleNamespace(
        engine=SimpleNamespace(
            traversal_engine=SimpleNamespace(),
        ),
    )

    tools.close()

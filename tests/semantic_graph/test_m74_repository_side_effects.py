"""M7.4-G4 repository side-effect, snapshot, and lifecycle qualification."""
from __future__ import annotations

import hashlib
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import audit_engine.semantic_audit.ae32b.evidence_tools as evidence_tools_module
from audit_engine.semantic_audit.ae32b.evidence_tools import (
    EvidenceToolError,
    RepositoryEvidenceTools,
)
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis import TraversalDirection
from audit_engine.semantic_audit.graph.backend.adapter_traversal import NativeAdapterGraphTraversalEngine
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "semantic_audit"
    / "fixtures"
    / "ae32c_provider_interface_incident"
)
BACKENDS = ("networkx", "scipy", "igraph", "graph-tool", "snap")


def _tree_state(root: Path) -> dict[str, tuple[str, int]]:
    """Capture every regular file's bytes and mode, including additions/removals."""
    state = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        state[relative] = (hashlib.sha256(data).hexdigest(), path.stat().st_mode & 0o777)
    return state


def _copy_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "repository"
    shutil.copytree(FIXTURE, destination)
    return destination


def _selected_backend(backend: str) -> bool:
    selected = os.environ.get("AE32C_M74_BACKEND")
    if selected is not None and selected != backend:
        pytest.skip(f"workflow job targets {selected}, not {backend}")
    return True


@pytest.mark.parametrize("backend", BACKENDS)
def test_g4_repository_evidence_operations_are_byte_and_mode_read_only(tmp_path, backend):
    """Repository-backed evidence operations must not alter, add, or remove files."""
    _selected_backend(backend)
    root = _copy_fixture(tmp_path)
    before = _tree_state(root)
    tools = RepositoryEvidenceTools(root, graph_backend=backend)
    try:
        assert tools.invoke("search_repository", {
            "query": "extract", "mode": "both", "max_results": 10,
        })["status"] == "ok"
        symbols = tools.invoke("search_symbols", {
            "query": "extract", "kind": "function", "max_results": 10,
        })
        assert symbols["status"] == "ok"
        assert symbols["result"]["symbols"]

        read = tools.invoke("read_source_file", {
            "path": "main.py", "start_line": 1, "end_line": 20,
        })
        assert read["status"] == "ok"
        assert read["result"]["source_sha256"] == tools.file_hashes["main.py"]

        graph = tools.invoke("graph_neighbors", {
            "node": "symbol:pipeline.extractor::extract",
            "direction": "incoming",
            "relation_types": ["CALLS"],
            "max_depth": 1,
            "max_results": 20,
        })
        assert graph["status"] == "ok"
        assert tools.graph_runtime_report()["source_files_modified"] is False
    finally:
        tools.close()

    assert _tree_state(root) == before


@pytest.mark.parametrize("backend", BACKENDS)
def test_g4_repository_queries_are_bound_to_constructed_source_snapshot(tmp_path, backend):
    """Concurrent on-disk edits cannot rewrite the already-indexed evidence snapshot."""
    _selected_backend(backend)
    root = _copy_fixture(tmp_path)
    tools = RepositoryEvidenceTools(root, graph_backend=backend)
    original = (root / "main.py").read_bytes()
    original_hash = tools.file_hashes["main.py"]
    changed = (b"#" + original[1:]) if original else b"#"
    try:
        # Same-size mutation exercises content identity, not only size checks.
        (root / "main.py").write_bytes(changed)
        assert len(changed) == len(original)

        def read_snapshot():
            return tools.invoke("read_source_file", {
                "path": "main.py", "start_line": 1, "end_line": 20,
            })

        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _index: read_snapshot(), range(8)))

        assert all(item["status"] == "ok" for item in responses)
        assert all(item["result"]["source_sha256"] == original_hash for item in responses)
        assert all(item["result"]["content"] == responses[0]["result"]["content"] for item in responses)
        assert tools.graph_fingerprint
    finally:
        (root / "main.py").write_bytes(original)
        tools.close()

    assert (root / "main.py").read_bytes() == original


def test_g4_snap_close_serializes_against_a_pending_query_and_query_fails_closed():
    """A query waiting on the worker lock must not use a worker after close."""
    if os.environ.get("AE32C_M74_BACKEND") not in (None, "snap"):
        pytest.skip("workflow job does not target SNAP")
    if not os.environ.get("AE32C_SNAP_WORKER_IMAGE"):
        pytest.skip("SNAP isolated worker is not configured")

    graph = SemanticGraph(nodes=[SemanticNode("A", "Module", {}, {})])
    service = SemanticGraphAnalysisService(graph, traversal_backend="snap")
    engine = service.engine.traversal_engine
    assert isinstance(engine, NativeAdapterGraphTraversalEngine)
    adapter = engine.adapter
    started = threading.Event()
    outcome = {}

    def query():
        started.set()
        try:
            engine.walk("A", direction=TraversalDirection.OUTGOING, max_depth=1)
            outcome["status"] = "success"
        except Exception as exc:  # the public query boundary must fail closed
            outcome["status"] = "error"
            outcome["error"] = str(exc)

    try:
        # RLock permits close() on this thread while the query thread is queued.
        with adapter._request_lock:
            worker = threading.Thread(target=query, daemon=True)
            worker.start()
            assert started.wait(timeout=2)
            adapter.close()
        worker.join(timeout=10)
        assert not worker.is_alive()
        assert outcome.get("status") == "error"
        assert "snap_worker_process_not_running" in outcome.get("error", "")
        assert engine.runtime_report()["backend_execution"]["queries_succeeded"] == 0
    finally:
        adapter.close()


def test_g4_same_size_edit_during_snapshot_loading_is_rejected(tmp_path, monkeypatch):
    """A file changed after its first read must fail the second manifest check."""
    root = _copy_fixture(tmp_path)
    original_reader = evidence_tools_module._read_snapshot_file
    mutation_applied = False

    def mutate_after_first_read(repository_root, relative_path, expected_size):
        nonlocal mutation_applied
        data = original_reader(repository_root, relative_path, expected_size)
        if relative_path == "main.py" and not mutation_applied:
            path = repository_root / relative_path
            changed = (b"#" + data[1:]) if data else b"#"
            assert len(changed) == len(data)
            path.write_bytes(changed)
            mutation_applied = True
        return data

    monkeypatch.setattr(
        evidence_tools_module, "_read_snapshot_file", mutate_after_first_read,
    )
    with pytest.raises(EvidenceToolError) as captured:
        RepositoryEvidenceTools(root, graph_backend="reference")
    assert captured.value.code == "source_changed_during_index"
    assert mutation_applied is True

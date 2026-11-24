"""M7.4-G4 repository side-effect, snapshot, and lifecycle qualification."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import stat
import threading
import time
from types import SimpleNamespace
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


def _tree_state(root: Path) -> dict[str, tuple[str, int, str | None]]:
    """Capture entry types, permission modes, file bytes, and symlink targets.

    Ownership, timestamps, ACLs, xattrs, hard-link identity, and external
    filesystem effects are intentionally outside this helper's coverage.
    """
    state: dict[str, tuple[str, int, str | None]] = {}
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames.sort()
        filenames.sort()
        symlink_directories = []
        for name in [*dirnames, *filenames]:
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                kind, value = "symlink", os.readlink(path)
                if name in dirnames:
                    symlink_directories.append(name)
            elif stat.S_ISDIR(info.st_mode):
                kind, value = "directory", None
            elif stat.S_ISREG(info.st_mode):
                kind, value = "regular_file", hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                kind, value = "other", str(info.st_rdev)
            state[relative] = (kind, mode, value)
        # Do not descend through directory symlinks.
        if symlink_directories:
            dirnames[:] = [name for name in dirnames if name not in symlink_directories]
    return state


def _copy_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "repository"
    shutil.copytree(FIXTURE, destination)
    return destination


def test_snapshot_identity_prefers_windows_birthtime_when_available(monkeypatch):
    info = SimpleNamespace(
        st_dev=1, st_ino=2, st_mode=0o100644, st_size=3,
        st_mtime=4.0, st_mtime_ns=4_000_000_000,
        st_ctime=5.0, st_ctime_ns=5_000_000_000,
        st_birthtime_ns=6_000_000_000,
    )
    monkeypatch.setattr(evidence_tools_module.os, "name", "nt")
    assert evidence_tools_module._snapshot_stat_identity(info)[6] == 6_000_000_000

    del info.st_birthtime_ns
    assert evidence_tools_module._snapshot_stat_identity(info)[6] == 5_000_000_000


@pytest.mark.skipif(os.name != "nt", reason="Windows junction/reparse-point behavior")
def test_snapshot_reader_rejects_windows_directory_junction(tmp_path):
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    payload = b"outside repository source\n"
    (outside / "secret.py").write_bytes(payload)
    junction = root / "junction"
    result = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"Windows junction creation unavailable: {result.stderr.strip()}")
    try:
        with pytest.raises(OSError, match="reparse-point manifest path"):
            evidence_tools_module._read_snapshot_file_with_identity(
                root.resolve(), "junction/secret.py", len(payload),
            )
    finally:
        os.rmdir(junction)


def test_g4_tree_state_records_directory_modes_and_symlink_targets(tmp_path):
    root = tmp_path / "tree"
    nested = root / "nested"
    nested.mkdir(parents=True)
    target = root / "target.txt"
    target.write_text("target", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to("target.txt")
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks are unavailable on this filesystem: {exc}")

    state = _tree_state(root)
    assert state["nested"][0] == "directory"
    assert state["target.txt"][0] == "regular_file"
    assert state["link.txt"] == ("symlink", state["link.txt"][1], "target.txt")

    link.unlink()
    link.symlink_to("missing.txt")
    assert _tree_state(root) != state


@pytest.fixture(scope="module", autouse=True)
def _validate_backend_target():
    selected = os.environ.get("AE32C_M74_BACKEND")
    if selected is not None and selected not in BACKENDS:
        pytest.fail(f"unknown AE32C_M74_BACKEND target: {selected!r}")


def _selected_backend(backend: str) -> bool:
    selected = os.environ.get("AE32C_M74_BACKEND")
    if selected is not None and selected not in BACKENDS:
        pytest.fail(f"unknown AE32C_M74_BACKEND target: {selected!r}")
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
def test_g4_repository_queries_use_constructed_snapshot_after_external_edit(tmp_path, backend):
    """Concurrent reads remain bound to the constructed snapshot after an external edit."""
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
    query_started = threading.Event()
    query_waiting_for_lock = threading.Event()
    outcome = {}
    underlying_lock = adapter._request_lock

    class ObservedRLock:
        """Expose the query thread's actual lock-acquisition attempt."""

        def acquire(self, *args, **kwargs):
            if query_started.is_set():
                query_waiting_for_lock.set()
            return underlying_lock.acquire(*args, **kwargs)

        def release(self):
            return underlying_lock.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.release()
            return False

    adapter._request_lock = ObservedRLock()

    def query():
        query_started.set()
        try:
            engine.walk("A", direction=TraversalDirection.OUTGOING, max_depth=1)
            outcome["status"] = "success"
        except Exception as exc:  # the public query boundary must fail closed
            outcome["status"] = "error"
            outcome["error"] = str(exc)

    try:
        # Hold the underlying RLock, then wait until the query really attempts
        # to acquire it. Thread-start notification alone is not sufficient.
        with adapter._request_lock:
            worker = threading.Thread(target=query, daemon=True)
            worker.start()
            assert query_started.wait(timeout=2)
            assert query_waiting_for_lock.wait(timeout=2)
            adapter.close()
        worker.join(timeout=10)
        assert not worker.is_alive()
        assert outcome.get("status") == "error"
        assert "snap_worker_process_not_running" in outcome.get("error", "")
        assert engine.runtime_report()["backend_execution"]["queries_succeeded"] == 0
    finally:
        adapter.close()


@pytest.mark.parametrize("backend", BACKENDS)
def test_g4_source_edit_during_active_read_query_preserves_pinned_snapshot(
    tmp_path, backend, monkeypatch,
):
    """A same-size disk edit during an in-flight read cannot rewrite its snapshot."""
    _selected_backend(backend)
    root = _copy_fixture(tmp_path)
    tools = RepositoryEvidenceTools(root, graph_backend=backend)
    source_path = root / "main.py"
    original = source_path.read_bytes()
    changed = (b"#" + original[1:]) if original else b"#"
    assert len(changed) == len(original)
    expected_hash = tools.file_hashes["main.py"]
    entered_source_read = threading.Event()
    release_source_read = threading.Event()
    response_holder = {}
    original_source_lines = evidence_tools_module._source_lines

    def pause_inside_active_query(text):
        if (
            threading.current_thread().name == "g4-active-source-read"
            and text == tools.contents["main.py"]
        ):
            entered_source_read.set()
            if not release_source_read.wait(timeout=10):
                raise TimeoutError("test did not release the in-flight source read")
        return original_source_lines(text)

    monkeypatch.setattr(evidence_tools_module, "_source_lines", pause_inside_active_query)

    def run_query():
        response_holder["response"] = tools.invoke("read_source_file", {
            "path": "main.py", "start_line": 1, "end_line": 20,
        })

    worker = threading.Thread(target=run_query, name="g4-active-source-read", daemon=True)
    try:
        worker.start()
        assert entered_source_read.wait(timeout=10), "read query did not reach its in-flight pause"
        source_path.write_bytes(changed)
        release_source_read.set()
        worker.join(timeout=10)
        assert not worker.is_alive(), "read query did not finish after release"
        response = response_holder["response"]
        assert response["status"] == "ok"
        assert response["result"]["source_sha256"] == expected_hash
        assert response["result"]["content"] == tools.invoke("read_source_file", {
            "path": "main.py", "start_line": 1, "end_line": 20,
        })["result"]["content"]
        assert source_path.read_bytes() == changed
    finally:
        release_source_read.set()
        worker.join(timeout=10)
        source_path.write_bytes(original)
        tools.close()


def test_g4_change_restore_between_snapshot_passes_is_detected_by_file_identity(
    tmp_path, monkeypatch,
):
    """Descriptor identity catches an ordinary ABA edit despite restored bytes."""
    root = _copy_fixture(tmp_path)
    source_path = root / "main.py"
    original = source_path.read_bytes()
    changed = (b"#" + original[1:]) if original else b"#"
    assert len(changed) == len(original)
    original_reader = evidence_tools_module._read_snapshot_file_with_identity
    main_reads = 0

    def change_then_restore(repository_root, relative_path, expected_size):
        nonlocal main_reads
        if relative_path != "main.py":
            return original_reader(repository_root, relative_path, expected_size)
        main_reads += 1
        if main_reads == 1:
            data, identity = original_reader(repository_root, relative_path, expected_size)
            source_path.write_bytes(changed)
            time.sleep(0.02)
            return data, identity
        if main_reads == 2:
            assert source_path.read_bytes() == changed
            source_path.write_bytes(original)
            time.sleep(0.02)
        return original_reader(repository_root, relative_path, expected_size)

    monkeypatch.setattr(
        evidence_tools_module, "_read_snapshot_file_with_identity", change_then_restore,
    )
    try:
        with pytest.raises(EvidenceToolError) as captured:
            RepositoryEvidenceTools(root, graph_backend="reference")
        assert captured.value.code == "source_changed_during_index"
        assert main_reads == 2
        assert source_path.read_bytes() == original
    finally:
        source_path.write_bytes(original)


def test_g4_same_size_edit_during_snapshot_loading_is_rejected(tmp_path, monkeypatch):
    """A file changed after its first read must fail the second manifest check."""
    root = _copy_fixture(tmp_path)
    original_reader = evidence_tools_module._read_snapshot_file_with_identity
    mutation_applied = False

    def mutate_after_first_read(repository_root, relative_path, expected_size):
        nonlocal mutation_applied
        data, identity = original_reader(repository_root, relative_path, expected_size)
        if relative_path == "main.py" and not mutation_applied:
            path = repository_root / relative_path
            changed = (b"#" + data[1:]) if data else b"#"
            assert len(changed) == len(data)
            path.write_bytes(changed)
            mutation_applied = True
        return data, identity

    monkeypatch.setattr(
        evidence_tools_module, "_read_snapshot_file_with_identity", mutate_after_first_read,
    )
    with pytest.raises(EvidenceToolError) as captured:
        RepositoryEvidenceTools(root, graph_backend="reference")
    assert captured.value.code == "source_changed_during_index"
    assert mutation_applied is True

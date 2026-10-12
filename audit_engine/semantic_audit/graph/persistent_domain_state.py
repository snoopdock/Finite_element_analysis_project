"""GE-02: durable, versioned GE-01 graph projections with review-only deltas.

Reuses the established SemanticGraphEvolutionService instead of creating another
backend/delta model. SHA-256 provides tamper detection, NOT authentication.
No scientific, SAT, or approval authority is inferred from a persisted graph.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution.service import SemanticGraphEvolutionService
from audit_engine.semantic_audit.graph.domain_integration import (
    GraphDomainError, GraphDomainView, SCHEMA as VIEW_SCHEMA,
    _read_json as read_ge01_json, from_scientific_graph, verify_snapshot,
)

STORE_SCHEMA = "ge02-state-head/v1"
COMMIT_SCHEMA = "ge02-graph-state-commit/v1"
TRANSITION_SCHEMA = "ge02-graph-transition/v1"
MAX_FILE_BYTES = 16_000_000
MAX_HISTORY = 10000
MAX_REVIEW_NODES = 50000
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
# Edges that indicate a structural *review* dependency from source to target.
# Scientific relations do not imply derivation or a causal direction.
REVIEW_RELATIONS = frozenset({"CITES_SOURCE", "HAS_CONCEPT", "SUBCONCEPT_OF", "RELATION_ASSERTED_BY", "CITES_STRUCTURALLY"})
DOMAINS = frozenset({"scientific_knowledge", "generated_text_audit", "combined_read_only"})


class GraphStoreError(ValueError):
    """Graph-store integrity, concurrency or safety boundary violation."""


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise GraphStoreError("Noncanonical or nonfinite graph-state JSON") from exc


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GraphStoreError("Duplicate JSON key")
        result[key] = value
    return result


def parse(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=lambda n: (_ for _ in ()).throw(GraphStoreError("Nonfinite number")))
    except (UnicodeError, ValueError) as exc:
        raise GraphStoreError("Corrupted graph-state JSON") from exc


def _safe_directory(directory: Path, *, create=False):
    directory = Path(os.path.abspath(directory))
    if any(parent.is_symlink() for parent in (directory, *directory.parents)):
        raise GraphStoreError("Symlink directory is forbidden")
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise GraphStoreError("Missing graph-state directory")
    return directory


def _read_file(path: Path, *, max_bytes=MAX_FILE_BYTES) -> bytes:
    if path.is_symlink():
        raise GraphStoreError("Symlink graph-state object is forbidden")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except OSError as exc:
        raise GraphStoreError(f"Cannot open graph-state object: {path.name}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise GraphStoreError("Unexpected type or oversized graph-state object")
        raw = os.read(fd, max_bytes + 1)
        if len(raw) != info.st_size:
            raise GraphStoreError("Graph-state object changed during read")
        return raw
    finally:
        os.close(fd)


def _sync(directory: Path):
    if os.name == "posix":
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _immutable(path: Path, raw: bytes):
    if len(raw) > MAX_FILE_BYTES:
        raise GraphStoreError("Graph-state object exceeds publication size limit")
    _safe_directory(path.parent, create=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        if _read_file(path) != raw:
            raise GraphStoreError("Existing content-addressed object is corrupted")
        return
    except OSError as exc:
        raise GraphStoreError("Graph-state object cannot be published") from exc
    try:
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        # Fail closed: damaged file is left for explicit operator remediation.
        raise
    _sync(path.parent)


def _replace_head(path: Path, raw: bytes):
    temp = path.parent / (".head-" + os.urandom(12).hex() + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        _sync(path.parent)
    finally:
        if temp.exists():
            temp.unlink()


def _valid_digest(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def _strict_view(snapshot: Any) -> GraphDomainView:
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "schema_version", "domain", "input_sha256", "graph_fingerprint", "graph",
        "authoritative_mutation_permitted", "scientific_truth_established", "snapshot_sha256"
    }:
        raise GraphStoreError("Unexpected GE-01 snapshot envelope")
    if snapshot["schema_version"] != VIEW_SCHEMA or snapshot["domain"] not in DOMAINS:
        raise GraphStoreError("Unsupported graph snapshot schema/domain")
    if snapshot["authoritative_mutation_permitted"] is not False or snapshot["scientific_truth_established"] is not False:
        raise GraphStoreError("Graph-state snapshot claims forbidden authority")
    if not _valid_digest(snapshot["input_sha256"]) or not _valid_digest(snapshot["snapshot_sha256"]):
        raise GraphStoreError("Invalid GE-01 input/snapshot digest")
    g = snapshot["graph"]
    if not isinstance(g, dict) or set(g) != {"nodes", "edges"} or not isinstance(g["nodes"], list) or not isinstance(g["edges"], list):
        raise GraphStoreError("Invalid graph data")
    if len(g["nodes"]) + len(g["edges"]) > MAX_REVIEW_NODES:
        raise GraphStoreError("Graph state exceeds resource budget")
    graph = SemanticGraph()
    for item in g["nodes"]:
        if not isinstance(item, dict) or set(item) != {"id", "type", "attributes", "metadata"}:
            raise GraphStoreError("Unexpected graph node")
        if not isinstance(item["attributes"], dict) or not isinstance(item["metadata"], dict):
            raise GraphStoreError("Invalid node attributes")
        graph.add_node(SemanticNode(item["id"], item["type"], item["attributes"], item["metadata"]))
    for item in g["edges"]:
        if not isinstance(item, dict) or set(item) != {"source", "target", "relation", "attributes", "metadata"}:
            raise GraphStoreError("Unexpected graph edge")
        if not isinstance(item["attributes"], dict) or not isinstance(item["metadata"], dict):
            raise GraphStoreError("Invalid edge attributes")
        graph.add_edge(SemanticEdge(item["source"], item["target"], item["relation"], item["attributes"], item["metadata"]))
    view = GraphDomainView(graph, snapshot["domain"], snapshot["input_sha256"])
    try:
        verify_snapshot(view, snapshot)
    except (GraphDomainError, ValueError) as exc:
        raise GraphStoreError("Persisted graph failed independent structural reconstruction") from exc
    return view


def _dependency_candidates(before: SemanticGraph, after: SemanticGraph, delta) -> dict:
    """Bounded reverse traversal. A result means REVIEW, never formal entailment."""
    seeds: set[str] = set()
    seeds.update(n.node_id for n in delta.added_nodes)
    seeds.update(n.node_id for n in delta.removed_nodes)
    seeds.update(m.node_id for m in delta.modified_nodes)
    for e in (*delta.added_edges, *delta.removed_edges):
        seeds.update((e.source_id, e.target_id))
    reverse: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for g in (before, after):
        for e in g.edges:
            if e.relation_type in REVIEW_RELATIONS:
                reverse[e.target_id].add((e.source_id, e.relation_type))
    discovered: dict[str, tuple[int, str]] = {}
    frontier = deque((s, 0, "direct_change") for s in sorted(seeds))
    while frontier:
        node, depth, reason = frontier.popleft()
        if node in discovered:
            continue
        if len(discovered) >= MAX_REVIEW_NODES:
            raise GraphStoreError("Impact propagation budget exceeded")
        discovered[node] = (depth, reason)
        for upstream, relation in sorted(reverse.get(node, set())):
            if upstream not in discovered:
                frontier.append((upstream, depth + 1, "reverse:" + relation))
    return {
        "status": "review_candidates_only",
        "scientific_truth_established": False,
        "automatic_approval_permitted": False,
        "dependency_relations": sorted(REVIEW_RELATIONS),
        "changed_seed_count": len(seeds),
        "review_candidates": [{"node_id": n, "distance": d, "reason": why}
                              for n, (d, why) in sorted(discovered.items())],
    }


def _transition(before: GraphDomainView | None, after: GraphDomainView) -> dict | None:
    if before is None:
        return None
    if before.domain != after.domain:
        raise GraphStoreError("Cross-domain graph state update forbidden")
    result = SemanticGraphEvolutionService().compare(before_graph=before.graph, after_graph=after.graph)
    return {
        "schema_version": TRANSITION_SCHEMA,
        "before_graph_fingerprint": before.fingerprint,
        "after_graph_fingerprint": after.fingerprint,
        "graph_delta": result.graph_delta.to_dict(),
        "topology_delta": result.topology_delta.to_dict(),
        "impact": _dependency_candidates(before.graph, after.graph, result.graph_delta),
    }


class PersistentDomainGraphStore:
    """Immutable objects and commits; atomic HEAD and optimistic concurrency.

    Disk is durable *in the filesystem*. To survive GitHub-hosted runner disposal,
    explicitly commit this store to a persistent branch or another storage backend.
    """

    def __init__(self, root: str | Path):
        self.root = Path(os.path.abspath(root))

    @contextmanager
    def _lock(self):
        _safe_directory(self.root, create=True)
        path = self.root / ".publication.lock"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError as exc:
            raise GraphStoreError("Publication lock exists; inspect stale lock manually") from exc
        try:
            with os.fdopen(fd, "w") as f:
                f.write("GE-02 exclusive publication lock\n")
                f.flush()
                os.fsync(f.fileno())
            yield
        finally:
            path.unlink()

    def _cas_read(self, kind: str, digest: str) -> dict:
        if kind not in ("objects", "commits", "transitions") or not _valid_digest(digest):
            raise GraphStoreError("Invalid content address")
        path = self.root / kind / (digest + ".json")
        _safe_directory(path.parent)
        raw = _read_file(path)
        if sha(raw) != digest or canonical(parse(raw)) != raw:
            raise GraphStoreError("Content-addressed object is corrupted")
        return parse(raw)

    def _cas_write(self, kind: str, payload: dict) -> str:
        raw = canonical(payload)
        digest = sha(raw)
        _immutable(self.root / kind / (digest + ".json"), raw)
        return digest

    def _head_receipt(self) -> str | None:
        _safe_directory(self.root)
        f = self.root / "HEAD.json"
        if not f.exists() and not f.is_symlink():
            return None
        head = parse(_read_file(f, max_bytes=1000))
        if not isinstance(head, dict) or set(head) != {"schema_version", "receipt_sha256", "head_sha256"}:
            raise GraphStoreError("Corrupted graph HEAD")
        digest = head.get("head_sha256")
        if head.get("schema_version") != STORE_SCHEMA or not _valid_digest(digest) or not _valid_digest(head["receipt_sha256"]):
            raise GraphStoreError("Invalid graph HEAD schema")
        if sha(canonical({k:v for k,v in head.items() if k != "head_sha256"})) != digest:
            raise GraphStoreError("Graph HEAD checksum mismatch")
        return head["receipt_sha256"]

    def verify(self) -> dict:
        """Verify reachable commit history, snapshot reconstruction and deltas."""
        _safe_directory(self.root)
        head = self._head_receipt()
        if head is None:
            return {"status": "empty", "head": None, "generation": 0, "domain": None}
        visited = set()
        receipt_hash = head
        expected_generation = None
        domain = None
        while receipt_hash is not None:
            if receipt_hash in visited or len(visited) >= MAX_HISTORY:
                raise GraphStoreError("Cycle/oversized graph history")
            visited.add(receipt_hash)
            receipt = self._cas_read("commits", receipt_hash)
            if not isinstance(receipt, dict) or set(receipt) != {
                "schema_version", "generation", "parent_receipt_sha256", "snapshot_object_sha256",
                "transition_object_sha256", "domain", "input_sha256", "graph_fingerprint"
            } or receipt["schema_version"] != COMMIT_SCHEMA:
                raise GraphStoreError("Corrupted graph receipt contract")
            gen = receipt["generation"]
            if type(gen) is not int or gen < 1 or (expected_generation is not None and gen != expected_generation):
                raise GraphStoreError("Nonmonotone graph history")
            if domain is None:
                domain = receipt["domain"]
            if domain != receipt["domain"]:
                raise GraphStoreError("Cross-domain graph history")
            snap = self._cas_read("objects", receipt["snapshot_object_sha256"])
            view = _strict_view(snap)
            if (view.domain != domain or view.fingerprint != receipt["graph_fingerprint"] or
                    view.input_sha256 != receipt["input_sha256"]):
                raise GraphStoreError("Graph receipt and snapshot mismatch")
            prev = receipt["parent_receipt_sha256"]
            trans = receipt["transition_object_sha256"]
            if gen == 1:
                if prev is not None or trans is not None:
                    raise GraphStoreError("Initial graph commit cannot claim predecessor")
            else:
                if not _valid_digest(prev) or not _valid_digest(trans):
                    raise GraphStoreError("Graph history missing predecessor or transition")
                t = self._cas_read("transitions", trans)
                old_receipt = self._cas_read("commits", prev)
                old_view = _strict_view(self._cas_read("objects", old_receipt["snapshot_object_sha256"]))
                if t != _transition(old_view, view):
                    raise GraphStoreError("Incremental transition does not reproduce")
            if receipt_hash == head:
                top_generation = gen
                top_view = view
            expected_generation = gen - 1
            receipt_hash = prev
        return {"status": "verified", "head": head, "generation": top_generation,
                "domain": domain, "snapshot_sha256": top_view.snapshot()["snapshot_sha256"],
                "graph_fingerprint": top_view.fingerprint, "commits_verified": len(visited)}

    def current_view(self) -> GraphDomainView | None:
        state = self.verify()
        if state["status"] == "empty":
            return None
        receipt = self._cas_read("commits", state["head"])
        return _strict_view(self._cas_read("objects", receipt["snapshot_object_sha256"]))

    def publish(self, view: GraphDomainView, *, expected_head: str | None | object = "auto") -> dict:
        """Publish a GE-01 view (not arbitrary JSON), with expected-head CAS."""
        if not isinstance(view, GraphDomainView):
            raise GraphStoreError("Publication requires a GE-01 domain view")
        snap = view.snapshot()
        _strict_view(snap)
        with self._lock():
            state = self.verify()
            current = state["head"]
            if expected_head != "auto" and expected_head != current:
                raise GraphStoreError("Stale graph-state expected HEAD")
            previous = self.current_view() if current else None
            if previous is not None and previous.domain != view.domain:
                raise GraphStoreError("Cross-domain HEAD update")
            if previous is not None and previous.snapshot() == snap:
                return {**state, "changed": False, "transition": None}
            trans = _transition(previous, view)
            transition_hash = self._cas_write("transitions", trans) if trans is not None else None
            object_hash = self._cas_write("objects", snap)
            gen = state["generation"] + 1
            receipt = {
                "schema_version": COMMIT_SCHEMA, "generation": gen,
                "parent_receipt_sha256": current, "snapshot_object_sha256": object_hash,
                "transition_object_sha256": transition_hash, "domain": view.domain,
                "input_sha256": view.input_sha256, "graph_fingerprint": view.fingerprint,
            }
            receipt_hash = self._cas_write("commits", receipt)
            new_head = {"schema_version": STORE_SCHEMA, "receipt_sha256": receipt_hash}
            new_head["head_sha256"] = sha(canonical(new_head))
            _replace_head(self.root / "HEAD.json", canonical(new_head))
            return {**self.verify(), "changed": True, "transition": trans}


def _input_path(repo: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not relative or not relative.endswith(".json"):
        raise GraphStoreError("Input must be a repository-relative JSON path")
    result = repo / path
    if repo not in result.resolve(strict=True).parents or result.is_symlink() or any(x.is_symlink() for x in result.parents):
        raise GraphStoreError("Input cannot leave or symlink through repository")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="GE-02 durable graph snapshot CLI")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--knowledge-graph", help="Repository-relative GE-01 scientific JSON input")
    parser.add_argument("--store", default=".graph-state/scientific", help="Repository-relative graph store")
    parser.add_argument("--command", choices=("capture", "verify"), default="capture")
    parser.add_argument("--expected-head", default="auto")
    parser.add_argument("--report", help="Write result to new report file outside repository")
    args = parser.parse_args(argv)
    repo = Path(args.repository).resolve(strict=True)
    if not repo.is_dir():
        raise GraphStoreError("Repository root is not a directory")
    store_arg = Path(args.store)
    if store_arg.is_absolute() or ".." in store_arg.parts or store_arg.parts[:1] != (".graph-state",):
        raise GraphStoreError("Graph store must live beneath .graph-state in target repository")
    store = PersistentDomainGraphStore(repo / store_arg)
    if args.command == "capture":
        if not args.knowledge_graph:
            raise GraphStoreError("Capture requires --knowledge-graph")
        view = from_scientific_graph(read_ge01_json(_input_path(repo, args.knowledge_graph)))
        expected = None if args.expected_head == "none" else args.expected_head
        result = store.publish(view, expected_head=expected)
    else:
        result = store.verify()
    output = canonical(result)
    if args.report:
        report = Path(args.report).absolute()
        if repo == report or repo in report.parents or report.exists() or report.is_symlink() or any(p.is_symlink() for p in report.parents):
            raise GraphStoreError("Unsafe or existing report output")
        _safe_directory(report.parent)
        _immutable(report, output)
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GraphStoreError, GraphDomainError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"GE-02 graph state rejected: {exc}", file=sys.stderr)
        sys.exit(2)

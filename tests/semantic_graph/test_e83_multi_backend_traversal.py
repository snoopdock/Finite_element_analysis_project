"""E.8.3: every registered native graph adapter can serve the AE-32B query path.

Fake native modules exercise adapter contracts when optional binary libraries
are unavailable. These tests do not claim binary compatibility; real native
smoke checks remain conditional on the actual distribution being installed.
"""
from __future__ import annotations

import importlib.machinery
import sys
import types

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis import GraphTraversalEngine
from audit_engine.semantic_audit.graph.backend.adapter_traversal import (
    NativeAdapterGraphTraversalEngine, NativeAdapterProjectionError,
)
from audit_engine.semantic_audit.graph.backend.optional_backend_support import BackendUnavailableError
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService


def graph_fixture():
    graph = SemanticGraph()
    for name in ("A", "B", "C", "D"):
        graph.add_node(SemanticNode(
            name, "PythonModule",
            {"path": f"{name.lower()}.py", "tags": [name]},
            {"source_sha256": f"hash-{name}"},
        ))
    graph.add_edge(SemanticEdge("A", "B", "IMPORTS", {"line": 2}, {"path": "a.py"}))
    graph.add_edge(SemanticEdge("A", "B", "DEPENDS_ON", {"line": 3}, {"path": "a.py"}))
    graph.add_edge(SemanticEdge("B", "C", "IMPORTS", {"line": 4}, {"path": "b.py"}))
    graph.add_edge(SemanticEdge("C", "C", "SELF", {}, {"path": "c.py"}))
    graph.add_edge(SemanticEdge("D", "A", "IMPORTS", {"line": 9}, {"path": "d.py"}))
    return graph


class _Vertex:
    def __init__(self, seq, index):
        self._seq, self.index = seq, index

    def __getitem__(self, key):
        return self._seq.attrs[key][self.index]


class _VertexSeq:
    def __init__(self):
        self.attrs, self.count = {}, 0

    def __setitem__(self, key, values):
        self.attrs[key] = list(values)

    def __iter__(self):
        return iter([_Vertex(self, i) for i in range(self.count)])

    def __getitem__(self, index):
        return _Vertex(self, index)


class _Edge:
    def __init__(self, seq, index, source, target):
        self._seq, self.index = seq, index
        self.source, self.target = source, target

    def __getitem__(self, key):
        return self._seq.attrs[key][self.index]


class _EdgeSeq:
    def __init__(self):
        self.attrs, self.pairs = {}, []

    def __setitem__(self, key, values):
        self.attrs[key] = list(values)

    def __iter__(self):
        return iter([
            _Edge(self, i, source, target)
            for i, (source, target) in enumerate(self.pairs)
        ])


class _FakeIGraph:
    def __init__(self, directed=True):
        assert directed is True
        self.vs, self.es = _VertexSeq(), _EdgeSeq()

    def add_vertices(self, count):
        self.vs.count += count

    def add_edges(self, pairs):
        self.es.pairs.extend(tuple(pair) for pair in pairs)


class _FakeProperty(dict):
    @staticmethod
    def _key(value):
        if hasattr(value, "index"):
            return value.index
        if hasattr(value, "source") and callable(value.source):
            return (value.source(), value.target())
        return int(value)

    def __getitem__(self, key):
        return super().__getitem__(self._key(key))

    def __setitem__(self, key, value):
        super().__setitem__(self._key(key), value)


class _FakeGraphToolEdge:
    def __init__(self, index, source, target):
        self.index, self._source, self._target = index, source, target

    def source(self):
        return self._source

    def target(self):
        return self._target


class _FakeGraphTool:
    def __init__(self, directed=True):
        assert directed is True
        self.vertex_properties, self.edge_properties = {}, {}
        self._vertices, self._edges = [], []

    def add_vertex(self, count):
        self._vertices.extend(range(len(self._vertices), len(self._vertices) + count))

    def vertex(self, index):
        return index

    def vertices(self):
        return iter(self._vertices)

    def edges(self):
        return iter(self._edges)

    def new_vertex_property(self, kind):
        assert kind in {"string", "object"}
        return _FakeProperty()

    def new_edge_property(self, kind):
        assert kind in {"string", "object", "int64_t"}
        return _FakeProperty()

    def add_edge(self, source, target):
        edge = _FakeGraphToolEdge(len(self._edges), source, target)
        self._edges.append(edge)
        return edge


class _SnapNode:
    def __init__(self, node_id):
        self._id = node_id

    def GetId(self):
        return self._id


class _SnapEdge:
    def __init__(self, edge_id, source, target):
        self._id, self._source, self._target = edge_id, source, target

    def GetId(self):
        return self._id

    def GetSrcNId(self):
        return self._source

    def GetDstNId(self):
        return self._target


class _FakeTNEANet:
    def __init__(self):
        self.nodes, self.edges = [], []
        self.node_attrs, self.edge_attrs = {}, {}
        self.node_values, self.edge_values = {}, {}

    @classmethod
    def New(cls):
        return cls()

    def AddStrAttrN(self, name):
        self.node_attrs[name] = "str"

    def AddStrAttrE(self, name):
        self.edge_attrs[name] = "str"

    def AddIntAttrE(self, name):
        self.edge_attrs[name] = "int"

    def AddNode(self, node_id):
        self.nodes.append(node_id)

    def AddEdge(self, source, target):
        edge_id = len(self.edges)
        self.edges.append((source, target))
        return edge_id

    def AddStrAttrDatN(self, node_id, value, name):
        self.node_values[(node_id, name)] = value

    def AddStrAttrDatE(self, edge_id, value, name):
        self.edge_values[(edge_id, name)] = value

    def AddIntAttrDatE(self, edge_id, value, name):
        self.edge_values[(edge_id, name)] = value

    def Nodes(self):
        return iter([_SnapNode(node_id) for node_id in self.nodes])

    def Edges(self):
        return iter([
            _SnapEdge(i, source, target)
            for i, (source, target) in enumerate(self.edges)
        ])

    def GetStrAttrDatN(self, node_id, name):
        return self.node_values[(node_id, name)]

    def GetStrAttrDatE(self, edge_id, name):
        return self.edge_values[(edge_id, name)]

    def GetIntAttrDatE(self, edge_id, name):
        return self.edge_values[(edge_id, name)]


def install_fake(monkeypatch, backend):
    module_name = {"igraph": "igraph", "graph-tool": "graph_tool", "snap": "snap"}[backend]
    module = types.ModuleType(module_name)
    module.__spec__ = importlib.machinery.ModuleSpec(module_name, loader=None)
    if backend == "igraph":
        module.Graph = _FakeIGraph
    elif backend == "graph-tool":
        module.Graph = _FakeGraphTool
    else:
        module.TNEANet = _FakeTNEANet
    monkeypatch.setitem(sys.modules, module_name, module)


def _query_result(graph, backend):
    service = SemanticGraphAnalysisService(
        graph, traversal_backend=backend, verify_backend_parity=True,
    )
    query = GraphQuery(
        "e83-backend-parity",
        QueryType.DEPENDENCY,
        ["A"],
        {"direction": "outgoing", "relation_types": ["IMPORTS", "DEPENDS_ON"], "max_depth": 3},
    )
    result = service.analyze(query)
    return result, service.engine.traversal_engine.runtime_report()


def test_scipy_backend_uses_csr_and_preserves_parallel_edge_occurrences():
    graph = graph_fixture()
    result, runtime = _query_result(graph, "scipy")
    reference = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(
        GraphQuery(
            "e83-backend-parity", QueryType.DEPENDENCY, ["A"],
            {"direction": "outgoing", "relation_types": ["IMPORTS", "DEPENDS_ON"], "max_depth": 3},
        )
    )
    assert result.discovered_entities == reference.discovered_entities == ("B", "C")
    assert result.observations == reference.observations
    assert result.evidence == reference.evidence
    assert runtime["active_computation_backend"] == "scipy"
    assert runtime["backend_parity_mode"] == "strict_per_query_reference_comparison"
    assert runtime["backend_loss_assessment"]["lossless"] is False
    assert runtime["backend_execution"]["parity_verified_queries"] == 1


@pytest.mark.parametrize("backend", ["igraph", "graph-tool", "snap"])
def test_optional_native_adapter_is_used_by_live_query_path(monkeypatch, backend):
    install_fake(monkeypatch, backend)
    graph = graph_fixture()
    result, runtime = _query_result(graph, backend)
    reference = SemanticGraphAnalysisService(graph, traversal_backend="reference").analyze(
        GraphQuery(
            "e83-backend-parity", QueryType.DEPENDENCY, ["A"],
            {"direction": "outgoing", "relation_types": ["IMPORTS", "DEPENDS_ON"], "max_depth": 3},
        )
    )
    assert result.discovered_entities == reference.discovered_entities == ("B", "C")
    assert result.observations == reference.observations
    assert result.evidence == reference.evidence
    assert runtime["active_computation_backend"] == backend
    assert runtime["backend_library"] == backend
    assert runtime["backend_execution"]["parity_verified_queries"] == 1
    assert runtime["backend_pipeline"]["backend"] == backend


def test_native_projection_mutation_fails_closed(monkeypatch):
    install_fake(monkeypatch, "igraph")
    graph = graph_fixture()
    engine = NativeAdapterGraphTraversalEngine(graph, "igraph")
    engine.adapter.graph.es.attrs["relation"][0] = "CORRUPTED"
    with pytest.raises(NativeAdapterProjectionError, match="native_edge_projection_semantic_mismatch"):
        engine.walk("A", max_depth=2)


def test_explicit_backend_selection_never_silently_falls_back(monkeypatch):
    from audit_engine.semantic_audit.graph.backend.adapter_traversal import NativeAdapterGraphTraversalEngine
    from audit_engine.semantic_audit.graph.backend.optional_backend_support import BackendUnavailableError
    from audit_engine.semantic_audit.graph.backend import optional_backend_support as support
    monkeypatch.setattr(support, "backend_available", lambda name: False if name == "igraph" else True)
    # The registry reads backend_available at construction time; explicit igraph
    # selection must fail instead of falling back to NetworkX.
    with pytest.raises(BackendUnavailableError, match="not installed"):
        NativeAdapterGraphTraversalEngine(graph_fixture(), "igraph")


def test_backend_registry_marks_all_adapters_as_semantic_query_capable():
    from audit_engine.semantic_audit.graph.backend.capability_registry import create_default_registry
    registry = create_default_registry()
    for backend in ("networkx", "scipy", "igraph", "graph-tool", "snap"):
        assert registry.get(backend)["capabilities"]["semantic_traversal"] is True


@pytest.mark.parametrize(
    ("backend", "module_name"),
    [("igraph", "igraph"), ("graph-tool", "graph_tool"), ("snap", "snap")],
)
def test_real_optional_native_backend_query_when_installed(backend, module_name):
    import importlib.util
    if importlib.util.find_spec(module_name) is None:
        pytest.skip(f"{backend} native library is not installed in this interpreter")
    graph = graph_fixture()
    result, runtime = _query_result(graph, backend)
    assert result.discovered_entities == ("B", "C")
    assert runtime["active_computation_backend"] == backend
    assert runtime["backend_execution"]["parity_verified_queries"] == 1

"""Native optional backend contract tests; fake native objects test projection logic.

Fakes do not certify binary compatibility with a real optional library. Actual
native smoke tests run separately when the correct library is installed.
"""
import copy
import importlib.machinery
import json
import sys
import types

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.backend.backend_factory import BackendFactory
from audit_engine.semantic_audit.graph.backend.backend_selector import BackendSelectionPolicy
from audit_engine.semantic_audit.graph.backend.capability_registry import create_default_registry
from audit_engine.semantic_audit.graph.backend.execution_context import BackendExecutionContext
from audit_engine.semantic_audit.graph.backend.backend_pipeline import BackendPipeline
from audit_engine.semantic_audit.graph.backend.optional_backend_support import BackendUnavailableError


class FakeIGraph:
    def __init__(self, directed):
        assert directed
        self.vs, self.es = {}, {}
        self.vertex_count = 0
        self.edge_list = []

    def add_vertices(self, n):
        self.vertex_count += n

    def add_edges(self, pairs):
        self.edge_list.extend(pairs)


class FakeProperty(dict):
    pass


class FakeToolGraph:
    def __init__(self, directed):
        assert directed
        self.vertex_properties, self.edge_properties = {}, {}
        self.n = 0
        self.edge_list = []

    def add_vertex(self, n):
        self.n += n

    def vertex(self, i):
        return i

    def new_vertex_property(self, kind):
        assert kind in {"string", "object"}
        return FakeProperty()

    def new_edge_property(self, kind):
        assert kind in {"string", "object", "int64_t"}
        return FakeProperty()

    def add_edge(self, source, target):
        edge_id = len(self.edge_list)
        self.edge_list.append((source, target))
        return edge_id


class FakeSNAPNetwork:
    def __init__(self):
        self.nodes, self.edges = [], []
        self.attrs_n, self.attrs_e = {}, {}
        self.node_values, self.edge_values = {}, {}

    def AddStrAttrN(self, name):
        self.attrs_n[name] = "str"

    def AddStrAttrE(self, name):
        self.attrs_e[name] = "str"

    def AddIntAttrE(self, name):
        self.attrs_e[name] = "int"

    def AddNode(self, ident):
        assert ident not in self.nodes
        self.nodes.append(ident)
        return ident

    def AddEdge(self, src, dst):
        ident = len(self.edges)
        self.edges.append((src, dst))
        return ident

    def AddStrAttrDatN(self, ident, value, name):
        assert self.attrs_n[name] == "str"
        self.node_values[(ident, name)] = value

    def AddStrAttrDatE(self, ident, value, name):
        assert self.attrs_e[name] == "str"
        self.edge_values[(ident, name)] = value

    def AddIntAttrDatE(self, ident, value, name):
        assert self.attrs_e[name] == "int"
        self.edge_values[(ident, name)] = value


class FakeSNAPType:
    @staticmethod
    def New():
        return FakeSNAPNetwork()


@pytest.fixture(params=["igraph", "graph-tool", "snap"])
def fake_native(request, monkeypatch):
    name = request.param
    module_name = {"igraph": "igraph", "graph-tool": "graph_tool", "snap": "snap"}[name]
    lib = types.ModuleType(module_name)
    lib.__spec__ = importlib.machinery.ModuleSpec(module_name, loader=None)
    if name == "igraph":
        lib.Graph = FakeIGraph
    elif name == "graph-tool":
        lib.Graph = FakeToolGraph
    else:
        lib.TNEANet = FakeSNAPType
    monkeypatch.setitem(sys.modules, module_name, lib)
    return name


def graph_fixture():
    g = SemanticGraph()
    for name in ["A", "B", "C"]:
        g.add_node(SemanticNode(name, "Concept", {"count": 3, "labels": ["x", name]}, {"provenance": {"source": "paper"}}))
    # Two parallel typed relationships, an inverse relationship, and a self-loop.
    for src, dst, rel, number in [
        ("A", "B", "DEPENDS_ON", 1),
        ("A", "B", "CITES", 2),
        ("B", "A", "DERIVES_FROM", 3),
        ("C", "C", "SELF_REVIEW", 4),
    ]:
        g.add_edge(SemanticEdge(src, dst, rel, {"n": number}, {"source": f"ref-{number}"}))
    return g


def test_native_backend_preserves_multiplicity_and_metadata(fake_native):
    graph = graph_fixture()
    before = copy.deepcopy(graph.to_dict())
    adapter = BackendFactory().create(fake_native, BackendExecutionContext(graph))
    assert adapter.export() is adapter.backend_graph()
    assert adapter.capabilities()["directed_graph"] is True
    assert adapter.capabilities()["multiedges"] is True
    assert adapter.capabilities()["self_loops"] is True
    assert adapter.capabilities()["lossless"] is True
    mapping = adapter.identity_mapping()
    assert mapping["semantic_to_backend"] == {"A": 0, "B": 1, "C": 2}
    assert mapping["backend_to_semantic"] == {0: "A", 1: "B", 2: "C"}
    assert list(mapping["semantic_edge_occurrence_to_backend"]) == list(range(4))
    assert adapter.nodes() == ["A", "B", "C"]
    assert adapter.neighbors("A") == ["B"]  # deduplicate parallel edges
    assert adapter.neighbors("C") == ["C"]
    assert adapter.edges()[1]["relation"] == "CITES"
    assert graph.to_dict() == before

    native = adapter.export()
    if fake_native == "igraph":
        assert native.vertex_count == 3
        assert native.edge_list == [(0, 1), (0, 1), (1, 0), (2, 2)]
        assert native.vs["semantic_id"] == ["A", "B", "C"]
        assert native.es["semantic_occurrence"] == [0, 1, 2, 3]
        assert native.es["attributes"][1] == {"n": 2}
        assert native.vs["metadata"][0] == {"provenance": {"source": "paper"}}
    elif fake_native == "graph-tool":
        assert native.n == 3
        assert native.edge_list == [(0, 1), (0, 1), (1, 0), (2, 2)]
        assert native.vertex_properties["semantic_id"][0] == "A"
        assert native.edge_properties["relation"][1] == "CITES"
        assert native.edge_properties["semantic_occurrence"][3] == 3
        assert native.vertex_properties["attributes"][0]["labels"] == ["x", "A"]
    else:
        assert native.nodes == [0, 1, 2]
        assert native.edges == [(0, 1), (0, 1), (1, 0), (2, 2)]
        assert native.node_values[(0, "semantic_id")] == "A"
        assert json.loads(native.node_values[(0, "metadata_json")]) == {"provenance": {"source": "paper"}}
        assert native.edge_values[(1, "relation")] == "CITES"
        assert json.loads(native.edge_values[(1, "attributes_json")]) == {"n": 2}
        assert native.edge_values[(3, "semantic_occurrence")] == 3


def test_empty_graph_supported(fake_native):
    adapter = BackendFactory().create(fake_native, BackendExecutionContext(SemanticGraph()))
    assert adapter.nodes() == []
    assert adapter.edges() == []
    assert adapter.identity_mapping()["semantic_to_backend"] == {}


def test_source_mutations_not_reflected_in_native_data(fake_native):
    original = graph_fixture()
    adapter = BackendFactory().create(fake_native, BackendExecutionContext(original))
    original.nodes[0].attributes["count"] = 999
    assert adapter._projection.nodes[0]["attributes"]["count"] == 3


def test_ambiguous_direct_mutation_rejected_before_projection(fake_native):
    g = graph_fixture()
    g.nodes.append(SemanticNode("A", "Duplicate"))
    with pytest.raises(ValueError, match="duplicate"):
        BackendFactory().create(fake_native, BackendExecutionContext(g))
    g = graph_fixture()
    g.edges[0].target_id = "MISSING"
    with pytest.raises(ValueError, match="Dangling"):
        BackendFactory().create(fake_native, BackendExecutionContext(g))


def test_invalid_attribute_dictionary_rejected(fake_native):
    g = graph_fixture()
    g.nodes[0].metadata = []
    with pytest.raises(TypeError, match="dictionaries"):
        BackendFactory().create(fake_native, BackendExecutionContext(g))


def test_pipeline_provenance_and_correct_loss_assessment(fake_native):
    registry = create_default_registry()
    policy = BackendSelectionPolicy(registry)
    result = BackendPipeline(policy, BackendFactory()).execute(
        {"available": True, "optional": True, "json_attributes_only": fake_native == "snap"},
        BackendExecutionContext(graph_fixture(), task_type="scientific"),
    )
    # igraph and graph-tool share capabilities, selection is deterministic.
    if fake_native != "snap":
        assert result.backend in ("igraph", "graph-tool")
    else:
        assert result.backend == "snap"
    assert result.loss_assessment.lossless
    assert result.loss_assessment.details["lossless"]
    assert result.summary()["provenance_count"] == 1


def test_optional_registration_does_not_eager_import(monkeypatch):
    for name in ("igraph", "graph_tool", "snap"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    registry = create_default_registry()
    assert {"igraph", "graph-tool", "snap"}.issubset(set(registry.list_backends()))
    for name in ("igraph", "graph-tool", "snap"):
        assert isinstance(registry.get(name)["capabilities"]["available"], bool)
        assert registry.get(name)["capabilities"]["multiedges"]
        assert registry.get(name)["capabilities"]["metadata"]
    assert all(name not in sys.modules for name in ("igraph", "graph_tool", "snap"))


def test_optional_backend_unavailable_has_actionable_error(monkeypatch):
    from audit_engine.semantic_audit.graph.backend import optional_backend_support as support
    import builtins
    import importlib
    original = importlib.import_module
    def refusing(name, *args, **kwargs):
        if name in {"igraph", "graph_tool", "snap"}:
            raise ModuleNotFoundError(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(importlib, "import_module", refusing)
    for name in ("igraph", "graph-tool", "snap"):
        with pytest.raises(BackendUnavailableError, match="Install|install"):
            support.require_backend(name)


def test_wrong_snap_package_rejected(monkeypatch):
    wrong = types.ModuleType("snap")
    wrong.__spec__ = importlib.machinery.ModuleSpec("snap", loader=None)
    monkeypatch.setitem(sys.modules, "snap", wrong)
    with pytest.raises(BackendUnavailableError, match="Stanford Snap.py"):
        BackendFactory().create("snap", BackendExecutionContext(graph_fixture()))


def test_snap_json_only_does_not_silently_lose_python_objects(fake_native):
    if fake_native != "snap":
        pytest.skip("JSON restriction is specific to SNAP")
    g = graph_fixture()
    g.nodes[0].attributes["set"] = {1, 2}
    with pytest.raises(TypeError, match="canonical JSON"):
        BackendFactory().create("snap", BackendExecutionContext(g))
    g = graph_fixture()
    g.nodes[0].metadata["nan"] = float("nan")
    with pytest.raises(TypeError, match="canonical JSON"):
        BackendFactory().create("snap", BackendExecutionContext(g))


def test_legacy_backends_remain_functional():
    g = graph_fixture()
    for name in ("networkx", "scipy"):
        adapter = BackendFactory().create(name, BackendExecutionContext(g))
        assert adapter.export() is not None
        assert adapter.loss_report() is not None
    reg = create_default_registry()
    policy = BackendSelectionPolicy(reg)
    assert policy.select({"sparse_matrix": True}) == "scipy"
    assert policy.select({"lossless": True, "metadata": True}) == "networkx"
    sparse_result = BackendPipeline(policy, BackendFactory()).execute(
        {"sparse_matrix": True}, BackendExecutionContext(g))
    assert sparse_result.loss_assessment.lossless is False


def test_selector_skips_unavailable_extensions():
    reg = create_default_registry()
    for name in ("igraph", "graph-tool", "snap"):
        reg.get(name)["capabilities"]["available"] = False
    choices = BackendSelectionPolicy(reg).find_backends({"lossless": True, "metadata": True})
    assert choices == ["networkx"]
    with pytest.raises(ValueError, match="No available"):
        BackendSelectionPolicy(reg).select({"optional": True})


def test_factory_unknown_backend_rejected():
    with pytest.raises(ValueError, match="Unknown backend"):
        BackendFactory().create("made-up", BackendExecutionContext(SemanticGraph()))

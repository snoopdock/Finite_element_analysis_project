"""Graph backend capabilities and optional dependency availability."""

from audit_engine.semantic_audit.graph.backend.optional_backend_support import backend_available


class BackendCapabilityRegistry:
    def __init__(self):
        self._backends = {}

    def register(self, name, adapter, capabilities):
        self._backends[name] = {"adapter": adapter, "capabilities": dict(capabilities)}

    def get(self, name):
        return self._backends[name]

    def list_backends(self):
        return list(self._backends.keys())

    def describe(self):
        return {name: dict(item["capabilities"]) for name, item in self._backends.items()}


def _acceptance_state(backend_name, adjacency_implementation):
    """Separate implementation/discoverability from conformance and approval."""
    return {
        "implementation": "present",
        "module_discoverable": backend_available(backend_name),
        "api_compatibility": "not_checked",
        "structural_conformance": "not_run",
        "native_adjacency_conformance": "not_run",
        "native_adjacency_implementation": adjacency_implementation,
        "repository_conformance": "not_run",
        "production_approval": False,
    }


def create_default_registry():
    registry = BackendCapabilityRegistry()
    registry.register("networkx", "NetworkXAdapter", {
        "acceptance_state": _acceptance_state("networkx", "implemented_unvalidated"),
        "lossless": True, "metadata": True, "multiedges": True,
        "directed": True, "semantic_traversal": True,
        "available": backend_available("networkx"),
    })
    registry.register("scipy", "SciPyAdapter", {
        "acceptance_state": _acceptance_state("scipy", "not_implemented"),
        # CSR is a hybrid backend: the matrix indexes connectivity while
        # exact typed edge occurrences and metadata are preserved separately.
        "lossless": False, "sparse_matrix": True, "metadata": False,
        "relation_side_channel": True, "directed": True, "multiedges": False,
        "semantic_traversal": True, "side_channel_preservation": True,
        "available": backend_available("scipy"),
    })
    for name, klass in (("igraph", "IGraphAdapter"),
                        ("graph-tool", "GraphToolAdapter"), ("snap", "SNAPAdapter")):
        registry.register(name, klass, {
            "acceptance_state": _acceptance_state(name, "not_implemented"),
            "lossless": True, "metadata": True, "multiedges": True,
            "directed": True, "semantic_traversal": True,
            "available": backend_available(name),
            "optional": True,
            "json_attributes_only": name == "snap",
        })
    return registry

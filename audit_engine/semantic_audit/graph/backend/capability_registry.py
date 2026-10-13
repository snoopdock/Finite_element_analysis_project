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


def create_default_registry():
    registry = BackendCapabilityRegistry()
    registry.register("networkx", "NetworkXAdapter", {
        "lossless": True, "metadata": True, "multiedges": True,
        "directed": True, "available": True,
    })
    registry.register("scipy", "SciPyAdapter", {
        "lossless": False, "sparse_matrix": True, "metadata": False,
        "relation_side_channel": True, "directed": True, "multiedges": False,
        "available": True,
    })
    for name, klass in (("igraph", "IGraphAdapter"),
                        ("graph-tool", "GraphToolAdapter"), ("snap", "SNAPAdapter")):
        registry.register(name, klass, {
            "lossless": True, "metadata": True, "multiedges": True,
            "directed": True, "available": backend_available(name),
            "optional": True,
            "json_attributes_only": name == "snap",
        })
    return registry

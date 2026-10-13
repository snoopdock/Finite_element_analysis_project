"""Lazy, backward-compatible factory for semantic graph computational backends."""


class BackendFactory:
    _ADAPTERS = {
        "networkx": ("networkx_adapter", "NetworkXAdapter"),
        "scipy": ("scipy_adapter", "SciPyAdapter"),
        "igraph": ("igraph_adapter", "IGraphAdapter"),
        "graph-tool": ("graph_tool_adapter", "GraphToolAdapter"),
        "snap": ("snap_adapter", "SNAPAdapter"),
    }

    def create(self, backend_name, context):
        if backend_name not in self._ADAPTERS:
            raise ValueError(f"Unknown backend: {backend_name}")
        import importlib
        module_name, class_name = self._ADAPTERS[backend_name]
        module = importlib.import_module(
            "audit_engine.semantic_audit.graph.backend." + module_name
        )
        return getattr(module, class_name)(context.graph)
